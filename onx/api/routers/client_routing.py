from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.security.client_access import client_access_control
from onx.schemas.client_routing import (
    BestIngressRequest,
    BestIngressResponse,
    BootstrapRequest,
    BootstrapResponse,
    ProbeReportRequest,
    ProbeReportResponse,
    SessionRebindRequest,
    SessionRebindResponse,
)
from onx.services.client_routing_service import ClientRoutingService


router = APIRouter(tags=["client-routing"])
client_routing_service = ClientRoutingService()


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=status.HTTP_200_OK)
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> BootstrapResponse:
    client_access_control.require_auth(request)
    client_access_control.enforce_bootstrap_limits(request, device_id=payload.device_id)
    try:
        result = client_routing_service.bootstrap(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BootstrapResponse.model_validate(result)


@router.post("/probe", response_model=ProbeReportResponse, status_code=status.HTTP_200_OK)
def submit_probe(
    payload: ProbeReportRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> ProbeReportResponse:
    client_access_control.require_auth(request)
    client_access_control.enforce_probe_limits(request, session_id=payload.session_id)
    try:
        result = client_routing_service.submit_probe(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProbeReportResponse.model_validate(result)


@router.post("/best-ingress", response_model=BestIngressResponse, status_code=status.HTTP_200_OK)
def best_ingress(
    payload: BestIngressRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> BestIngressResponse:
    client_access_control.require_auth(request)
    client_access_control.enforce_best_ingress_limits(request, session_id=payload.session_id)
    try:
        result = client_routing_service.choose_best_ingress(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BestIngressResponse.model_validate(result)


@router.post("/session-rebind", response_model=SessionRebindResponse, status_code=status.HTTP_200_OK)
def session_rebind(
    payload: SessionRebindRequest,
    request: Request,
    db: Session = Depends(get_database_session),
) -> SessionRebindResponse:
    client_access_control.require_auth(request)
    client_access_control.enforce_rebind_limits(request, session_id=payload.session_id)
    try:
        result = client_routing_service.session_rebind(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SessionRebindResponse.model_validate(result)
