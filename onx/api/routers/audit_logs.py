from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.schemas.jobs import EventLogRead, EventLevelValue
from onx.services.event_log_service import EventLogService


router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])
event_log_service = EventLogService()


@router.get("", response_model=list[EventLogRead])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    entity_type: str | None = Query(default=None, min_length=1, max_length=64),
    entity_id: str | None = Query(default=None, min_length=1, max_length=64),
    level: EventLevelValue | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list:
    level_value: EventLevel | None = None
    if level is not None:
        try:
            level_value = EventLevel(level.value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid audit log level.") from exc
    return event_log_service.list_events(
        db,
        limit=limit,
        entity_type=entity_type,
        entity_id=entity_id,
        level=level_value,
    )
