from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.schemas.client_lust_cert import LustClientCertificateIssueRequest, LustClientCertificateRead
from onx.services.client_auth_service import client_auth_service
from onx.services.client_device_service import client_device_service
from onx.services.device_certificate_service import device_certificate_service


router = APIRouter(prefix="/client/lust/cert", tags=["client-lust-cert"])


def _resolve_client_user(db: Session, authorization: str | None):
    token = _extract_bearer_token(authorization)
    resolved = client_auth_service.resolve_session(db, token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client session is not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session = resolved
    client_auth_service.touch_session(db, session)
    return user


def _serialize_current(item) -> LustClientCertificateRead:
    payload = device_certificate_service.serialize_certificate(item)
    payload["ca_certificate_pem"] = device_certificate_service.ca_certificate_pem()
    return LustClientCertificateRead(**payload)


@router.post("/issue", response_model=LustClientCertificateRead, status_code=status.HTTP_200_OK)
def issue_client_lust_certificate(
    payload: LustClientCertificateIssueRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> LustClientCertificateRead:
    user = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=payload.device_id)
    certificate = device_certificate_service.issue_for_device(db, device=device, csr_pem=payload.csr_pem)
    return _serialize_current(certificate)


@router.get("/current", response_model=LustClientCertificateRead | None, status_code=status.HTTP_200_OK)
def get_current_client_lust_certificate(
    device_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> LustClientCertificateRead | None:
    user = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=device_id)
    certificate = device_certificate_service.get_current_for_device(db, device_id=device.id)
    if certificate is None:
        return None
    return _serialize_current(certificate)


@router.post("/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_client_lust_certificate(
    device_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> Response:
    user = _resolve_client_user(db, authorization)
    device = client_device_service.get_owned_device(db, user_id=user.id, device_id=device_id)
    device_certificate_service.revoke_for_device(db, device_id=device.id, commit=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
