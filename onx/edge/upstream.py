from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from onx.edge.config import EdgeRuntimeConfig
from onx.edge.runtime import EdgeSession


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class UpstreamGatewayRelay:
    def __init__(self, config: EdgeRuntimeConfig) -> None:
        self._config = config

    def enabled(self) -> bool:
        return str(self._config.service.role or "").strip().lower() == "gate" and bool((self._config.routing or {}).get("route_maps"))

    async def attach_session(self, session: EdgeSession) -> dict[str, Any] | None:
        candidates = self._candidate_members(session)
        if not candidates:
            return None
        last_error: Exception | None = None
        for member in candidates:
            try:
                token = self._issue_upstream_token(session, member)
                base_url = self._member_base_url(member)
                open_path = self._member_path(member, "/upstream/session/open")
                async with httpx.AsyncClient(http2=True, verify=True, timeout=15.0) as client:
                    response = await client.post(
                        f"{base_url}{open_path}",
                        headers=self._headers(token),
                        json={},
                    )
                    response.raise_for_status()
                    payload = response.json()
                upstream = {
                    "member": member,
                    "token": token,
                    "session_id": str(payload.get("session_id") or "").strip(),
                    "base_url": base_url,
                }
                if not upstream["session_id"]:
                    raise RuntimeError("Upstream LuST session did not return session_id.")
                session.metadata["upstream"] = upstream
                return upstream
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if last_error is not None:
            raise RuntimeError(f"No LuST egress could accept the upstream session: {last_error}") from last_error
        return None

    async def forward_frame(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        upstream = self._require_upstream(session)
        payload = dict(frame)
        payload["session_id"] = upstream["session_id"]
        async with httpx.AsyncClient(http2=True, verify=True, timeout=30.0) as client:
            response = await client.post(
                f"{upstream['base_url']}{self._member_path(upstream['member'], '/upstream/frame')}",
                headers=self._headers(upstream["token"]),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def poll_frame(self, session: EdgeSession, *, timeout: float) -> dict[str, Any] | None:
        upstream = self._require_upstream(session)
        async with httpx.AsyncClient(http2=True, verify=True, timeout=max(10.0, timeout + 10.0)) as client:
            response = await client.get(
                f"{upstream['base_url']}{self._member_path(upstream['member'], '/upstream/frame/poll')}",
                headers=self._headers(upstream["token"]),
                params={"session_id": upstream["session_id"], "timeout": timeout},
            )
            if response.status_code == 204:
                return None
            response.raise_for_status()
            return response.json()

    async def close_session(self, session: EdgeSession) -> None:
        upstream = session.metadata.get("upstream")
        if not isinstance(upstream, dict) or not upstream.get("session_id"):
            return
        async with httpx.AsyncClient(http2=True, verify=True, timeout=15.0) as client:
            response = await client.post(
                f"{upstream['base_url']}{self._member_path(upstream['member'], '/upstream/session/close')}",
                headers=self._headers(upstream["token"]),
                json={"session_id": upstream["session_id"]},
            )
            if response.status_code not in {200, 204, 404}:
                response.raise_for_status()

    def _candidate_members(self, session: EdgeSession) -> list[dict[str, Any]]:
        route_maps = list((self._config.routing or {}).get("route_maps") or [])
        if not route_maps:
            return []
        forced_route_map_id = str(session.claims.get("forced_route_map_id") or "").strip()
        forced_egress_pool_id = str(session.claims.get("forced_egress_pool_id") or "").strip()
        forced_egress_service_id = str(session.claims.get("forced_egress_service_id") or "").strip()

        if forced_route_map_id:
            route_maps = [item for item in route_maps if str(item.get("route_map_id") or "").strip() == forced_route_map_id]
            if not route_maps:
                raise RuntimeError(f"Forced LuST route map '{forced_route_map_id}' is not available on this gateway.")

        if forced_egress_pool_id:
            route_maps = [item for item in route_maps if str(item.get("egress_pool_id") or "").strip() == forced_egress_pool_id]
            if not route_maps:
                raise RuntimeError(f"Forced LuST egress pool '{forced_egress_pool_id}' is not available on this gateway.")

        selected = route_maps[0]
        members = list(selected.get("members") or [])
        if not members:
            return []
        if forced_egress_service_id:
            members = [item for item in members if str(item.get("service_id") or "").strip() == forced_egress_service_id]
            if not members:
                raise RuntimeError(
                    f"Forced LuST egress service '{forced_egress_service_id}' is not available in the selected route."
                )
        strategy = str(selected.get("selection_strategy") or "hash").strip().lower()
        if strategy == "ordered":
            return members
        hint = "|".join(
            str(session.claims.get(key) or "")
            for key in ("device_id", "user_id", "peer_id")
        ).strip("|") or session.session_id
        total_weight = sum(max(1, int(item.get("weight") or 1)) for item in members)
        bucket = int(hashlib.sha256(hint.encode("utf-8")).hexdigest(), 16) % total_weight
        cursor = 0
        ordered: list[dict[str, Any]] = []
        for member in members:
            cursor += max(1, int(member.get("weight") or 1))
            if bucket < cursor:
                ordered.append(member)
                break
        for member in members:
            if member not in ordered:
                ordered.append(member)
        return ordered

    def _issue_upstream_token(self, session: EdgeSession, member: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iss": self._config.trust.token_issuer,
            "aud": self._config.trust.upstream_token_audience,
            "typ": "lust_upstream",
            "ver": 1,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=120)).timestamp()),
            "gateway_service_id": self._config.service.id,
            "gateway_node_id": self._config.service.node_id,
            "target_service_id": str(member.get("service_id") or ""),
            "user_id": str(session.claims.get("user_id") or ""),
            "device_id": str(session.claims.get("device_id") or ""),
            "peer_id": str(session.claims.get("peer_id") or ""),
        }
        header = {"alg": "HS256", "typ": "JWT"}
        segments = [
            _b64encode(json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8")),
            _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")),
        ]
        signing_input = ".".join(segments).encode("ascii")
        signature = hmac.new(self._config.access_token_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        segments.append(_b64encode(signature))
        return ".".join(segments)

    @staticmethod
    def _member_base_url(member: dict[str, Any]) -> str:
        host = str(member.get("host") or "").strip()
        port = int(member.get("port") or 443)
        return f"https://{host}:{port}"

    @staticmethod
    def _member_path(member: dict[str, Any], suffix: str) -> str:
        base = str(member.get("h2_path") or "/lust").rstrip("/")
        if not base.startswith("/"):
            base = "/" + base
        return base + suffix

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": "ONyX-LuST-Gateway/0.1",
        }

    @staticmethod
    def _require_upstream(session: EdgeSession) -> dict[str, Any]:
        upstream = session.metadata.get("upstream")
        if not isinstance(upstream, dict) or not upstream.get("session_id"):
            raise RuntimeError("LuST session is not bound to an upstream egress.")
        return upstream
