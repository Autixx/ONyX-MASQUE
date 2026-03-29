from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EdgeServiceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    node_id: str
    public_host: str
    public_port: int = 443
    tls_server_name: str | None = None
    path: str = "/lust"
    stream_path: str = "/lust/stream"
    dns_resolver: str | None = None


class EdgeTrustConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token_issuer: str = "onx-control-plane"
    token_audience: str = "onx-lust-edge"
    client_ca_cert_path: str = "/etc/onx/lust-edge/client-ca.cert.pem"
    access_token_secret_path: str = "/etc/onx/lust-edge/access-token.secret"


class EdgeRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    issuer: str = "ONyX control-plane"
    transport: str = "lust"
    protocol: str = "lust-h2"
    service: EdgeServiceConfig
    trust: EdgeTrustConfig = Field(default_factory=EdgeTrustConfig)

    @property
    def access_token_secret(self) -> str:
        return Path(self.trust.access_token_secret_path).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def load_edge_config() -> EdgeRuntimeConfig:
    config_path = Path(os.environ.get("ONX_LUST_EDGE_CONFIG_PATH", "/etc/onx/lust-edge/config.json")).expanduser()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    service_raw = raw.get("service") or {}
    return EdgeRuntimeConfig(
        version=int(raw.get("version") or 1),
        issuer=str(raw.get("issuer") or "ONyX control-plane"),
        transport=str(raw.get("transport") or "lust"),
        protocol=str(raw.get("protocol") or "lust-h2"),
        service=EdgeServiceConfig(**service_raw),
        trust=EdgeTrustConfig(**dict(raw.get("trust") or {})),
    )
