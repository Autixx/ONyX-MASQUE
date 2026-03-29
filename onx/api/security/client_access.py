from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import secrets
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status

from onx.core.config import get_settings


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass
class _BucketState:
    tokens: float
    updated_at: float
    last_seen: float


class InMemoryTokenBucketLimiter:
    def __init__(self, *, cleanup_interval_seconds: int = 300) -> None:
        self._cleanup_interval_seconds = max(30, int(cleanup_interval_seconds))
        self._buckets: dict[str, _BucketState] = {}
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    def consume(
        self,
        key: str,
        *,
        rate_per_minute: float,
        burst: int,
        tokens: float = 1.0,
    ) -> tuple[bool, int]:
        if rate_per_minute <= 0 or burst <= 0:
            return True, 0

        now = time.monotonic()
        refill_per_sec = rate_per_minute / 60.0
        capacity = float(burst)
        wanted = max(tokens, 0.0)

        with self._lock:
            self._cleanup(now)
            state = self._buckets.get(key)
            if state is None:
                state = _BucketState(tokens=capacity, updated_at=now, last_seen=now)
                self._buckets[key] = state
            else:
                elapsed = max(0.0, now - state.updated_at)
                state.tokens = min(capacity, state.tokens + elapsed * refill_per_sec)
                state.updated_at = now
                state.last_seen = now

            if state.tokens >= wanted:
                state.tokens -= wanted
                return True, 0

            deficit = wanted - state.tokens
            if refill_per_sec <= 0:
                retry_after = 60
            else:
                retry_after = int(math.ceil(deficit / refill_per_sec))
            return False, max(retry_after, 1)

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._cleanup_interval_seconds:
            return
        stale_after = max(self._cleanup_interval_seconds * 2, 600)
        stale_keys = [
            key
            for key, state in self._buckets.items()
            if (now - state.last_seen) > stale_after
        ]
        for key in stale_keys:
            self._buckets.pop(key, None)
        self._last_cleanup = now


class ClientAccessControl:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._limiter = InMemoryTokenBucketLimiter(
            cleanup_interval_seconds=self._settings.client_rate_limit_cleanup_interval_seconds,
        )
        self._rebind_lock = Lock()
        self._last_rebind_by_session: dict[str, float] = {}

    def require_auth(self, request: Request) -> None:
        mode = self._settings.client_api_auth_mode.strip().lower()
        if mode in {"", "disabled", "off", "none"}:
            return

        token = self._extract_bearer_token(request)
        if token is None:
            self._unauthorized("Missing bearer token.")

        if mode == "token":
            self._require_static_token(token)
            return
        if mode == "jwt":
            self._require_jwt(token)
            return
        if mode == "token_or_jwt":
            if self._validate_static_token(token):
                return
            self._require_jwt(token)
            return

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unsupported auth mode '{self._settings.client_api_auth_mode}'.",
        )

    def enforce_bootstrap_limits(self, request: Request, *, device_id: str) -> None:
        if not self._settings.client_rate_limit_enabled:
            return
        ip = self._client_ip(request)
        self._consume_or_raise(
            key=f"bootstrap:ip:{ip}",
            rate=self._settings.client_rl_bootstrap_ip_rate_per_minute,
            burst=self._settings.client_rl_bootstrap_ip_burst,
        )
        self._consume_or_raise(
            key=f"bootstrap:device:{device_id}",
            rate=self._settings.client_rl_bootstrap_device_rate_per_minute,
            burst=self._settings.client_rl_bootstrap_device_burst,
        )

    def enforce_probe_limits(self, request: Request, *, session_id: str) -> None:
        self._enforce_ip_and_subject_limits(
            request,
            endpoint="probe",
            subject=f"session:{session_id}",
            subject_rate=self._settings.client_rl_probe_session_rate_per_minute,
            subject_burst=self._settings.client_rl_probe_session_burst,
        )

    def enforce_best_ingress_limits(self, request: Request, *, session_id: str) -> None:
        self._enforce_ip_and_subject_limits(
            request,
            endpoint="best-ingress",
            subject=f"session:{session_id}",
            subject_rate=self._settings.client_rl_best_session_rate_per_minute,
            subject_burst=self._settings.client_rl_best_session_burst,
        )

    def enforce_rebind_limits(self, request: Request, *, session_id: str) -> None:
        self._enforce_ip_and_subject_limits(
            request,
            endpoint="session-rebind",
            subject=f"session:{session_id}",
            subject_rate=self._settings.client_rl_rebind_session_rate_per_minute,
            subject_burst=self._settings.client_rl_rebind_session_burst,
        )
        cooldown = max(0, int(self._settings.client_rl_rebind_cooldown_seconds))
        if cooldown <= 0:
            return

        now = time.monotonic()
        with self._rebind_lock:
            last = self._last_rebind_by_session.get(session_id)
            if last is not None:
                elapsed = now - last
                if elapsed < cooldown:
                    retry_after = int(math.ceil(cooldown - elapsed))
                    self._rate_limited(
                        f"Rebind cooldown is active for session '{session_id}'.",
                        retry_after=retry_after,
                    )
            self._last_rebind_by_session[session_id] = now

    def _enforce_ip_and_subject_limits(
        self,
        request: Request,
        *,
        endpoint: str,
        subject: str,
        subject_rate: float,
        subject_burst: int,
    ) -> None:
        if not self._settings.client_rate_limit_enabled:
            return
        ip = self._client_ip(request)
        self._consume_or_raise(
            key=f"{endpoint}:ip:{ip}",
            rate=self._settings.client_rl_common_ip_rate_per_minute,
            burst=self._settings.client_rl_common_ip_burst,
        )
        self._consume_or_raise(
            key=f"{endpoint}:{subject}",
            rate=subject_rate,
            burst=subject_burst,
        )

    def _consume_or_raise(self, *, key: str, rate: float, burst: int) -> None:
        allowed, retry_after = self._limiter.consume(
            key,
            rate_per_minute=rate,
            burst=burst,
            tokens=1.0,
        )
        if not allowed:
            self._rate_limited("Rate limit exceeded.", retry_after=retry_after)

    def _require_static_token(self, token: str) -> None:
        if not self._validate_static_token(token):
            self._unauthorized("Invalid bearer token.")

    def _validate_static_token(self, token: str) -> bool:
        configured = [
            item.strip()
            for item in self._settings.client_api_tokens.split(",")
            if item.strip()
        ]
        if not configured:
            return False
        return any(secrets.compare_digest(item, token) for item in configured)

    def _require_jwt(self, token: str) -> None:
        try:
            self._validate_jwt_hs256(token)
        except ValueError as exc:
            self._unauthorized(str(exc))

    def _validate_jwt_hs256(self, token: str) -> dict:
        secret_value = self._settings.client_api_jwt_secret
        if len(secret_value.strip()) == 0:
            raise ValueError("JWT auth is enabled but secret is not configured.")

        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("JWT format is invalid.")
        header_b64, payload_b64, signature_b64 = parts

        try:
            header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
            signature = _b64url_decode(signature_b64)
        except Exception as exc:
            raise ValueError("JWT decode failed.") from exc

        alg = str(header.get("alg") or "")
        if alg != "HS256":
            raise ValueError("Unsupported JWT algorithm. Only HS256 is allowed.")

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected = hmac.new(
            secret_value.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("JWT signature validation failed.")

        now = int(time.time())
        leeway = max(0, int(self._settings.client_api_jwt_leeway_seconds))

        if self._settings.client_api_jwt_require_exp:
            exp = payload.get("exp")
            if exp is None:
                raise ValueError("JWT exp claim is required.")
            try:
                exp_i = int(exp)
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT exp claim is invalid.") from exc
            if exp_i < now - leeway:
                raise ValueError("JWT token is expired.")

        if payload.get("nbf") is not None:
            try:
                nbf_i = int(payload["nbf"])
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT nbf claim is invalid.") from exc
            if nbf_i > now + leeway:
                raise ValueError("JWT token is not active yet.")

        if payload.get("iat") is not None:
            try:
                iat_i = int(payload["iat"])
            except (TypeError, ValueError) as exc:
                raise ValueError("JWT iat claim is invalid.") from exc
            if iat_i > now + leeway:
                raise ValueError("JWT iat claim is in the future.")

        expected_issuer = self._settings.client_api_jwt_issuer.strip()
        if expected_issuer:
            if str(payload.get("iss") or "") != expected_issuer:
                raise ValueError("JWT issuer mismatch.")

        expected_audience = self._settings.client_api_jwt_audience.strip()
        if expected_audience:
            aud = payload.get("aud")
            if isinstance(aud, list):
                ok = expected_audience in [str(item) for item in aud]
            else:
                ok = str(aud or "") == expected_audience
            if not ok:
                raise ValueError("JWT audience mismatch.")

        return payload

    @staticmethod
    def _extract_bearer_token(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization", "").strip()
        if not auth_header:
            return None
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header[7:].strip()
        return token or None

    @staticmethod
    def _client_ip(request: Request) -> str:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    @staticmethod
    def _unauthorized(message: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _rate_limited(message: str, *, retry_after: int) -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(max(int(retry_after), 1))},
        )


client_access_control = ClientAccessControl()
