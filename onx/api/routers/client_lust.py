from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.routers.client_auth import _extract_bearer_token
from onx.schemas.client_lust import LustClientSessionRead
from onx.services.lust_service_service import lust_service_manager


router = APIRouter(prefix="/lust", tags=["client-lust"])


def _resolve_session(db: Session, authorization: str | None, peer_id: str | None):
    token = _extract_bearer_token(authorization)
    resolved = lust_service_manager.resolve_session_by_token(db, token=token, peer_id=peer_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LuST session token is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return resolved


def _serialize_session(peer, service) -> LustClientSessionRead:
    stream_path = str(service.h2_path or "/lust").rstrip("/") + "/stream"
    return LustClientSessionRead(
        peer_id=peer.id,
        username=peer.username,
        service_id=service.id,
        service_name=service.name,
        node_id=service.node_id,
        stream_path=stream_path,
        dns_resolver=service.client_dns_resolver,
        connected_at=datetime.now(timezone.utc),
    )


@router.get("", response_model=LustClientSessionRead, status_code=status.HTTP_200_OK)
def lust_session(
    authorization: str | None = Header(default=None),
    x_onyx_peer_id: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
) -> LustClientSessionRead:
    peer, service = _resolve_session(db, authorization, x_onyx_peer_id)
    return _serialize_session(peer, service)


@router.get("/stream", status_code=status.HTTP_200_OK)
async def lust_session_stream(
    authorization: str | None = Header(default=None),
    x_onyx_peer_id: str | None = Header(default=None),
    db: Session = Depends(get_database_session),
):
    peer, service = _resolve_session(db, authorization, x_onyx_peer_id)
    session = _serialize_session(peer, service)

    async def _event_source():
        hello = {"type": "hello", **session.model_dump(mode="json")}
        yield "event: hello\n"
        yield f"data: {json.dumps(hello, separators=(',', ':'), ensure_ascii=True)}\n\n"
        while True:
            payload = {
                "type": "ping",
                "peer_id": peer.id,
                "service_id": service.id,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            yield "event: ping\n"
            yield f"data: {json.dumps(payload, separators=(',', ':'), ensure_ascii=True)}\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
