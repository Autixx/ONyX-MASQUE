from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from onx.core.config import get_settings


class LustAccessTokenService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def issue_token(
        self,
        *,
        user_id: str,
        device_id: str,
        peer_id: str,
        service_id: str,
        node_id: str,
        cert_fingerprint_sha256: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "iss": self._settings.lust_access_token_issuer,
            "aud": self._settings.lust_access_token_audience,
            "typ": "lust_access",
            "ver": 1,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self._settings.lust_access_token_ttl_seconds)).timestamp()),
            "user_id": user_id,
            "device_id": device_id,
            "peer_id": peer_id,
            "service_id": service_id,
            "node_id": node_id,
            "cert_fingerprint_sha256": cert_fingerprint_sha256.lower(),
        }
        header = {"alg": "HS256", "typ": "JWT"}
        segments = [self._encode_json(header), self._encode_json(payload)]
        signing_input = ".".join(segments).encode("ascii")
        signature = self._sign(signing_input)
        segments.append(self._b64encode(signature))
        return ".".join(segments)

    def verify_token(self, token: str) -> dict[str, Any]:
        parts = str(token or "").strip().split(".")
        if len(parts) != 3:
            raise ValueError("Malformed LuST access token.")
        signing_input = ".".join(parts[:2]).encode("ascii")
        actual = self._b64decode(parts[2])
        expected = self._sign(signing_input)
        if not hmac.compare_digest(expected, actual):
            raise ValueError("LuST access token signature is invalid.")
        payload = json.loads(self._b64decode(parts[1]).decode("utf-8"))
        now = int(datetime.now(timezone.utc).timestamp())
        if str(payload.get("iss") or "") != self._settings.lust_access_token_issuer:
            raise ValueError("Unexpected LuST token issuer.")
        if str(payload.get("aud") or "") != self._settings.lust_access_token_audience:
            raise ValueError("Unexpected LuST token audience.")
        if str(payload.get("typ") or "") != "lust_access":
            raise ValueError("Unexpected LuST token type.")
        if int(payload.get("nbf") or 0) > now:
            raise ValueError("LuST access token is not active yet.")
        if int(payload.get("exp") or 0) <= now:
            raise ValueError("LuST access token has expired.")
        return payload

    def signing_secret(self) -> str:
        if self._settings.lust_access_token_secret:
            return self._settings.lust_access_token_secret
        digest = hashlib.sha256(f"{self._settings.master_key}:lust-edge".encode("utf-8")).hexdigest()
        return digest

    def _sign(self, value: bytes) -> bytes:
        return hmac.new(self.signing_secret().encode("utf-8"), value, hashlib.sha256).digest()

    @classmethod
    def _encode_json(cls, value: dict[str, Any]) -> str:
        return cls._b64encode(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))


lust_access_token_service = LustAccessTokenService()
