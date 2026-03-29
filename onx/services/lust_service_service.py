from __future__ import annotations

import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.device_certificate import DeviceCertificate
from onx.db.models.lust_service import LustService
from onx.db.models.node import Node
from onx.db.models.peer import Peer
from onx.services.lust_edge_deploy_service import lust_edge_deploy_service


class LustServiceManager:
    def list_services(self, db: Session, *, node_id: str | None = None) -> list[LustService]:
        query = select(LustService).order_by(LustService.created_at.desc())
        if node_id:
            query = query.where(LustService.node_id == node_id)
        return list(db.scalars(query).all())

    def get_service(self, db: Session, service_id: str) -> LustService | None:
        return db.get(LustService, service_id)

    def create_service(self, db: Session, payload) -> LustService:
        existing = db.scalar(select(LustService).where(LustService.name == payload.name))
        if existing is not None:
            raise ValueError("LuST service with this name already exists.")
        service = LustService(**payload.model_dump())
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def update_service(self, db: Session, service: LustService, payload) -> LustService:
        dumped = payload.model_dump(exclude_unset=True)
        if "name" in dumped and dumped["name"] and dumped["name"] != service.name:
            existing = db.scalar(select(LustService).where(LustService.name == dumped["name"]))
            if existing is not None and existing.id != service.id:
                raise ValueError("LuST service with this name already exists.")
        for field_name, value in dumped.items():
            setattr(service, field_name, value)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service

    def delete_service(self, db: Session, service: LustService) -> None:
        db.delete(service)
        db.commit()

    def apply_service(self, db: Session, service: LustService) -> LustService:
        if not service.public_host.strip():
            raise ValueError("LuST service public_host is required.")
        service.desired_config_json = lust_edge_deploy_service.build_service_deployment(db, service)
        service.state = "applying"
        service.last_error_text = None
        service.health_summary_json = {
            "status": "applying",
            "listen": f"{service.listen_host}:{service.listen_port}",
            "endpoint": f"{service.public_host}:{service.public_port or service.listen_port}",
            "http_version": "h2",
            "tls": bool(service.use_tls),
            "edge_mode": "external",
        }
        db.add(service)
        db.commit()
        from onx.services.lust_edge_node_service import lust_edge_node_service
        try:
            lust_edge_node_service.deploy_service(db, service)
        except Exception as exc:
            service.state = "failed"
            service.last_error_text = str(exc)
            service.health_summary_json = {
                "status": "failed",
                "listen": f"{service.listen_host}:{service.listen_port}",
                "endpoint": f"{service.public_host}:{service.public_port or service.listen_port}",
                "http_version": "h2",
                "tls": bool(service.use_tls),
                "edge_mode": "external",
            }
            db.add(service)
            db.commit()
            raise
        db.refresh(service)
        return service

    def assign_peer(self, db: Session, service: LustService, peer: Peer, *, save_to_peer: bool = True) -> dict:
        token = self._extract_existing_token(peer) or secrets.token_urlsafe(24)
        profile = self.render_peer_config(service, peer, token=token)
        if save_to_peer:
            peer.node_id = service.node_id
            peer.lust_service_id = service.id
            peer.xray_service_id = None
            peer.awg_service_id = None
            peer.wg_service_id = None
            peer.openvpn_cloak_service_id = None
            peer.config = json.dumps(profile, separators=(",", ":"), ensure_ascii=True)
            db.add(peer)
            db.commit()
            db.refresh(peer)
        return {
            "peer_id": peer.id,
            "node_id": service.node_id,
            "service_id": service.id,
            "token_hint": token[-6:],
        }

    @staticmethod
    def render_peer_config(service: LustService, peer: Peer, *, token: str) -> dict:
        endpoint_port = service.public_port or service.listen_port
        return {
            "type": "lust",
            "protocol": "lust-h2",
            "version": 1,
            "endpoint": {
                "scheme": "https" if service.use_tls else "http",
                "host": service.public_host,
                "port": endpoint_port,
                "server_name": service.tls_server_name or service.public_host,
                "path": service.h2_path,
                "http_version": "2",
            },
            "session": {
                "protocol": "lust-h2",
                "stream_path": str(service.h2_path or "/lust").rstrip("/") + "/stream",
                "open_path": str(service.h2_path or "/lust").rstrip("/") + "/session/open",
                "frame_path": str(service.h2_path or "/lust").rstrip("/") + "/frame",
                "poll_path": str(service.h2_path or "/lust").rstrip("/") + "/frame/poll",
                "close_path": str(service.h2_path or "/lust").rstrip("/") + "/session/close",
                "heartbeat_seconds": 15,
                "connect_timeout_seconds": 10,
                "poll_timeout_seconds": 20,
            },
            "authentication": {
                "scheme": service.auth_scheme,
                "token": token,
            },
            "client": {
                "peer_id": peer.id,
                "username": peer.username,
            },
            "dns": {
                "resolver": service.client_dns_resolver,
            },
        }

    @staticmethod
    def render_runtime_profile(
        service: LustService,
        peer: Peer,
        *,
        token: str,
        certificate: DeviceCertificate,
        ca_certificate_pem: str,
    ) -> dict:
        profile = LustServiceManager.render_peer_config(service, peer, token=token)
        profile["authentication"] = {
            "scheme": "bearer",
            "token": token,
        }
        profile["mtls"] = {
            "mode": "required" if service.use_tls else "disabled",
            "client_certificate_pem": certificate.certificate_pem,
            "client_certificate_fingerprint_sha256": certificate.fingerprint_sha256,
            "ca_certificate_pem": ca_certificate_pem,
            "client_key_ref": "lust-client-key",
        }
        profile["edge"] = {
            "service_id": service.id,
            "node_id": service.node_id,
        }
        profile["tunnel"] = {
            "mode": "wintun",
            "interface_name": "wintun",
            "address_v4": "198.18.0.1",
            "netmask_v4": "255.255.0.0",
            "gateway_v4": "198.18.0.1",
            "mtu": 1380,
            "dns_servers": [service.client_dns_resolver] if service.client_dns_resolver else [],
            "bypass_routes": [],
        }
        return profile

    @staticmethod
    def _extract_existing_token(peer: Peer) -> str | None:
        if not peer.config:
            return None
        try:
            parsed = json.loads(peer.config)
        except json.JSONDecodeError:
            return None
        auth = parsed.get("authentication") if isinstance(parsed, dict) else None
        token = auth.get("token") if isinstance(auth, dict) else None
        return str(token).strip() or None

    def resolve_session_by_token(self, db: Session, *, token: str | None, peer_id: str | None = None) -> tuple[Peer, LustService] | None:
        normalized = str(token or "").strip()
        if not normalized:
            return None
        peers = list(
            db.scalars(
                select(Peer)
                .where(
                    Peer.lust_service_id.is_not(None),
                    Peer.is_active.is_(True),
                    Peer.revoked_at.is_(None),
                    Peer.config.is_not(None),
                )
                .order_by(Peer.created_at.desc())
            ).all()
        )
        for peer in peers:
            if peer_id and peer.id != peer_id:
                continue
            if self._extract_existing_token(peer) != normalized:
                continue
            service = db.get(LustService, peer.lust_service_id)
            if service is None or service.state != "active":
                continue
            return peer, service
        return None

    @staticmethod
    def serialize_service(db: Session, service: LustService) -> dict:
        node = db.get(Node, service.node_id)
        peer_count = db.query(Peer).filter(Peer.lust_service_id == service.id, Peer.revoked_at.is_(None)).count()
        return {
            "id": service.id,
            "name": service.name,
            "node_id": service.node_id,
            "node_name": node.name if node is not None else service.node_id,
            "state": service.state,
            "listen_host": service.listen_host,
            "listen_port": service.listen_port,
            "public_host": service.public_host,
            "public_port": service.public_port,
            "tls_server_name": service.tls_server_name,
            "h2_path": service.h2_path,
            "use_tls": service.use_tls,
            "auth_scheme": service.auth_scheme,
            "client_dns_resolver": service.client_dns_resolver,
            "description": service.description,
            "desired_config_json": service.desired_config_json,
            "health_summary_json": service.health_summary_json,
            "last_error_text": service.last_error_text,
            "peer_count": peer_count,
            "created_at": service.created_at,
            "updated_at": service.updated_at,
        }


lust_service_manager = LustServiceManager()
