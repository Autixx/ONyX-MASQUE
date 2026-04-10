from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from onx.db.models.lust_service import LustService
from onx.db.models.node_secret import NodeSecretKind
from onx.services.device_certificate_service import device_certificate_service
from onx.services.lust_access_token_service import lust_access_token_service
from onx.services.lust_routing_service import lust_routing_service
from onx.services.secret_service import SecretService


class LustEdgeDeployService:
    def __init__(self) -> None:
        self._secrets = SecretService()
        self._templates_dir = Path(__file__).resolve().parents[2] / "templates" / "lust-edge"

    def build_service_deployment(self, db: Session, service: LustService) -> dict:
        client_ca_ref = f"lust-edge:{service.id}:client-ca-cert"
        access_secret_ref = f"lust-edge:{service.id}:access-token-secret"
        client_ca_pem = device_certificate_service.ca_certificate_pem()
        access_secret = lust_access_token_service.signing_secret()
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=service.node_id,
            kind=NodeSecretKind.TRANSPORT_PRIVATE_KEY,
            secret_ref=client_ca_ref,
            secret_value=client_ca_pem,
        )
        self._secrets.upsert_node_secret_with_ref(
            db,
            node_id=service.node_id,
            kind=NodeSecretKind.TRANSPORT_PRIVATE_KEY,
            secret_ref=access_secret_ref,
            secret_value=access_secret,
        )

        path = str(service.h2_path or "/lust").strip() or "/lust"
        if not path.startswith("/"):
            path = "/" + path
        stream_path = path.rstrip("/") + "/stream"
        edge_config = {
            "version": 1,
            "issuer": "ONyX control-plane",
            "transport": "lust",
            "protocol": "lust-h2",
            "service": {
                "id": service.id,
                "name": service.name,
                "node_id": service.node_id,
                "role": service.role,
                "public_host": service.public_host,
                "public_port": service.public_port or service.listen_port,
                "tls_server_name": service.tls_server_name or service.public_host,
                "path": path,
                "stream_path": stream_path,
                "dns_resolver": service.client_dns_resolver,
            },
            "trust": {
                "token_issuer": "onx-control-plane",
                "token_audience": "onx-lust-edge",
                "upstream_token_audience": "onx-lust-edge-upstream",
                "client_ca_cert_path": "/etc/onx/lust-edge/client-ca.cert.pem",
                "access_token_secret_path": "/etc/onx/lust-edge/access-token.secret",
            },
            "routing": lust_routing_service.build_gateway_runtime_config(db, service) if str(service.role or "").strip().lower() == "gate" else {},
            "acme": {
                "enabled": bool(service.use_tls),
                "server_name": service.tls_server_name or service.public_host,
                "email": (service.acme_email or "").strip() or None,
            },
        }
        return {
            "edge_config": edge_config,
            "acme": {
                "enabled": bool(service.use_tls),
                "server_name": service.tls_server_name or service.public_host,
                "email": (service.acme_email or "").strip() or None,
            },
            "paths": {
                "app_dir": "/opt/onx/lust-edge",
                "app_py": "/opt/onx/lust-edge/onx_lust_edge.py",
                "install_script": "/opt/onx/lust-edge/install-edge.sh",
                "venv_dir": "/opt/onx/lust-edge/.venv",
                "config_json": "/etc/onx/lust-edge/config.json",
                "client_ca_cert": "/etc/onx/lust-edge/client-ca.cert.pem",
                "access_token_secret": "/etc/onx/lust-edge/access-token.secret",
                "nginx_site": f"/etc/nginx/sites-available/onx-lust-{service.id}.conf",
                "nginx_site_enabled": f"/etc/nginx/sites-enabled/onx-lust-{service.id}.conf",
                "systemd_unit": "/etc/systemd/system/onx-lust-edge.service",
                "renew_hook": "/etc/letsencrypt/renewal-hooks/deploy/onx-lust-nginx-reload.sh",
            },
            "secret_refs": {
                "client_ca_cert_ref": client_ca_ref,
                "access_token_secret_ref": access_secret_ref,
            },
            "files": {
                "config.json": json.dumps(edge_config, indent=2, ensure_ascii=True) + "\n",
                "nginx.conf": self.render_nginx_site(service),
                "onx-lust-edge.service": self.render_systemd_unit(),
                "onx_lust_edge.py": self.render_edge_app(),
                "install-edge.sh": self.render_install_script(),
                "renew-nginx.sh": self.render_renew_hook(),
            },
        }

    @staticmethod
    def render_nginx_site(service: LustService) -> str:
        server_name = service.tls_server_name or service.public_host
        path = str(service.h2_path or "/lust").strip() or "/lust"
        if not path.startswith("/"):
            path = "/" + path
        path_prefix = path.rstrip("/") + "/"
        listen_port = int(service.public_port or 443)
        return f"""server {{
    listen {listen_port} ssl http2;
    server_name {server_name};

    ssl_certificate /etc/letsencrypt/live/{server_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{server_name}/privkey.pem;
    ssl_client_certificate /etc/onx/lust-edge/client-ca.cert.pem;
    ssl_verify_client optional;

    location = {path} {{
        proxy_pass http://127.0.0.1:9443{path};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
        proxy_set_header X-SSL-Client-Fingerprint $ssl_client_fingerprint;
        proxy_set_header X-SSL-Client-Serial $ssl_client_serial;
    }}

    location ^~ {path_prefix} {{
        proxy_pass http://127.0.0.1:9443;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
        proxy_set_header X-SSL-Client-Fingerprint $ssl_client_fingerprint;
        proxy_set_header X-SSL-Client-Serial $ssl_client_serial;
        proxy_set_header Connection "";
    }}

    location / {{
        return 403;
    }}
}}
"""

    @staticmethod
    def render_systemd_unit() -> str:
        return """[Unit]
Description=ONyX LuST edge
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/onx/lust-edge
Environment=ONX_LUST_EDGE_CONFIG_PATH=/etc/onx/lust-edge/config.json
Environment=ONX_LUST_EDGE_APP_DIR=/opt/onx/lust-edge
ExecStart=/opt/onx/lust-edge/.venv/bin/python /opt/onx/lust-edge/onx_lust_edge.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""

    def render_edge_app(self) -> str:
        return self._render_template("onx_lust_edge.py.template")

    def render_install_script(self) -> str:
        return self._render_template("install-edge.sh.template")

    @staticmethod
    def render_renew_hook() -> str:
        return """#!/usr/bin/env bash
set -euo pipefail

if command -v systemctl >/dev/null 2>&1; then
  systemctl reload nginx >/dev/null 2>&1 || true
fi
"""

    def _render_template(self, filename: str) -> str:
        return (self._templates_dir / filename).read_text(encoding="utf-8")


lust_edge_deploy_service = LustEdgeDeployService()
