from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.lust_service import LustService
from onx.db.models.node import Node
from onx.db.models.peer import Peer
from onx.schemas.peers import PeerConfigUpdate, PeerCreate, PeerRead
from onx.services.event_log_service import EventLogService
from onx.services.lust_routing_service import lust_routing_service
from onx.services.lust_service_service import lust_service_manager
from onx.services.realtime_service import realtime_service


router = APIRouter(prefix="/peers", tags=["peers"])
event_log_service = EventLogService()


@router.get("", response_model=list[PeerRead], status_code=status.HTTP_200_OK)
def list_peers(
    node_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    include_revoked: bool = Query(default=False),
    db: Session = Depends(get_database_session),
) -> list[Peer]:
    query = select(Peer).order_by(Peer.created_at.desc())
    if not include_revoked:
        query = query.where(Peer.revoked_at.is_(None), Peer.is_active.is_(True))
    if node_id:
        query = query.where(Peer.node_id == node_id)
    if username:
        query = query.where(Peer.username.ilike(f"%{username.strip()}%"))
    return list(db.scalars(query).all())


@router.post("", response_model=PeerRead, status_code=status.HTTP_201_CREATED)
def create_peer(payload: PeerCreate, db: Session = Depends(get_database_session)) -> Peer:
    node = db.get(Node, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    if payload.lust_service_id:
        service = db.get(LustService, payload.lust_service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
    try:
        lust_route_override = lust_routing_service.normalize_peer_route_override(
            db,
            gateway_service_id=payload.lust_service_id,
            override=payload.lust_route_override.model_dump(mode="python"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    peer = Peer(
        username=payload.username,
        email=payload.email,
        node_id=payload.node_id,
        lust_service_id=payload.lust_service_id,
        registered_at=payload.registered_at,
        config_expires_at=payload.config_expires_at,
        last_ip=payload.last_ip,
        traffic_24h_mb=payload.traffic_24h_mb,
        traffic_month_mb=payload.traffic_month_mb,
        config=payload.config,
        lust_route_override_json=lust_route_override,
    )
    db.add(peer)
    db.commit()
    db.refresh(peer)
    return peer


@router.get("/{peer_id}", response_model=PeerRead, status_code=status.HTTP_200_OK)
def get_peer(peer_id: str, db: Session = Depends(get_database_session)) -> Peer:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    return peer


@router.put("/{peer_id}/config", response_model=PeerRead, status_code=status.HTTP_200_OK)
def update_peer_config(
    peer_id: str,
    payload: PeerConfigUpdate,
    db: Session = Depends(get_database_session),
) -> Peer:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    provided_fields = set(payload.model_fields_set)
    if "config" in provided_fields:
        peer.config = payload.config
    if "lust_service_id" in provided_fields:
        if payload.lust_service_id:
            service = db.get(LustService, payload.lust_service_id)
            if service is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST service not found.")
        peer.lust_service_id = payload.lust_service_id
    override_payload = peer.lust_route_override_json
    if "lust_route_override" in provided_fields and payload.lust_route_override is not None:
        override_payload = payload.lust_route_override.model_dump(mode="python")
    elif "lust_service_id" in provided_fields and not peer.lust_service_id:
        override_payload = {}
    try:
        peer.lust_route_override_json = lust_routing_service.normalize_peer_route_override(
            db,
            gateway_service_id=peer.lust_service_id,
            override=override_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.add(peer)
    db.commit()
    db.refresh(peer)
    return peer


@router.post("/{peer_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_peer(peer_id: str, db: Session = Depends(get_database_session)) -> Response:
    peer = db.get(Peer, peer_id)
    if peer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peer not found.")
    lust_service_id = peer.lust_service_id
    peer.is_active = False
    peer.revoked_at = datetime.now(timezone.utc)
    db.add(peer)
    db.commit()
    if lust_service_id:
        service = lust_service_manager.get_service(db, lust_service_id)
        if service is not None and service.state == "active":
            lust_service_manager.apply_service(db, service)
    event_log_service.log(
        db,
        entity_type="peer",
        entity_id=peer.id,
        message=f"Peer '{peer.username}' revoked.",
        details={
            "node_id": peer.node_id,
            "lust_service_id": lust_service_id,
        },
    )
    realtime_service.publish("peer.revoked", {"id": peer.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
