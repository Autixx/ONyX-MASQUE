from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onx.db.models.lust_service import LustService
from onx.db.models.node import Node, NodeStatus
from onx.db.models.peer import Peer
from onx.db.models.subscription import Subscription, SubscriptionStatus
from onx.db.models.transport_package import TransportPackage
from onx.db.models.user import User, UserStatus
from onx.schemas.transport_packages import DEFAULT_TRANSPORT_PRIORITY
from onx.services.geoip_service import compute_excluded_allowed_ips
from onx.services.lust_service_service import lust_service_manager


class TransportPackageService:
    def list_packages(self, db: Session) -> list[TransportPackage]:
        return list(db.scalars(select(TransportPackage).order_by(TransportPackage.created_at.desc())).all())

    def get_by_user(self, db: Session, user_id: str) -> TransportPackage | None:
        return db.scalar(select(TransportPackage).where(TransportPackage.user_id == user_id))

    def get_or_create_for_user(self, db: Session, user: User) -> TransportPackage:
        package = self.get_by_user(db, user.id)
        if package is not None:
            return package
        package = TransportPackage(
            user_id=user.id,
            lust_enabled=True,
            priority_order_json=list(DEFAULT_TRANSPORT_PRIORITY),
        )
        db.add(package)
        db.commit()
        db.refresh(package)
        return package

    def upsert_for_user(self, db: Session, user: User, payload) -> TransportPackage:
        package = self.get_or_create_for_user(db, user)
        package.preferred_lust_service_id = payload.preferred_lust_service_id
        package.lust_enabled = payload.lust_enabled
        package.split_tunnel_enabled = payload.split_tunnel_enabled
        country_code = (payload.split_tunnel_country_code or "").strip().lower() or None
        package.split_tunnel_country_code = country_code
        if package.split_tunnel_enabled and country_code:
            try:
                package.split_tunnel_routes_json = compute_excluded_allowed_ips(country_code)
            except Exception:
                package.split_tunnel_routes_json = self._normalize_routes(payload.split_tunnel_routes)
        else:
            package.split_tunnel_routes_json = self._normalize_routes(payload.split_tunnel_routes)
        package.priority_order_json = list(DEFAULT_TRANSPORT_PRIORITY)
        db.add(package)
        db.commit()
        db.refresh(package)
        return package

    def reconcile_for_user(self, db: Session, user: User, package: TransportPackage) -> dict:
        now = datetime.now(timezone.utc)
        summary: dict = {
            "user_id": user.id,
            "username": user.username,
            "reconciled_at": now.isoformat(),
            "profile_type": "lust",
            "enabled_transports": self.enabled_transport_types(package),
        }
        subscription = db.scalar(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        summary["subscription"] = {
            "active": subscription is not None,
            "subscription_id": subscription.id if subscription is not None else None,
            "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None,
        }
        if user.status != UserStatus.ACTIVE:
            summary["status"] = "user_not_active"
            return self._store_summary(db, package, now, summary)
        if not package.lust_enabled:
            summary["status"] = "disabled"
            return self._store_summary(db, package, now, summary)
        if subscription is None:
            summary["status"] = "no_active_subscription"
            return self._store_summary(db, package, now, summary)

        service = self._select_lust_service(db, package)
        if service is None:
            summary["status"] = "missing_service"
            return self._store_summary(db, package, now, summary)

        peer = self._select_lust_peer(db, user, service.id)
        if peer is None:
            peer = Peer(
                username=user.username,
                email=user.email,
                node_id=service.node_id,
                config_expires_at=subscription.expires_at if subscription is not None else None,
            )
        else:
            peer.node_id = service.node_id
            peer.config_expires_at = subscription.expires_at
        result = lust_service_manager.assign_peer(db, service, peer, save_to_peer=True)
        summary["status"] = "ready"
        summary["service_id"] = service.id
        summary["peer_id"] = result["peer_id"]
        summary["node_id"] = service.node_id
        summary["split_tunnel_enabled"] = bool(package.split_tunnel_enabled)
        summary["split_tunnel_routes"] = list(package.split_tunnel_routes_json or [])
        return self._store_summary(db, package, now, summary)

    @staticmethod
    def enabled_transport_types(package: TransportPackage) -> list[str]:
        return ["lust"] if package.lust_enabled else []

    @staticmethod
    def _normalize_routes(value: list[str] | None) -> list[str]:
        routes: list[str] = []
        for item in value or []:
            normalized = str(item or "").strip()
            if normalized and normalized not in routes:
                routes.append(normalized)
        return routes

    @staticmethod
    def _store_summary(db: Session, package: TransportPackage, now: datetime, summary: dict) -> dict:
        package.last_reconciled_at = now
        package.last_reconcile_summary_json = summary
        db.add(package)
        db.commit()
        db.refresh(package)
        return summary

    @staticmethod
    def _select_lust_service(db: Session, package: TransportPackage) -> LustService | None:
        if package.preferred_lust_service_id:
            preferred = db.get(LustService, package.preferred_lust_service_id)
            if preferred is not None and preferred.state == "active":
                node = db.get(Node, preferred.node_id)
                if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                    return preferred
        services = list(
            db.scalars(
                select(LustService).where(LustService.state == "active").order_by(LustService.updated_at.desc())
            ).all()
        )
        for service in services:
            node = db.get(Node, service.node_id)
            if node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None:
                return service
        return None

    @staticmethod
    def _select_lust_peer(db: Session, user: User, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                Peer.lust_service_id == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )


transport_package_service = TransportPackageService()
