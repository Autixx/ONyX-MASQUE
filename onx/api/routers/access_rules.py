from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.security.admin_access import admin_access_control
from onx.db.models.event_log import EventLevel
from onx.schemas.access_rules import AccessRuleMatrixRead, AccessRuleRead, AccessRuleUpsert
from onx.services.access_rule_service import AccessRuleService
from onx.services.event_log_service import EventLogService


router = APIRouter(prefix="/access-rules", tags=["access-rules"])
access_rule_service = AccessRuleService()
event_log_service = EventLogService()


def _serialize_rule(item) -> dict:
    return {
        "id": item.id,
        "permission_key": item.permission_key,
        "description": item.description,
        "allowed_roles": list(item.allowed_roles_json or []),
        "enabled": item.enabled,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _serialize_rule_for_audit(item) -> dict:
    return {
        "id": item.id,
        "permission_key": item.permission_key,
        "description": item.description,
        "allowed_roles": list(item.allowed_roles_json or []),
        "enabled": item.enabled,
        "created_at": item.created_at.isoformat() if item.created_at is not None else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at is not None else None,
    }


def _build_audit_details(request: Request) -> dict:
    context = getattr(request.state, "admin_access_context", {}) or {}
    return {
        "path": request.url.path,
        "method": request.method.upper(),
        "client_ip": request.client.host if request.client else None,
        "actor_roles": context.get("roles", []),
        "auth_kind": context.get("auth_kind"),
        "permission_key": context.get("permission_key"),
    }


@router.get("", response_model=list[AccessRuleRead])
def list_access_rules(db: Session = Depends(get_database_session)) -> list[dict]:
    return [_serialize_rule(item) for item in access_rule_service.list_rules(db)]


@router.get("/matrix", response_model=AccessRuleMatrixRead)
def get_access_rule_matrix(db: Session = Depends(get_database_session)) -> AccessRuleMatrixRead:
    return AccessRuleMatrixRead(
        items=admin_access_control.describe_permission_matrix(db)
    )


@router.put("/{permission_key}", response_model=AccessRuleRead)
def upsert_access_rule(
    permission_key: str,
    payload: AccessRuleUpsert,
    request: Request,
    db: Session = Depends(get_database_session),
) -> dict:
    existing_rule = access_rule_service.get_rule_by_permission_key(db, permission_key)
    previous_state = _serialize_rule_for_audit(existing_rule) if existing_rule is not None else None
    try:
        rule = access_rule_service.upsert_rule(db, permission_key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    current_state = _serialize_rule(rule)
    details = _build_audit_details(request)
    details["previous"] = previous_state
    details["current"] = _serialize_rule_for_audit(rule)
    event_log_service.log(
        db,
        entity_type="access_rule",
        entity_id=rule.id,
        level=EventLevel.INFO,
        message="Access rule upserted.",
        details=details,
    )
    return current_state


@router.delete("/{permission_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_access_rule(
    permission_key: str,
    request: Request,
    db: Session = Depends(get_database_session),
) -> Response:
    rule = access_rule_service.get_rule_by_permission_key(db, permission_key)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access rule not found.")
    deleted_state = _serialize_rule_for_audit(rule)
    access_rule_service.delete_rule(db, rule)
    details = _build_audit_details(request)
    details["deleted"] = deleted_state
    event_log_service.log(
        db,
        entity_type="access_rule",
        entity_id=deleted_state["id"],
        level=EventLevel.WARNING,
        message="Access rule deleted.",
        details=details,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
