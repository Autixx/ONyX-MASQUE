from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.device import Device
from onx.db.models.dns_policy import DNSPolicy
from onx.db.models.issued_bundle import IssuedBundle
from onx.db.models.lust_service import LustService
from onx.db.models.node import Node, NodeRole, NodeStatus
from onx.db.models.peer import Peer
from onx.db.models.plan import Plan
from onx.db.models.route_policy import RoutePolicy
from onx.db.models.transport_package import TransportPackage
from onx.db.models.user import User, UserStatus
from onx.db.models.subscription import SubscriptionStatus
from onx.schemas.transport_packages import DEFAULT_TRANSPORT_PRIORITY
from onx.services.client_device_service import client_device_service
from onx.services.device_certificate_service import device_certificate_service
from onx.services.dns_policy_service import DNSPolicyService
from onx.services.lust_access_token_service import lust_access_token_service
from onx.services.lust_service_service import lust_service_manager
from onx.services.subscription_service import subscription_service
from onx.services.transport_package_service import transport_package_service


class BundleService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def issue_for_user_device(
        self,
        db: Session,
        *,
        user: User,
        device: Device,
        destination_country_code: str | None = None,
        candidate_limit: int = 4,
    ) -> IssuedBundle:
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active.")
        subscription = subscription_service.get_active_for_user(
            db,
            user_id=user.id,
            tz_offset_minutes=client_device_service.extract_timezone_offset_minutes(device.metadata_json or {}),
        )
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active subscription.")
        if subscription.status != SubscriptionStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is not active.")
        if subscription.expires_at is not None and subscription.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is expired.")
        client_device_service.assert_recently_verified(device)

        transport_package = transport_package_service.get_or_create_for_user(db, user)
        profiles_check = self._build_runtime_profiles(db, user=user, device=device, transport_package=transport_package)
        if not profiles_check:
            transport_package_service.reconcile_for_user(db, user, transport_package)

        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=self._settings.client_bundle_ttl_seconds)
        payload = self._build_bundle_payload(
            db,
            user=user,
            device=device,
            subscription=subscription,
            issued_at=issued_at,
            expires_at=expires_at,
            destination_country_code=destination_country_code,
            candidate_limit=candidate_limit,
        )
        envelope = client_device_service.encrypt_for_public_key(device.device_public_key, payload)
        bundle_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        bundle = IssuedBundle(
            user_id=user.id,
            device_id=device.id,
            bundle_format_version="1",
            bundle_hash=bundle_hash,
            encrypted_bundle_json=json.dumps(envelope, separators=(",", ":"), ensure_ascii=True),
            metadata_json={
                "destination_country_code": destination_country_code,
                "subscription_id": subscription.id,
                "subscription_expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "profile_type": "lust",
            },
            expires_at=expires_at,
        )
        db.add(bundle)
        db.commit()
        db.refresh(bundle)
        return bundle

    def get_current_for_device(self, db: Session, *, user_id: str, device_id: str) -> IssuedBundle | None:
        now = datetime.now(timezone.utc)
        return db.scalar(
            select(IssuedBundle)
            .where(
                IssuedBundle.user_id == user_id,
                IssuedBundle.device_id == device_id,
                IssuedBundle.invalidated_at.is_(None),
                IssuedBundle.expires_at > now,
            )
            .order_by(IssuedBundle.created_at.desc())
        )

    def _build_bundle_payload(
        self,
        db: Session,
        *,
        user: User,
        device: Device,
        subscription,
        issued_at: datetime,
        expires_at: datetime,
        destination_country_code: str | None,
        candidate_limit: int,
    ) -> dict:
        transport_package = db.scalar(select(TransportPackage).where(TransportPackage.user_id == user.id))
        runtime_profiles = self._build_runtime_profiles(db, user=user, device=device, transport_package=transport_package)
        if runtime_profiles:
            first_profile = runtime_profiles[0]
            transports = [
                {
                    "type": "lust",
                    "priority": 1,
                    "node_id": first_profile["node_id"],
                    "node_name": first_profile["node_name"],
                    "service_id": first_profile["service_id"],
                }
            ]
            candidates = [db.get(Node, first_profile["node_id"])] if first_profile.get("node_id") else []
            candidates = [item for item in candidates if item is not None]
        else:
            candidates = list(
                db.scalars(
                    select(Node)
                    .where(
                        Node.status == NodeStatus.REACHABLE,
                        Node.traffic_suspended_at.is_(None),
                        Node.role.in_([NodeRole.GATEWAY, NodeRole.MIXED]),
                    )
                    .order_by(Node.name.asc())
                ).all()
            )[: max(1, candidate_limit)]
            transports = [
                {
                    "type": "lust",
                    "priority": index + 1,
                    "node_id": node.id,
                    "node_name": node.name,
                    "endpoint": node.management_address,
                }
                for index, node in enumerate(candidates)
            ]

        dns_resolver = self._settings.client_bundle_dns_resolver
        if candidates:
            node_ids = [n.id for n in candidates]
            node_dns_policy = db.scalar(
                select(DNSPolicy)
                .join(RoutePolicy, DNSPolicy.route_policy_id == RoutePolicy.id)
                .where(
                    RoutePolicy.node_id.in_(node_ids),
                    DNSPolicy.enabled.is_(True),
                )
                .order_by(RoutePolicy.node_id)
            )
            if node_dns_policy:
                host, _ = DNSPolicyService.parse_dns_address(node_dns_policy.dns_address)
                dns_resolver = host

        return {
            "bundle_id": f"bundle-{user.id[:8]}-{device.id[:8]}-{int(issued_at.timestamp())}",
            "bundle_format_version": "1",
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "user": {
                "id": user.id,
                "username": user.username,
            },
            "device": {
                "id": device.id,
                "label": device.device_label,
                "platform": device.platform,
            },
            "subscription": {
                "id": subscription.id,
                "plan_id": subscription.plan_id,
                "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "device_limit": subscription.device_limit,
                "speed_limit_kbps": db.get(Plan, subscription.plan_id).speed_limit_kbps if subscription.plan_id else None,
            },
            "dns": {
                "resolver": dns_resolver,
                "force_all": self._settings.client_bundle_dns_force_all,
                "force_doh": self._settings.client_bundle_dns_force_doh,
            },
            "routing": {
                "destination_country_code": destination_country_code,
                "transports": transports,
            },
            "runtime": {
                "profiles": runtime_profiles,
            },
            "transport_package": {
                "enabled_transports": self._enabled_transports(transport_package),
                "priority_order": self._priority_order(transport_package),
                "split_tunnel_enabled": bool(transport_package and transport_package.split_tunnel_enabled),
                "split_tunnel_routes": self._split_tunnel_routes(transport_package),
                "last_reconciled_at": transport_package.last_reconciled_at.isoformat() if transport_package and transport_package.last_reconciled_at else None,
            },
            "policy": {
                "hide_protocol": True,
                "hide_topology": True,
            },
        }

    def _build_runtime_profiles(
        self,
        db: Session,
        *,
        user: User,
        device: Device,
        transport_package: TransportPackage | None = None,
    ) -> list[dict]:
        if transport_package is None:
            transport_package = db.scalar(select(TransportPackage).where(TransportPackage.user_id == user.id))
        split_tunnel_enabled = bool(transport_package and transport_package.split_tunnel_enabled)
        split_tunnel_routes = self._split_tunnel_routes(transport_package)
        profiles: list[dict] = []
        if transport_package is None or not transport_package.lust_enabled:
            return profiles
        peer = self._select_runtime_peer(db, user=user, transport_package=transport_package)
        if peer is None:
            return profiles
        certificate = device_certificate_service.get_current_for_device(db, device_id=device.id)
        if certificate is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device has no active LuST certificate. Issue a device certificate before requesting a bundle.",
            )
        node = db.get(Node, peer.node_id)
        if node is None or node.status != NodeStatus.REACHABLE or node.traffic_suspended_at is not None:
            return profiles
        service = db.get(LustService, peer.lust_service_id)
        if service is None or service.state != "active":
            return profiles
        token = lust_access_token_service.issue_token(
            user_id=user.id,
            device_id=device.id,
            peer_id=peer.id,
            service_id=service.id,
            node_id=service.node_id,
            cert_fingerprint_sha256=certificate.fingerprint_sha256,
        )
        runtime_config = lust_service_manager.render_runtime_profile(
            service,
            peer,
            token=token,
            certificate=certificate,
            ca_certificate_pem=device_certificate_service.ca_certificate_pem(),
        )
        profiles.append(
            {
                "id": f"profile-{peer.id}",
                "type": "lust",
                "priority": 1,
                "peer_id": peer.id,
                "service_id": peer.lust_service_id,
                "node_id": node.id,
                "node_name": node.name,
                "expires_at": peer.config_expires_at.isoformat() if peer.config_expires_at else None,
                "config": json.dumps(runtime_config, separators=(",", ":"), ensure_ascii=True),
                "metadata": {
                    "split_tunnel_enabled": split_tunnel_enabled and bool(split_tunnel_routes),
                    "split_tunnel_routes": list(split_tunnel_routes),
                    "mtls_required": True,
                    "certificate_fingerprint_sha256": certificate.fingerprint_sha256,
                },
            }
        )
        return profiles

    @staticmethod
    def detect_transport_type(config_text: str) -> str | None:
        try:
            parsed = json.loads(config_text)
        except json.JSONDecodeError:
            return None
        return "lust" if isinstance(parsed, dict) and parsed.get("type") == "lust" else None

    @staticmethod
    def _enabled_transports(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None:
            return ["lust"]
        return ["lust"] if transport_package.lust_enabled else []

    @staticmethod
    def _priority_order(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None or not transport_package.lust_enabled:
            return list(DEFAULT_TRANSPORT_PRIORITY)
        return ["lust"]

    @staticmethod
    def _split_tunnel_routes(transport_package: TransportPackage | None) -> list[str]:
        if transport_package is None:
            return []
        out: list[str] = []
        for item in transport_package.split_tunnel_routes_json or []:
            value = str(item or "").strip()
            if value and value not in out:
                out.append(value)
        return out

    def _select_runtime_peer(self, db: Session, *, user: User, transport_package: TransportPackage | None) -> Peer | None:
        service = self._select_lust_service(db, transport_package)
        if service is None:
            return None
        return self._select_peer_for_service(db, user=user, service_field=Peer.lust_service_id, service_id=service.id)

    @staticmethod
    def _select_peer_for_service(db: Session, *, user: User, service_field, service_id: str) -> Peer | None:
        return db.scalar(
            select(Peer)
            .where(
                service_field == service_id,
                Peer.is_active.is_(True),
                Peer.revoked_at.is_(None),
                Peer.config.is_not(None),
                or_(Peer.username == user.username, Peer.email == user.email),
            )
            .order_by(Peer.created_at.desc())
        )

    @staticmethod
    def _node_is_reachable(db: Session, node_id: str) -> bool:
        node = db.get(Node, node_id)
        return node is not None and node.status == NodeStatus.REACHABLE and node.traffic_suspended_at is None

    def _select_lust_service(self, db: Session, transport_package: TransportPackage | None) -> LustService | None:
        if transport_package and transport_package.preferred_lust_service_id:
            preferred = db.get(LustService, transport_package.preferred_lust_service_id)
            if preferred is not None and preferred.state == "active" and self._node_is_reachable(db, preferred.node_id):
                return preferred
        services = list(
            db.scalars(select(LustService).where(LustService.state == "active").order_by(LustService.updated_at.desc())).all()
        )
        for service in services:
            if self._node_is_reachable(db, service.node_id):
                return service
        return None


bundle_service = BundleService()
