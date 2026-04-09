from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.lust_egress_pool import LustEgressPool
from onx.db.models.lust_gateway_route_map import LustGatewayRouteMap
from onx.db.models.lust_service import LustService
from onx.db.models.node import Node, NodeStatus


class LustRoutingService:
    _VALID_SERVICE_ROLES = {"standalone", "gate", "egress"}
    _VALID_POOL_STRATEGIES = {"hash", "ordered"}

    def list_egress_pools(self, db: Session) -> list[LustEgressPool]:
        return list(db.scalars(select(LustEgressPool).order_by(LustEgressPool.created_at.desc())).all())

    def get_egress_pool(self, db: Session, pool_id: str) -> LustEgressPool | None:
        return db.get(LustEgressPool, pool_id)

    def create_egress_pool(self, db: Session, payload) -> LustEgressPool:
        existing = db.scalar(select(LustEgressPool).where(LustEgressPool.name == payload.name))
        if existing is not None:
            raise ValueError("LuST egress pool with this name already exists.")
        pool = LustEgressPool(
            name=payload.name,
            enabled=bool(payload.enabled),
            selection_strategy=self._normalize_strategy(payload.selection_strategy),
            members_json=self._normalize_members(db, payload.members_json),
            description=payload.description,
        )
        db.add(pool)
        db.commit()
        db.refresh(pool)
        return pool

    def update_egress_pool(self, db: Session, pool: LustEgressPool, payload) -> LustEgressPool:
        dumped = payload.model_dump(exclude_unset=True)
        if "name" in dumped and dumped["name"] and dumped["name"] != pool.name:
            existing = db.scalar(select(LustEgressPool).where(LustEgressPool.name == dumped["name"]))
            if existing is not None and existing.id != pool.id:
                raise ValueError("LuST egress pool with this name already exists.")
        for field_name, value in dumped.items():
            if field_name == "selection_strategy":
                value = self._normalize_strategy(value)
            elif field_name == "members_json":
                value = self._normalize_members(db, value)
            setattr(pool, field_name, value)
        db.add(pool)
        db.commit()
        db.refresh(pool)
        return pool

    def delete_egress_pool(self, db: Session, pool: LustEgressPool) -> None:
        db.delete(pool)
        db.commit()

    def list_route_maps(self, db: Session, *, gateway_service_id: str | None = None) -> list[LustGatewayRouteMap]:
        query = select(LustGatewayRouteMap).order_by(LustGatewayRouteMap.priority.asc(), LustGatewayRouteMap.created_at.desc())
        if gateway_service_id:
            query = query.where(LustGatewayRouteMap.gateway_service_id == gateway_service_id)
        return list(db.scalars(query).all())

    def get_route_map(self, db: Session, route_map_id: str) -> LustGatewayRouteMap | None:
        return db.get(LustGatewayRouteMap, route_map_id)

    def create_route_map(self, db: Session, payload) -> LustGatewayRouteMap:
        existing = db.scalar(select(LustGatewayRouteMap).where(LustGatewayRouteMap.name == payload.name))
        if existing is not None:
            raise ValueError("LuST gateway route map with this name already exists.")
        gateway_service = self._require_gateway_service(db, payload.gateway_service_id)
        pool = self._require_egress_pool(db, payload.egress_pool_id)
        route_map = LustGatewayRouteMap(
            name=payload.name,
            enabled=bool(payload.enabled),
            gateway_service_id=gateway_service.id,
            egress_pool_id=pool.id,
            priority=int(payload.priority),
            destination_country_code=self._normalize_country(payload.destination_country_code),
            description=payload.description,
        )
        db.add(route_map)
        db.commit()
        db.refresh(route_map)
        return route_map

    def update_route_map(self, db: Session, route_map: LustGatewayRouteMap, payload) -> LustGatewayRouteMap:
        dumped = payload.model_dump(exclude_unset=True)
        if "name" in dumped and dumped["name"] and dumped["name"] != route_map.name:
            existing = db.scalar(select(LustGatewayRouteMap).where(LustGatewayRouteMap.name == dumped["name"]))
            if existing is not None and existing.id != route_map.id:
                raise ValueError("LuST gateway route map with this name already exists.")
        if "gateway_service_id" in dumped and dumped["gateway_service_id"]:
            self._require_gateway_service(db, dumped["gateway_service_id"])
        if "egress_pool_id" in dumped and dumped["egress_pool_id"]:
            self._require_egress_pool(db, dumped["egress_pool_id"])
        for field_name, value in dumped.items():
            if field_name == "destination_country_code":
                value = self._normalize_country(value)
            setattr(route_map, field_name, value)
        db.add(route_map)
        db.commit()
        db.refresh(route_map)
        return route_map

    def delete_route_map(self, db: Session, route_map: LustGatewayRouteMap) -> None:
        db.delete(route_map)
        db.commit()

    def resolve_gateway_candidates(
        self,
        db: Session,
        gateway_service: LustService,
        *,
        destination_country_code: str | None = None,
    ) -> list[dict[str, Any]]:
        route_maps = [
            item
            for item in self.list_route_maps(db, gateway_service_id=gateway_service.id)
            if item.enabled and self._country_matches(item.destination_country_code, destination_country_code)
        ]
        route_maps.sort(key=lambda item: (item.priority, item.created_at))
        resolved: list[dict[str, Any]] = []
        for route_map in route_maps:
            pool = db.get(LustEgressPool, route_map.egress_pool_id)
            if pool is None or not pool.enabled:
                continue
            members = self._resolve_pool_members(db, pool)
            if not members:
                continue
            resolved.append(
                {
                    "route_map_id": route_map.id,
                    "route_map_name": route_map.name,
                    "priority": route_map.priority,
                    "destination_country_code": route_map.destination_country_code,
                    "egress_pool_id": pool.id,
                    "egress_pool_name": pool.name,
                    "selection_strategy": pool.selection_strategy,
                    "members": members,
                }
            )
        return resolved

    def select_egress_member(
        self,
        db: Session,
        gateway_service: LustService,
        *,
        destination_country_code: str | None = None,
        stable_hint: str | None = None,
    ) -> dict[str, Any] | None:
        candidates = self.resolve_gateway_candidates(db, gateway_service, destination_country_code=destination_country_code)
        if not candidates:
            return None
        selected_map = candidates[0]
        members = list(selected_map["members"])
        strategy = str(selected_map.get("selection_strategy") or "hash").strip().lower()
        if not members:
            return None
        if strategy == "ordered":
            return members[0]
        hint = str(stable_hint or gateway_service.id).strip() or gateway_service.id
        total_weight = sum(max(1, int(item.get("weight") or 1)) for item in members)
        bucket = int(hashlib.sha256(hint.encode("utf-8")).hexdigest(), 16) % total_weight
        cursor = 0
        for member in members:
            cursor += max(1, int(member.get("weight") or 1))
            if bucket < cursor:
                return member
        return members[0]

    def build_gateway_runtime_config(self, db: Session, gateway_service: LustService) -> dict[str, Any]:
        return {
            "gateway_service_id": gateway_service.id,
            "route_maps": self.resolve_gateway_candidates(db, gateway_service),
        }

    def normalize_peer_route_override(
        self,
        db: Session,
        *,
        gateway_service_id: str | None,
        override: dict[str, Any] | None,
    ) -> dict[str, str]:
        raw = dict(override or {})
        normalized = {
            "route_map_id": str(raw.get("route_map_id") or "").strip(),
            "egress_pool_id": str(raw.get("egress_pool_id") or "").strip(),
            "egress_service_id": str(raw.get("egress_service_id") or "").strip(),
        }
        normalized = {key: value for key, value in normalized.items() if value}
        if not normalized:
            return {}
        if not gateway_service_id:
            raise ValueError("LuST route override requires a gateway service on the peer.")

        gateway_service = self._require_gateway_service(db, gateway_service_id)
        route_maps = self.resolve_gateway_candidates(db, gateway_service)
        if not route_maps:
            raise ValueError("Selected LuST gateway service does not have any active route maps.")

        route_map_id = normalized.get("route_map_id")
        egress_pool_id = normalized.get("egress_pool_id")
        egress_service_id = normalized.get("egress_service_id")

        if route_map_id:
            selected_map = next((item for item in route_maps if str(item.get("route_map_id") or "") == route_map_id), None)
            if selected_map is None:
                raise ValueError("LuST route override route_map_id does not belong to the selected gateway service.")
            if egress_pool_id and str(selected_map.get("egress_pool_id") or "") != egress_pool_id:
                raise ValueError("LuST route override egress_pool_id does not match the selected route map.")
            egress_pool_id = str(selected_map.get("egress_pool_id") or "") or egress_pool_id
            candidate_maps = [selected_map]
        elif egress_pool_id:
            candidate_maps = [item for item in route_maps if str(item.get("egress_pool_id") or "") == egress_pool_id]
            if not candidate_maps:
                raise ValueError("LuST route override egress_pool_id is not reachable from the selected gateway service.")
        else:
            candidate_maps = list(route_maps)

        if egress_service_id:
            service = db.get(LustService, egress_service_id)
            if service is None or str(service.role or "").strip().lower() != "egress":
                raise ValueError("LuST route override egress_service_id must point to an existing egress service.")
            if bool(service.maintenance_mode):
                raise ValueError("LuST route override egress_service_id is currently in maintenance mode.")
            member_found = any(
                str(member.get("service_id") or "") == egress_service_id
                for route_map in candidate_maps
                for member in list(route_map.get("members") or [])
            )
            if not member_found:
                raise ValueError("LuST route override egress_service_id is not available through the selected gateway route.")

        out: dict[str, str] = {}
        if route_map_id:
            out["route_map_id"] = route_map_id
        if egress_pool_id:
            out["egress_pool_id"] = egress_pool_id
        if egress_service_id:
            out["egress_service_id"] = egress_service_id
        return out

    def serialize_egress_pool(self, db: Session, pool: LustEgressPool) -> dict[str, Any]:
        return {
            "id": pool.id,
            "name": pool.name,
            "enabled": bool(pool.enabled),
            "selection_strategy": pool.selection_strategy,
            "members_json": list(pool.members_json or []),
            "description": pool.description,
            "resolved_members": self._resolve_pool_members(db, pool),
            "created_at": pool.created_at,
            "updated_at": pool.updated_at,
        }

    def serialize_route_map(self, db: Session, route_map: LustGatewayRouteMap) -> dict[str, Any]:
        gateway_service = db.get(LustService, route_map.gateway_service_id)
        pool = db.get(LustEgressPool, route_map.egress_pool_id)
        return {
            "id": route_map.id,
            "name": route_map.name,
            "enabled": bool(route_map.enabled),
            "gateway_service_id": route_map.gateway_service_id,
            "gateway_service_name": gateway_service.name if gateway_service is not None else None,
            "egress_pool_id": route_map.egress_pool_id,
            "egress_pool_name": pool.name if pool is not None else None,
            "priority": route_map.priority,
            "destination_country_code": route_map.destination_country_code,
            "description": route_map.description,
            "created_at": route_map.created_at,
            "updated_at": route_map.updated_at,
        }

    def _require_gateway_service(self, db: Session, service_id: str) -> LustService:
        service = db.get(LustService, service_id)
        if service is None:
            raise ValueError("LuST gateway service not found.")
        if str(service.role or "standalone").strip().lower() not in {"gate", "standalone"}:
            raise ValueError("Gateway route map can only target LuST gate or standalone services.")
        return service

    def _require_egress_pool(self, db: Session, pool_id: str) -> LustEgressPool:
        pool = db.get(LustEgressPool, pool_id)
        if pool is None:
            raise ValueError("LuST egress pool not found.")
        return pool

    def _normalize_members(self, db: Session, members: list[Any] | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(members or []):
            payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            service_id = str(payload.get("service_id") or "").strip()
            if not service_id or service_id in seen:
                continue
            service = db.get(LustService, service_id)
            if service is None:
                raise ValueError(f"LuST egress service '{service_id}' not found.")
            if str(service.role or "standalone").strip().lower() not in self._VALID_SERVICE_ROLES:
                raise ValueError(f"LuST service '{service.name}' has an invalid role.")
            if str(service.role or "standalone").strip().lower() != "egress":
                raise ValueError(f"LuST service '{service.name}' is not an egress service.")
            weight = max(1, int(payload.get("weight") or service.selection_weight or 100))
            out.append({"service_id": service_id, "weight": weight})
            seen.add(service_id)
        return out

    def _resolve_pool_members(self, db: Session, pool: LustEgressPool) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        for item in list(pool.members_json or []):
            service_id = str(dict(item).get("service_id") or "").strip()
            if not service_id:
                continue
            service = db.get(LustService, service_id)
            if service is None or str(service.role or "").strip().lower() != "egress":
                continue
            if bool(service.maintenance_mode):
                continue
            node = db.get(Node, service.node_id)
            if node is None or node.status != NodeStatus.REACHABLE or node.traffic_suspended_at is not None:
                continue
            if service.state != "active":
                continue
            members.append(
                {
                    "service_id": service.id,
                    "service_name": service.name,
                    "node_id": service.node_id,
                    "node_name": node.name,
                    "host": service.public_host,
                    "port": service.public_port or service.listen_port,
                    "tls_server_name": service.tls_server_name or service.public_host,
                    "h2_path": service.h2_path,
                    "country_code": service.country_code,
                    "weight": max(1, int(dict(item).get("weight") or service.selection_weight or 100)),
                }
            )
        return members

    @classmethod
    def _normalize_strategy(cls, value: str | None) -> str:
        normalized = str(value or "hash").strip().lower() or "hash"
        if normalized not in cls._VALID_POOL_STRATEGIES:
            raise ValueError("selection_strategy must be one of: hash, ordered.")
        return normalized

    @staticmethod
    def _normalize_country(value: str | None) -> str | None:
        normalized = str(value or "").strip().upper()
        return normalized or None

    @staticmethod
    def _country_matches(route_country: str | None, requested_country: str | None) -> bool:
        if not route_country:
            return True
        return route_country == str(requested_country or "").strip().upper()


lust_routing_service = LustRoutingService()
