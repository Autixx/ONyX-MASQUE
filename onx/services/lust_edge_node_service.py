from __future__ import annotations

from datetime import datetime, timezone
import shlex

from sqlalchemy.orm import Session

from onx.db.models.lust_service import LustService
from onx.db.models.node import Node, NodeAuthType
from onx.db.models.node_secret import NodeSecretKind
from onx.deploy.ssh_executor import SSHExecutor
from onx.services.lust_edge_deploy_service import lust_edge_deploy_service
from onx.services.secret_service import SecretService


class LustEdgeNodeService:
    def __init__(self, ssh_executor: SSHExecutor | None = None) -> None:
        self._ssh = ssh_executor or SSHExecutor()
        self._secrets = SecretService()

    def deploy_service(self, db: Session, service: LustService, progress_callback=None) -> dict:
        node = db.get(Node, service.node_id)
        if node is None:
            raise ValueError("Node not found.")
        if progress_callback:
            progress_callback("resolving management secret")
        management_secret = self._get_management_secret(db, node)
        if progress_callback:
            progress_callback("building deployment payload")
        payload = lust_edge_deploy_service.build_service_deployment(db, service)
        paths = dict(payload.get("paths") or {})
        files = dict(payload.get("files") or {})
        secret_refs = dict(payload.get("secret_refs") or {})
        acme = dict(payload.get("acme") or {})
        secret_files = {
            paths["client_ca_cert"]: self._decrypt_secret_ref(db, secret_refs["client_ca_cert_ref"]),
            paths["access_token_secret"]: self._decrypt_secret_ref(db, secret_refs["access_token_secret_ref"]),
        }
        remote_dirs = {
            paths["app_dir"],
            "/etc/onx/lust-edge",
            "/etc/nginx/sites-available",
            "/etc/nginx/sites-enabled",
        }
        if progress_callback:
            progress_callback("preparing remote directories")
        self._run_checked(
            node,
            management_secret,
            "mkdir -p " + " ".join(shlex.quote(item) for item in sorted(remote_dirs)),
            step="create remote directories",
        )

        if progress_callback:
            progress_callback("uploading edge application")
        self._install_file(node, management_secret, paths["app_py"], files["onx_lust_edge.py"], mode="0755")
        if progress_callback:
            progress_callback("uploading node installer")
        self._install_file(node, management_secret, paths["install_script"], files["install-edge.sh"], mode="0755")
        if progress_callback:
            progress_callback("uploading edge configuration")
        self._install_file(node, management_secret, paths["config_json"], files["config.json"], mode="0600")
        if progress_callback:
            progress_callback("uploading nginx configuration")
        self._install_file(node, management_secret, paths["nginx_site"], files["nginx.conf"], mode="0644")
        if progress_callback:
            progress_callback("uploading systemd unit")
        self._install_file(node, management_secret, paths["systemd_unit"], files["onx-lust-edge.service"], mode="0644")
        if progress_callback:
            progress_callback("uploading cert renewal hook")
        self._install_file(node, management_secret, paths["renew_hook"], files["renew-nginx.sh"], mode="0755")
        if progress_callback:
            progress_callback("uploading trust material")
        for path, content in secret_files.items():
            self._install_file(node, management_secret, path, content.strip() + "\n", mode="0600")

        stdout_parts: list[str] = []
        if progress_callback:
            progress_callback("installing node packages")
        code, stdout, stderr = self._run(
            node,
            management_secret,
            shlex.quote(paths["install_script"]),
            timeout_seconds=300,
        )
        if code != 0:
            raise RuntimeError(f"install node packages failed: {stderr or stdout or 'unknown error'}")
        if stdout.strip():
            stdout_parts.append(stdout.strip())

        if acme.get("enabled"):
            server_name = str(acme.get("server_name") or "").strip()
            if not server_name:
                raise ValueError("LuST ACME server_name is required for TLS deployment.")
            email = str(acme.get("email") or "").strip()
            email_arg = f"--email {shlex.quote(email)}" if email else "--register-unsafely-without-email"
            if progress_callback:
                progress_callback(f"issuing letsencrypt certificate for {server_name}")
            code, stdout, stderr = self._run(
                node,
                management_secret,
                "systemctl stop nginx >/dev/null 2>&1 || true; "
                "certbot certonly --standalone --non-interactive --agree-tos --keep-until-expiring "
                f"--preferred-challenges http -d {shlex.quote(server_name)} {email_arg}",
                timeout_seconds=600,
            )
            if code != 0:
                raise RuntimeError(
                    f"issue letsencrypt certificate for {server_name} failed: {stderr or stdout or 'unknown error'}"
                )
            if stdout.strip():
                stdout_parts.append(stdout.strip())

        if progress_callback:
            progress_callback("enabling nginx site")
        self._run_checked(
            node,
            management_secret,
            f"ln -sfn {shlex.quote(paths['nginx_site'])} {shlex.quote(paths['nginx_site_enabled'])}",
            step="enable nginx site",
        )
        self._run_checked(
            node,
            management_secret,
            "rm -f /etc/nginx/sites-enabled/default >/dev/null 2>&1 || true",
            step="disable default nginx site",
        )
        if progress_callback:
            progress_callback("reloading systemd")
        self._run_checked(node, management_secret, "systemctl daemon-reload", step="reload systemd")
        if progress_callback:
            progress_callback("starting lust edge service")
        self._run_checked(
            node,
            management_secret,
            "systemctl enable --now onx-lust-edge.service && systemctl restart onx-lust-edge.service",
            step="start lust edge service",
            timeout_seconds=180,
        )
        if progress_callback:
            progress_callback("validating nginx configuration")
        self._run_checked(node, management_secret, "nginx -t", step="validate nginx configuration")
        if progress_callback:
            progress_callback("starting nginx")
        self._run_checked(
            node,
            management_secret,
            "systemctl enable --now nginx && systemctl reload nginx",
            step="start nginx",
            timeout_seconds=180,
        )

        if progress_callback:
            progress_callback("running local health check")
        code, stdout, stderr = self._run(
            node,
            management_secret,
            f"\"{paths['venv_dir']}/bin/python\" - <<\"PY\"\n"
            "import json\n"
            "import urllib.request\n"
            "with urllib.request.urlopen(\"http://127.0.0.1:9443/health\", timeout=10) as resp:\n"
            "    payload = json.loads(resp.read().decode(\"utf-8\"))\n"
            "    if payload.get(\"status\") != \"ok\":\n"
            "        raise SystemExit(json.dumps(payload))\n"
            "    print(json.dumps(payload))\n"
            "PY\n",
            timeout_seconds=180,
        )
        if code != 0:
            raise RuntimeError(f"run local health check failed: {stderr or stdout or f'node {node.name} health check failed'}")
        if stdout.strip():
            stdout_parts.append(stdout.strip())

        applied_at = datetime.now(timezone.utc)
        service.state = "active"
        service.last_error_text = None
        service.health_summary_json = {
            "status": "active",
            "edge_mode": "external",
            "node_name": node.name,
            "public_endpoint": f"{service.public_host}:{service.public_port or service.listen_port}",
            "path": service.h2_path,
            "tls_mode": "letsencrypt" if service.use_tls else "disabled",
            "tls_server_name": service.tls_server_name or service.public_host,
            "applied_at": applied_at.isoformat(),
        }
        db.add(service)
        db.commit()
        db.refresh(service)
        return {
            "node_id": node.id,
            "node_name": node.name,
            "service_id": service.id,
            "service_name": service.name,
            "paths": paths,
            "health": service.health_summary_json,
            "stdout": "\n\n".join(stdout_parts),
        }

    def _get_management_secret(self, db: Session, node: Node) -> str:
        secret_kind = NodeSecretKind.SSH_PASSWORD if node.auth_type == NodeAuthType.PASSWORD else NodeSecretKind.SSH_PRIVATE_KEY
        secret = self._secrets.get_active_secret(db, node.id, secret_kind)
        if secret is None:
            raise ValueError(f"Missing active management secret for node '{node.name}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    def _decrypt_secret_ref(self, db: Session, secret_ref: str) -> str:
        secret = self._secrets.get_secret_by_ref(db, secret_ref)
        if secret is None:
            raise ValueError(f"Missing deployment secret '{secret_ref}'.")
        return self._secrets.decrypt(secret.encrypted_value)

    @staticmethod
    def _remote_shell(node: Node, command: str) -> str:
        inner = shlex.quote(command)
        if node.ssh_user == "root":
            return f"sh -lc {inner}"
        return f"sudo -n sh -lc {inner}"

    def _run(self, node: Node, management_secret: str, command: str, *, timeout_seconds: int = 60) -> tuple[int, str, str]:
        return self._ssh.run(
            node,
            management_secret,
            self._remote_shell(node, command),
            timeout_seconds=timeout_seconds,
        )

    def _run_checked(
        self,
        node: Node,
        management_secret: str,
        command: str,
        *,
        step: str,
        timeout_seconds: int = 60,
    ) -> tuple[str, str]:
        code, stdout, stderr = self._run(node, management_secret, command, timeout_seconds=timeout_seconds)
        if code != 0:
            raise RuntimeError(f"{step} failed: {stderr or stdout or 'unknown error'}")
        return stdout, stderr

    def _install_file(self, node: Node, management_secret: str, destination: str, content: str, *, mode: str) -> None:
        temp_path = f"/tmp/onx-lust-{abs(hash(destination)) & 0xFFFFFFFF:x}"
        self._ssh.write_file(node, management_secret, temp_path, content)
        try:
            code, stdout, stderr = self._run(
                node,
                management_secret,
                "install "
                f"-D -m {shlex.quote(mode)} "
                f"{shlex.quote(temp_path)} {shlex.quote(destination)}",
            )
            if code != 0:
                raise RuntimeError(stderr or stdout or f"Failed to install remote file {destination}")
        finally:
            self._ssh.run(node, management_secret, f"rm -f {shlex.quote(temp_path)}", timeout_seconds=15)


lust_edge_node_service = LustEdgeNodeService()
