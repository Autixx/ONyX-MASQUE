from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import logging
import os
import platform
import secrets
import signal
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import httpx


LOG_NAME = "lust-client"
CLIENT_HOME = Path.home() / ".onyx-client"
RUNTIME_DIR = CLIENT_HOME / "runtime"
LOG_DIR = CLIENT_HOME / "logs"
STATUS_PATH = RUNTIME_DIR / "lust-client-status.json"
WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str | None) -> bytes:
    raw = str(value or "").encode("ascii")
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


def _subprocess_hidden_kwargs() -> dict[str, Any]:
    if platform.system() != "Windows" or not WINDOWS_CREATE_NO_WINDOW:
        return {}
    return {"creationflags": WINDOWS_CREATE_NO_WINDOW}


def _resolve_binary_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent / "bin"


def _runtime_binary(name: str) -> Path:
    return _resolve_binary_dir() / name


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(slots=True)
class EndpointConfig:
    scheme: str
    host: str
    port: int
    server_name: str
    path: str
    http_version: str


@dataclass(slots=True)
class AuthConfig:
    scheme: str
    token: str


@dataclass(slots=True)
class ClientIdentity:
    peer_id: str
    username: str


@dataclass(slots=True)
class MtlsConfig:
    mode: str
    client_certificate_path: str | None
    client_key_path: str | None
    client_certificate_pem: str | None
    ca_certificate_pem: str | None
    client_certificate_fingerprint_sha256: str | None


@dataclass(slots=True)
class SessionPaths:
    stream_path: str
    open_path: str
    frame_path: str
    poll_path: str
    close_path: str
    heartbeat_seconds: float
    connect_timeout_seconds: float
    poll_timeout_seconds: float


@dataclass(slots=True)
class ProxyConfig:
    socks_host: str
    socks_port: int


@dataclass(slots=True)
class TunnelConfig:
    mode: str
    interface_name: str
    address_v4: str
    netmask_v4: str
    gateway_v4: str
    mtu: int
    primary_interface: str | None
    dns_servers: tuple[str, ...]
    bypass_routes: tuple[str, ...]


@dataclass(slots=True)
class LustConfig:
    endpoint: EndpointConfig
    authentication: AuthConfig
    client: ClientIdentity
    mtls: MtlsConfig
    session: SessionPaths
    proxy: ProxyConfig
    tunnel: TunnelConfig
    dns_resolver: str | None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LustConfig":
        endpoint_raw = dict(raw.get("endpoint") or {})
        session_raw = dict(raw.get("session") or {})
        auth_raw = dict(raw.get("authentication") or {})
        client_raw = dict(raw.get("client") or {})
        dns_raw = dict(raw.get("dns") or {})
        mtls_raw = dict(raw.get("mtls") or {})
        proxy_raw = dict(raw.get("proxy") or {})
        tunnel_raw = dict(raw.get("tunnel") or {})
        path = str(endpoint_raw.get("path") or "/lust").strip() or "/lust"
        if not path.startswith("/"):
            path = "/" + path
        endpoint = EndpointConfig(
            scheme=str(endpoint_raw.get("scheme") or "https").strip().lower(),
            host=str(endpoint_raw.get("host") or "").strip(),
            port=int(endpoint_raw.get("port") or 443),
            server_name=str(endpoint_raw.get("server_name") or endpoint_raw.get("host") or "").strip(),
            path=path,
            http_version=str(endpoint_raw.get("http_version") or "2").strip(),
        )
        if endpoint.scheme not in {"http", "https"} or not endpoint.host or endpoint.port <= 0:
            raise ValueError("Invalid LuST endpoint configuration.")
        auth = AuthConfig(
            scheme=str(auth_raw.get("scheme") or "bearer").strip().lower(),
            token=str(auth_raw.get("token") or "").strip(),
        )
        if auth.scheme != "bearer" or not auth.token:
            raise ValueError("Only bearer authentication with a token is supported.")
        client = ClientIdentity(
            peer_id=str(client_raw.get("peer_id") or "").strip(),
            username=str(client_raw.get("username") or "").strip(),
        )
        if not client.peer_id:
            raise ValueError("client.peer_id is required.")
        mtls = MtlsConfig(
            mode=str(mtls_raw.get("mode") or "disabled").strip().lower(),
            client_certificate_path=str(mtls_raw.get("client_certificate_path") or "").strip() or None,
            client_key_path=str(mtls_raw.get("client_key_path") or "").strip() or None,
            client_certificate_pem=str(mtls_raw.get("client_certificate_pem") or "").strip() or None,
            ca_certificate_pem=str(mtls_raw.get("ca_certificate_pem") or "").strip() or None,
            client_certificate_fingerprint_sha256=str(mtls_raw.get("client_certificate_fingerprint_sha256") or "").strip() or None,
        )
        if mtls.mode == "required" and (not mtls.client_certificate_path or not mtls.client_key_path):
            raise ValueError("LuST mTLS requires client_certificate_path and client_key_path.")

        def _session_path(key: str, fallback: str) -> str:
            value = str(session_raw.get(key) or fallback).strip() or fallback
            return value if value.startswith("/") else "/" + value

        session = SessionPaths(
            stream_path=_session_path("stream_path", path.rstrip("/") + "/stream"),
            open_path=_session_path("open_path", path.rstrip("/") + "/session/open"),
            frame_path=_session_path("frame_path", path.rstrip("/") + "/frame"),
            poll_path=_session_path("poll_path", path.rstrip("/") + "/frame/poll"),
            close_path=_session_path("close_path", path.rstrip("/") + "/session/close"),
            heartbeat_seconds=max(5.0, float(session_raw.get("heartbeat_seconds") or 15.0)),
            connect_timeout_seconds=max(3.0, float(session_raw.get("connect_timeout_seconds") or 10.0)),
            poll_timeout_seconds=max(5.0, float(session_raw.get("poll_timeout_seconds") or 20.0)),
        )
        proxy = ProxyConfig(
            socks_host=str(proxy_raw.get("socks_host") or "127.0.0.1").strip() or "127.0.0.1",
            socks_port=int(proxy_raw.get("socks_port") or 1080),
        )
        tunnel_mode = str(tunnel_raw.get("mode") or ("wintun" if platform.system() == "Windows" else "proxy")).strip().lower()
        dns_servers_raw = tunnel_raw.get("dns_servers") or []
        if not isinstance(dns_servers_raw, list):
            dns_servers_raw = [dns_servers_raw]
        dns_servers = tuple(str(item).strip() for item in dns_servers_raw if str(item or "").strip())
        bypass_raw = tunnel_raw.get("bypass_routes") or []
        if not isinstance(bypass_raw, list):
            bypass_raw = [bypass_raw]
        tunnel = TunnelConfig(
            mode=tunnel_mode or "proxy",
            interface_name=str(tunnel_raw.get("interface_name") or "wintun").strip() or "wintun",
            address_v4=str(tunnel_raw.get("address_v4") or "198.18.0.1").strip() or "198.18.0.1",
            netmask_v4=str(tunnel_raw.get("netmask_v4") or "255.255.0.0").strip() or "255.255.0.0",
            gateway_v4=str(tunnel_raw.get("gateway_v4") or tunnel_raw.get("address_v4") or "198.18.0.1").strip() or "198.18.0.1",
            mtu=max(1200, int(tunnel_raw.get("mtu") or 1380)),
            primary_interface=str(tunnel_raw.get("primary_interface") or "").strip() or None,
            dns_servers=dns_servers,
            bypass_routes=tuple(str(item).strip() for item in bypass_raw if str(item or "").strip()),
        )
        if tunnel.mode not in {"wintun", "proxy"}:
            raise ValueError("tunnel.mode must be either 'wintun' or 'proxy'.")
        if tunnel.mode == "wintun":
            for value in (tunnel.address_v4, tunnel.netmask_v4, tunnel.gateway_v4):
                ipaddress.IPv4Address(value)
            for value in tunnel.dns_servers:
                ipaddress.ip_address(value)
            for value in tunnel.bypass_routes:
                ipaddress.ip_network(value, strict=False)
        return cls(
            endpoint=endpoint,
            authentication=auth,
            client=client,
            mtls=mtls,
            session=session,
            proxy=proxy,
            tunnel=tunnel,
            dns_resolver=str(dns_raw.get("resolver") or "").strip() or None,
        )

    @property
    def base_url(self) -> str:
        return f"{self.endpoint.scheme}://{self.endpoint.host}:{self.endpoint.port}"

    def url_for(self, path: str) -> str:
        return f"{self.base_url}{path}"


@dataclass(slots=True)
class PrimaryRoute:
    interface_alias: str
    next_hop: str


def ensure_dirs() -> None:
    CLIENT_HOME.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging(verbose: bool) -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger(LOG_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    file_handler = logging.FileHandler(LOG_DIR / "lust-client.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def write_status(
    *,
    state: str,
    config: LustConfig | None,
    detail: str = "",
    response: dict[str, Any] | None = None,
    proxy: dict[str, Any] | None = None,
    tunnel: dict[str, Any] | None = None,
) -> None:
    payload = {
        "state": state,
        "detail": detail,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "response": response or {},
        "proxy": proxy or {},
        "tunnel": tunnel or {},
    }
    if config is not None:
        payload["endpoint"] = {
            "base_url": config.base_url,
            "host": config.endpoint.host,
            "port": config.endpoint.port,
            "http_version": config.endpoint.http_version,
            "peer_id": config.client.peer_id,
            "username": config.client.username,
        }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def load_config(path: str) -> LustConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or str(raw.get("type") or "").strip().lower() != "lust":
        raise ValueError("LuST config must be a JSON object with type='lust'.")
    return LustConfig.from_dict(raw)


def build_tls_verify(config: LustConfig) -> str | bool | ssl.SSLContext:
    if config.endpoint.scheme != "https":
        return False
    if config.mtls.mode != "required":
        return True
    ensure_dirs()
    cert_path = config.mtls.client_certificate_path
    key_path = config.mtls.client_key_path
    if config.mtls.client_certificate_pem:
        cert_file = RUNTIME_DIR / "lust-client-runtime-cert.pem"
        cert_file.write_text(config.mtls.client_certificate_pem.strip() + "\n", encoding="utf-8")
        cert_path = str(cert_file)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if config.mtls.ca_certificate_pem:
        ca_file = RUNTIME_DIR / "lust-client-runtime-ca.pem"
        ca_file.write_text(config.mtls.ca_certificate_pem.strip() + "\n", encoding="utf-8")
        context.load_verify_locations(cafile=str(ca_file))
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context


def install_signal_handlers(stop_event: threading.Event, logger: logging.Logger) -> None:
    def _handler(signum, _frame):
        logger.info("signal_received signum=%s", signum)
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handler)


def _probe_headers(config: LustConfig) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {config.authentication.token}",
        "User-Agent": "ONyX-LuST-Client/0.3",
        "X-ONyX-Peer-ID": config.client.peer_id,
    }
    if config.mtls.client_certificate_fingerprint_sha256:
        headers["X-ONyX-Cert-Fingerprint"] = config.mtls.client_certificate_fingerprint_sha256
    return headers


def probe_endpoint(config: LustConfig, verify: str | bool | ssl.SSLContext, logger: logging.Logger) -> dict[str, Any]:
    started = time.perf_counter()
    with httpx.Client(
        http2=True,
        verify=verify,
        timeout=httpx.Timeout(config.session.connect_timeout_seconds, connect=config.session.connect_timeout_seconds, read=None),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(config.url_for(config.endpoint.path), headers=_probe_headers(config))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    negotiated = str(response.http_version or "")
    logger.info("probe_ok status=%s http=%s elapsed_ms=%s url=%s", response.status_code, negotiated or "unknown", elapsed_ms, config.url_for(config.endpoint.path))
    if config.endpoint.http_version == "2" and negotiated not in {"HTTP/2", "HTTP/2.0"}:
        raise RuntimeError(f"Endpoint is reachable but did not negotiate HTTP/2: {negotiated or 'unknown'}")
    if response.status_code >= 500:
        raise RuntimeError(f"LuST endpoint returned server error {response.status_code}")
    return {"status_code": response.status_code, "http_version": negotiated, "elapsed_ms": elapsed_ms}


class EdgeController:
    def __init__(self, config: LustConfig, logger: logging.Logger, verify: str | bool | ssl.SSLContext) -> None:
        self._config = config
        self._logger = logger
        self._verify = verify
        self._stop_event = threading.Event()
        self._session_id = ""
        self._failed_detail = ""
        self._thread_local = threading.local()
        self._lock = threading.Lock()
        self._tcp_channels: dict[str, socket.socket] = {}
        self._udp_channels: dict[str, "UdpAssociation"] = {}
        self._poll_thread: threading.Thread | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def failed_detail(self) -> str:
        return self._failed_detail

    def start(self) -> dict[str, Any]:
        payload = self._request_json("POST", self._config.session.open_path, json_body={})
        self._session_id = str(payload.get("session_id") or "").strip()
        if not self._session_id:
            raise RuntimeError("LuST edge did not return a session_id.")
        self._poll_thread = threading.Thread(target=self._poll_loop, name="lust-poll", daemon=True)
        self._poll_thread.start()
        return payload

    def stop(self) -> None:
        self._stop_event.set()
        if self._session_id:
            try:
                self._request_json("POST", self._config.session.close_path, json_body={"session_id": self._session_id}, allow_empty=True)
            except Exception:
                pass
        with self._lock:
            tcp_channels = list(self._tcp_channels.values())
            udp_channels = list(set(self._udp_channels.values()))
            self._tcp_channels.clear()
            self._udp_channels.clear()
        for sock in tcp_channels:
            try:
                sock.close()
            except Exception:
                pass
        for assoc in udp_channels:
            assoc.close()
        self._session_id = ""

    def send_frame(self, frame: dict[str, Any], *, allow_empty: bool = False) -> dict[str, Any]:
        if not self._session_id:
            raise RuntimeError("LuST session is not open.")
        payload = dict(frame)
        payload["session_id"] = self._session_id
        return self._request_json("POST", self._config.session.frame_path, json_body=payload, allow_empty=allow_empty)

    def register_tcp_channel(self, channel_id: str, sock: socket.socket) -> None:
        with self._lock:
            self._tcp_channels[channel_id] = sock

    def unregister_tcp_channel(self, channel_id: str) -> None:
        with self._lock:
            self._tcp_channels.pop(channel_id, None)

    def register_udp_channel(self, channel_id: str, association: "UdpAssociation") -> None:
        with self._lock:
            self._udp_channels[channel_id] = association

    def unregister_udp_channel(self, channel_id: str) -> None:
        with self._lock:
            self._udp_channels.pop(channel_id, None)

    def close_channel(self, channel_id: str) -> None:
        try:
            self.send_frame({"op": "close", "channel_id": channel_id}, allow_empty=False)
        except Exception:
            pass
        with self._lock:
            sock = self._tcp_channels.pop(channel_id, None)
            assoc = self._udp_channels.pop(channel_id, None)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        if assoc is not None:
            assoc.close_channel(channel_id)

    def _poll_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                response = self._request(
                    "GET",
                    self._config.session.poll_path,
                    params={"session_id": self._session_id, "timeout": self._config.session.poll_timeout_seconds},
                    allow_statuses={204},
                )
                if response.status_code == 204:
                    continue
                self._dispatch_frame(response.json())
        except Exception as exc:
            self._failed_detail = str(exc)
            self._logger.warning("poll_loop_failed %s", exc)
            self._stop_event.set()

    def _dispatch_frame(self, frame: dict[str, Any]) -> None:
        op = str(frame.get("op") or "").strip().lower()
        channel_id = str(frame.get("channel_id") or "").strip()
        if not channel_id:
            return
        if op == "tcp_data":
            with self._lock:
                sock = self._tcp_channels.get(channel_id)
            if sock is None:
                return
            try:
                sock.sendall(_b64decode(frame.get("data_b64")))
            except Exception:
                self.close_channel(channel_id)
            return
        if op == "udp_data":
            with self._lock:
                assoc = self._udp_channels.get(channel_id)
            if assoc is not None:
                assoc.handle_remote_datagram(
                    channel_id,
                    host=str(frame.get("host") or ""),
                    port=int(frame.get("port") or 0),
                    data=_b64decode(frame.get("data_b64")),
                )
            return
        if op in {"close", "error"}:
            self.close_channel(channel_id)

    def _request_json(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None, allow_empty: bool = False) -> dict[str, Any]:
        response = self._request(method, path, json_body=json_body, params=params)
        if allow_empty and not response.content:
            return {}
        return response.json()

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None, allow_statuses: set[int] | None = None) -> httpx.Response:
        client = self._thread_client()
        response = client.request(method, self._config.url_for(path), headers=self._headers(), json=json_body, params=params)
        allowed = allow_statuses or set()
        if response.status_code >= 400 and response.status_code not in allowed:
            detail = response.text.strip()
            try:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("detail"):
                    detail = str(payload["detail"])
            except Exception:
                pass
            raise RuntimeError(f"LuST edge {method} {path} failed: {response.status_code} {detail}")
        return response

    def _thread_client(self) -> httpx.Client:
        client = getattr(self._thread_local, "client", None)
        if client is None:
            client = httpx.Client(
                http2=True,
                verify=self._verify,
                timeout=httpx.Timeout(self._config.session.connect_timeout_seconds, connect=self._config.session.connect_timeout_seconds, read=30.0),
                follow_redirects=False,
                trust_env=False,
            )
            self._thread_local.client = client
        return client

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.authentication.token}",
            "User-Agent": "ONyX-LuST-Client/0.3",
            "X-ONyX-Peer-ID": self._config.client.peer_id,
        }
        if self._config.client.username:
            headers["X-ONyX-Username"] = self._config.client.username
        if self._config.dns_resolver:
            headers["X-ONyX-DNS-Resolver"] = self._config.dns_resolver
        if self._config.mtls.client_certificate_fingerprint_sha256:
            headers["X-ONyX-Cert-Fingerprint"] = self._config.mtls.client_certificate_fingerprint_sha256
        return headers


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise EOFError("Unexpected EOF.")
        chunks.extend(chunk)
    return bytes(chunks)


def _read_socks_address(sock: socket.socket, atyp: int) -> tuple[str, int]:
    if atyp == 1:
        host = socket.inet_ntoa(_read_exact(sock, 4))
    elif atyp == 3:
        length = _read_exact(sock, 1)[0]
        host = _read_exact(sock, length).decode("utf-8")
    elif atyp == 4:
        host = socket.inet_ntop(socket.AF_INET6, _read_exact(sock, 16))
    else:
        raise ValueError("Unsupported SOCKS ATYP.")
    port = struct.unpack("!H", _read_exact(sock, 2))[0]
    return host, port


def parse_socks5_udp_request(packet: bytes) -> tuple[str, int, bytes]:
    if len(packet) < 10:
        raise ValueError("SOCKS5 UDP packet is too short.")
    atyp = packet[3]
    offset = 4
    if atyp == 1:
        host = socket.inet_ntoa(packet[offset:offset + 4])
        offset += 4
    elif atyp == 3:
        length = packet[offset]
        offset += 1
        host = packet[offset:offset + length].decode("utf-8")
        offset += length
    elif atyp == 4:
        host = socket.inet_ntop(socket.AF_INET6, packet[offset:offset + 16])
        offset += 16
    else:
        raise ValueError("Unsupported SOCKS5 UDP ATYP.")
    port = struct.unpack("!H", packet[offset:offset + 2])[0]
    return host, port, packet[offset + 2:]


def build_socks5_udp_response(host: str, port: int, payload: bytes) -> bytes:
    try:
        header = b"\x00\x00\x00\x01" + socket.inet_aton(host)
    except OSError:
        encoded = host.encode("utf-8")
        header = b"\x00\x00\x00\x03" + bytes([len(encoded)]) + encoded
    return header + struct.pack("!H", int(port)) + payload


class UdpAssociation:
    def __init__(self, controller: EdgeController, logger: logging.Logger, bind_host: str) -> None:
        self._controller = controller
        self._logger = logger
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_host, 0))
        self.sock.settimeout(1.0)
        self.client_addr: tuple[str, int] | None = None
        self._stop_event = threading.Event()
        self._channels_by_target: dict[tuple[str, int], str] = {}
        self._target_by_channel: dict[str, tuple[str, int]] = {}
        self._thread = threading.Thread(target=self._run, name=f"lust-udp-{self.sock.getsockname()[1]}", daemon=True)
        self._thread.start()

    @property
    def bind_port(self) -> int:
        return int(self.sock.getsockname()[1])

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                packet, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                host, port, payload = parse_socks5_udp_request(packet)
            except ValueError:
                continue
            self.client_addr = addr
            key = (host, port)
            channel_id = self._channels_by_target.get(key)
            if channel_id is None:
                channel_id = f"udp-{secrets.token_hex(8)}"
                self._channels_by_target[key] = channel_id
                self._target_by_channel[channel_id] = key
                self._controller.send_frame({"op": "open_udp", "channel_id": channel_id, "host": host, "port": port})
                self._controller.register_udp_channel(channel_id, self)
            self._controller.send_frame({"op": "udp_data", "channel_id": channel_id, "data_b64": _b64encode(payload)})

    def handle_remote_datagram(self, channel_id: str, *, host: str, port: int, data: bytes) -> None:
        if self.client_addr is None:
            return
        if not host or port <= 0:
            host, port = self._target_by_channel.get(channel_id, ("0.0.0.0", 0))
        packet = build_socks5_udp_response(host, port, data)
        try:
            self.sock.sendto(packet, self.client_addr)
        except OSError:
            self.close()

    def close_channel(self, channel_id: str) -> None:
        target = self._target_by_channel.pop(channel_id, None)
        if target is not None:
            self._channels_by_target.pop(target, None)
        self._controller.unregister_udp_channel(channel_id)

    def close(self) -> None:
        self._stop_event.set()
        for channel_id in list(self._target_by_channel):
            self.close_channel(channel_id)
        try:
            self.sock.close()
        except OSError:
            pass


class Socks5Server:
    def __init__(self, controller: EdgeController, config: LustConfig, logger: logging.Logger) -> None:
        self._controller = controller
        self._config = config
        self._logger = logger
        self._stop_event = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._bind_listener()
        self._listener.listen(64)
        self._listener.settimeout(1.0)
        self._thread = threading.Thread(target=self._accept_loop, name="lust-socks", daemon=True)

    @property
    def listen_host(self) -> str:
        return str(self._listener.getsockname()[0])

    @property
    def listen_port(self) -> int:
        return int(self._listener.getsockname()[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._listener.close()
        except OSError:
            pass

    def _bind_listener(self) -> None:
        candidates = [
            (self._config.proxy.socks_host, self._config.proxy.socks_port),
            (self._config.proxy.socks_host, 1086),
            (self._config.proxy.socks_host, 0),
        ]
        last_error = None
        for host, port in candidates:
            try:
                self._listener.bind((host, port))
                return
            except OSError as exc:
                last_error = exc
        raise RuntimeError(f"Unable to bind local SOCKS5 listener: {last_error}")

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, addr = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn, addr), name=f"lust-socks-client-{addr[1]}", daemon=True).start()

    def _handle_client(self, conn: socket.socket, addr) -> None:
        conn.settimeout(30.0)
        udp_assoc: UdpAssociation | None = None
        try:
            greeting = _read_exact(conn, 2)
            if greeting[0] != 5:
                raise ValueError("Unsupported SOCKS version.")
            methods = _read_exact(conn, greeting[1])
            if 0 not in methods:
                conn.sendall(b"\x05\xff")
                return
            conn.sendall(b"\x05\x00")
            request = _read_exact(conn, 4)
            if request[0] != 5:
                raise ValueError("Invalid SOCKS request version.")
            cmd = request[1]
            host, port = _read_socks_address(conn, request[3])
            if cmd == 1:
                self._handle_connect(conn, host, port)
                return
            if cmd == 3:
                udp_assoc = self._handle_udp_associate(conn)
                while conn.recv(1):
                    pass
                return
            conn.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        except Exception as exc:
            self._logger.debug("socks_client_error addr=%s detail=%s", addr, exc)
            try:
                conn.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            except Exception:
                pass
        finally:
            if udp_assoc is not None:
                udp_assoc.close()
            try:
                conn.close()
            except OSError:
                pass

    def _handle_connect(self, conn: socket.socket, host: str, port: int) -> None:
        channel_id = f"tcp-{secrets.token_hex(8)}"
        self._controller.send_frame({"op": "open_tcp", "channel_id": channel_id, "host": host, "port": port})
        self._controller.register_tcp_channel(channel_id, conn)
        conn.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")

        def _pump_local() -> None:
            try:
                while True:
                    data = conn.recv(65535)
                    if not data:
                        break
                    self._controller.send_frame({"op": "tcp_data", "channel_id": channel_id, "data_b64": _b64encode(data)})
            except Exception:
                pass
            finally:
                self._controller.close_channel(channel_id)

        threading.Thread(target=_pump_local, name=f"lust-tcp-{channel_id}", daemon=True).start()
        while conn.fileno() >= 0:
            time.sleep(0.5)
            if self._controller.failed_detail:
                raise RuntimeError(self._controller.failed_detail)

    def _handle_udp_associate(self, conn: socket.socket) -> UdpAssociation:
        assoc = UdpAssociation(self._controller, self._logger, self._config.proxy.socks_host)
        conn.sendall(b"\x05\x00\x00\x01" + socket.inet_aton(self._config.proxy.socks_host) + struct.pack("!H", assoc.bind_port))
        return assoc


class WintunRunner:
    def __init__(self, config: LustConfig, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger
        self._process: subprocess.Popen[str] | None = None
        self._adapter_name = "wintun"
        self._primary_route: PrimaryRoute | None = None
        self._edge_ip: str | None = None
        self._log_threads: list[threading.Thread] = []
        self._recent_logs: dict[str, deque[str]] = {
            "stdout": deque(maxlen=24),
            "stderr": deque(maxlen=24),
        }

    def start(self, *, socks_host: str, socks_port: int) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise RuntimeError("LuST Wintun mode is only supported on Windows.")
        self._require_installed_package()
        tun2socks_path = _runtime_binary("tun2socks.exe")
        wintun_dll_path = _runtime_binary("wintun.dll")
        if not tun2socks_path.exists():
            raise RuntimeError(f"Missing tun2socks runtime: {tun2socks_path}")
        if not wintun_dll_path.exists():
            raise RuntimeError(f"Missing Wintun runtime: {wintun_dll_path}")
        self._ensure_admin()
        self._primary_route = self._detect_primary_route()
        if self._config.tunnel.primary_interface:
            self._primary_route = PrimaryRoute(interface_alias=self._config.tunnel.primary_interface, next_hop=self._primary_route.next_hop)
        self._edge_ip = self._resolve_edge_host_ipv4()
        env = os.environ.copy()
        env["PATH"] = str(tun2socks_path.parent) + os.pathsep + env.get("PATH", "")
        args = [
            str(tun2socks_path),
            "-device",
            "wintun",
            "-proxy",
            f"socks5://{socks_host}:{socks_port}",
            "-interface",
            self._primary_route.interface_alias,
        ]
        self._logger.info("wintun_start argv=%s", args)
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **_subprocess_hidden_kwargs(),
        )
        self._start_log_reader("stdout", self._process.stdout)
        self._start_log_reader("stderr", self._process.stderr)
        self._wait_for_adapter("wintun")
        desired_name = self._config.tunnel.interface_name
        if desired_name.lower() != "wintun":
            self._rename_adapter("wintun", desired_name)
            self._wait_for_adapter(desired_name)
        self._adapter_name = desired_name
        self._configure_interface()
        time.sleep(1.0)
        self._wait_for_tunnel_ready()
        self.ensure_running()
        return {
            "mode": "wintun",
            "interface": self._adapter_name,
            "address_v4": self._config.tunnel.address_v4,
            "gateway_v4": self._config.tunnel.gateway_v4,
            "primary_interface": self._primary_route.interface_alias,
            "edge_bypass_ip": self._edge_ip,
            "tun2socks_pid": self._process.pid if self._process and self._process.pid is not None else None,
        }

    def _require_installed_package(self) -> None:
        if not getattr(sys, "frozen", False):
            return
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            os.environ.get("ProgramW6432", ""),
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
        ]
        install_roots = [Path(item).resolve() for item in candidates if item]
        for root in install_roots:
            try:
                exe_dir.relative_to(root)
                return
            except ValueError:
                continue
        raise RuntimeError("LuST Wintun mode requires the installed ONyX Client package. Portable builds support proxy mode only.")

    def ensure_running(self) -> None:
        if self._process is None:
            raise RuntimeError("Wintun runtime is not running.")
        code = self._process.poll()
        if code is not None:
            detail = self._recent_process_output()
            if detail:
                raise RuntimeError(f"tun2socks exited unexpectedly with code {code}: {detail}")
            raise RuntimeError(f"tun2socks exited unexpectedly with code {code}")

    def stop(self) -> None:
        try:
            self._teardown_routes()
        finally:
            if self._process is not None:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                self._process = None

    def _start_log_reader(self, stream_name: str, stream: TextIO | None) -> None:
        if stream is None:
            return

        def _run() -> None:
            try:
                for line in iter(stream.readline, ""):
                    text = line.strip()
                    if text:
                        self._recent_logs[stream_name].append(text)
                        self._logger.debug("tun2socks_%s %s", stream_name, text)
            except Exception:
                return

        thread = threading.Thread(target=_run, name=f"tun2socks-{stream_name}", daemon=True)
        thread.start()
        self._log_threads.append(thread)

    def _recent_process_output(self) -> str:
        stderr = list(self._recent_logs.get("stderr") or [])
        stdout = list(self._recent_logs.get("stdout") or [])
        combined = stderr if stderr else stdout
        if not combined:
            return ""
        return " | ".join(combined[-6:])

    def _ensure_admin(self) -> None:
        result = self._run_powershell("[bool](([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))")
        if result.lower() != "true":
            raise RuntimeError("LuST Wintun mode requires administrative privileges.")

    def _detect_primary_route(self) -> PrimaryRoute:
        script = (
            "Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
            "| Where-Object { $_.NextHop -and $_.InterfaceAlias -and $_.State -eq 'Alive' } "
            "| Sort-Object RouteMetric,InterfaceMetric "
            "| Select-Object -First 1 InterfaceAlias,NextHop "
            "| ConvertTo-Json -Compress"
        )
        raw = self._run_powershell(script)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Unable to detect primary route: {raw}") from exc
        interface_alias = str(parsed.get("InterfaceAlias") or "").strip()
        next_hop = str(parsed.get("NextHop") or "").strip()
        if not interface_alias or not next_hop:
            raise RuntimeError("Unable to detect active primary IPv4 route.")
        return PrimaryRoute(interface_alias=interface_alias, next_hop=next_hop)

    def _resolve_edge_host_ipv4(self) -> str:
        try:
            ipaddress.IPv4Address(self._config.endpoint.host)
            return self._config.endpoint.host
        except ValueError:
            pass
        infos = socket.getaddrinfo(self._config.endpoint.host, self._config.endpoint.port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if not infos:
            raise RuntimeError(f"Unable to resolve LuST edge host: {self._config.endpoint.host}")
        return str(infos[0][4][0])

    def _wait_for_adapter(self, name: str) -> None:
        deadline = time.time() + 15.0
        while time.time() < deadline:
            self.ensure_running()
            script = f"Get-NetAdapter -Name {_ps_quote(name)} -ErrorAction SilentlyContinue | Select-Object -First 1 Name | ConvertTo-Json -Compress"
            raw = self._run_powershell(script, allow_failure=True)
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
                resolved_name = parsed.get("Name") if isinstance(parsed, dict) else parsed
                if str(resolved_name or "").strip().lower() == name.lower():
                    return
            time.sleep(0.5)
        raise RuntimeError(f"Wintun adapter '{name}' did not appear in time.")

    def _rename_adapter(self, old_name: str, new_name: str) -> None:
        script = f"Rename-NetAdapter -Name {_ps_quote(old_name)} -NewName {_ps_quote(new_name)} -Confirm:$false | Out-Null"
        self._run_powershell(script)

    def _configure_interface(self) -> None:
        self._netsh(
            [
                "interface",
                "ipv4",
                "set",
                "address",
                f"name={self._adapter_name}",
                "source=static",
                f"addr={self._config.tunnel.address_v4}",
                f"mask={self._config.tunnel.netmask_v4}",
            ]
        )
        self._netsh(
            [
                "interface",
                "ipv4",
                "set",
                "subinterface",
                self._adapter_name,
                f"mtu={self._config.tunnel.mtu}",
                "store=active",
            ]
        )
        dns_servers = list(self._config.tunnel.dns_servers)
        if not dns_servers and self._config.dns_resolver:
            dns_servers.append(self._config.dns_resolver)
        if dns_servers:
            self._netsh(
                [
                    "interface",
                    "ipv4",
                    "set",
                    "dnsservers",
                    f"name={self._adapter_name}",
                    "source=static",
                    f"address={dns_servers[0]}",
                    "register=none",
                    "validate=no",
                ]
            )
            for index, dns_server in enumerate(dns_servers[1:], start=2):
                self._netsh(
                    [
                        "interface",
                        "ipv4",
                        "add",
                        "dnsservers",
                        f"name={self._adapter_name}",
                        f"address={dns_server}",
                        f"index={index}",
                        "validate=no",
                    ]
                )
        self._replace_route(f"{self._edge_ip}/32", self._primary_route.interface_alias, self._primary_route.next_hop)
        for prefix in self._config.tunnel.bypass_routes:
            self._replace_route(prefix, self._primary_route.interface_alias, self._primary_route.next_hop)
        self._replace_route("0.0.0.0/0", self._adapter_name, self._config.tunnel.gateway_v4)

    def _wait_for_tunnel_ready(self) -> None:
        deadline = time.time() + 8.0
        last_state = ""
        while time.time() < deadline:
            self.ensure_running()
            adapter_json = self._run_powershell(
                f"Get-NetAdapter -Name {_ps_quote(self._adapter_name)} -ErrorAction SilentlyContinue | "
                "Select-Object -First 1 Name,Status,ifIndex | ConvertTo-Json -Compress",
                allow_failure=True,
            )
            route_json = self._run_powershell(
                f"Get-NetRoute -AddressFamily IPv4 -InterfaceAlias {_ps_quote(self._adapter_name)} "
                "-DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
                "Select-Object -First 1 DestinationPrefix,NextHop,RouteMetric | ConvertTo-Json -Compress",
                allow_failure=True,
            )
            adapter_ok = False
            route_ok = False
            if adapter_json:
                try:
                    parsed = json.loads(adapter_json)
                    adapter_ok = str(parsed.get("Name") or "").strip().lower() == self._adapter_name.lower()
                except json.JSONDecodeError:
                    adapter_ok = False
            if route_json:
                try:
                    parsed = json.loads(route_json)
                    route_ok = str(parsed.get("DestinationPrefix") or "").strip() == "0.0.0.0/0"
                except json.JSONDecodeError:
                    route_ok = False
            if adapter_ok and route_ok:
                return
            last_state = f"adapter={adapter_json or 'missing'} route={route_json or 'missing'}"
            time.sleep(0.5)
        raise RuntimeError(f"LuST Wintun tunnel did not become active: {last_state or 'adapter/route missing'}")

    def _teardown_routes(self) -> None:
        if self._primary_route is not None and self._edge_ip:
            self._delete_route(f"{self._edge_ip}/32", self._primary_route.interface_alias, self._primary_route.next_hop)
        if self._primary_route is not None:
            for prefix in self._config.tunnel.bypass_routes:
                self._delete_route(prefix, self._primary_route.interface_alias, self._primary_route.next_hop)
        self._delete_route("0.0.0.0/0", self._adapter_name, self._config.tunnel.gateway_v4)

    def _replace_route(self, prefix: str, interface_name: str, gateway: str) -> None:
        self._delete_route(prefix, interface_name, gateway)
        self._netsh(
            [
                "interface",
                "ipv4",
                "add",
                "route",
                prefix,
                interface_name,
                gateway,
                "metric=1",
                "store=active",
            ]
        )

    def _delete_route(self, prefix: str, interface_name: str, gateway: str) -> None:
        self._netsh(
            [
                "interface",
                "ipv4",
                "delete",
                "route",
                prefix,
                interface_name,
                gateway,
            ],
            allow_failure=True,
        )

    def _netsh(self, args: list[str], *, allow_failure: bool = False) -> str:
        proc = subprocess.run(
            ["netsh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hidden_kwargs(),
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0 and not allow_failure:
            raise RuntimeError(output or f"netsh failed: {' '.join(args)}")
        return output

    def _run_powershell(self, script: str, *, allow_failure: bool = False) -> str:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_hidden_kwargs(),
        )
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0 and not allow_failure:
            raise RuntimeError(output or f"powershell failed: {script}")
        return output


def run(config_path: str, interval_seconds: float, verbose: bool, probe_once: bool) -> int:
    logger = configure_logging(verbose)
    stop_event = threading.Event()
    install_signal_handlers(stop_event, logger)
    try:
        config = load_config(config_path)
        verify = build_tls_verify(config)
    except Exception as exc:
        logger.error("config_error %s", exc)
        write_status(state="error", config=None, detail=f"config_error: {exc}")
        return 2
    logger.info("config_loaded peer_id=%s base_url=%s tunnel_mode=%s", config.client.peer_id, config.base_url, config.tunnel.mode)
    write_status(state="starting", config=config, detail="client starting")
    try:
        probe_meta = probe_endpoint(config, verify, logger)
    except Exception as exc:
        logger.error("startup_probe_failed %s", exc)
        write_status(state="error", config=config, detail=f"startup_probe_failed: {exc}")
        return 1
    if probe_once:
        write_status(state="running", config=config, detail="probe succeeded", response=probe_meta)
        logger.info("probe_once_complete peer_id=%s", config.client.peer_id)
        return 0
    controller = EdgeController(config, logger, verify)
    socks_server: Socks5Server | None = None
    tunnel_runner: WintunRunner | None = None
    try:
        session_meta = controller.start()
        socks_server = Socks5Server(controller, config, logger)
        socks_server.start()
        proxy_meta = {
            "mode": "socks5",
            "host": socks_server.listen_host,
            "port": socks_server.listen_port,
            "internal_only": True,
        }
        tunnel_meta: dict[str, Any] = {
            "mode": "proxy",
            "interface": "",
            "socks5_upstream": {"host": socks_server.listen_host, "port": socks_server.listen_port},
        }
        if config.tunnel.mode == "wintun":
            tunnel_runner = WintunRunner(config, logger)
            tunnel_meta = tunnel_runner.start(socks_host=socks_server.listen_host, socks_port=socks_server.listen_port)
            tunnel_meta["socks5_upstream"] = {"host": socks_server.listen_host, "port": socks_server.listen_port}
            logger.info("wintun_ready interface=%s edge_bypass_ip=%s", tunnel_meta.get("interface"), tunnel_meta.get("edge_bypass_ip"))
        else:
            logger.info("socks_ready host=%s port=%s session_id=%s", socks_server.listen_host, socks_server.listen_port, controller.session_id)
        write_status(
            state="running",
            config=config,
            detail="LuST transport is active",
            response={**probe_meta, **session_meta},
            proxy=proxy_meta,
            tunnel=tunnel_meta,
        )
        while not stop_event.is_set():
            if controller.failed_detail:
                raise RuntimeError(controller.failed_detail)
            if tunnel_runner is not None:
                tunnel_runner.ensure_running()
            time.sleep(max(1.0, interval_seconds))
    except Exception as exc:
        logger.warning("runtime_failed %s", exc)
        write_status(state="degraded", config=config, detail=f"runtime_failed: {exc}", response=probe_meta)
        return 1
    finally:
        if tunnel_runner is not None:
            tunnel_runner.stop()
        if socks_server is not None:
            socks_server.stop()
        controller.stop()
        write_status(state="stopped", config=config, detail="client stopped")
        logger.info("client_stopped peer_id=%s", config.client.peer_id)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ONyX LuST client")
    parser.add_argument("--config", required=True, help="Path to the issued LuST JSON config.")
    parser.add_argument("--interval-seconds", type=float, default=15.0, help="Polling interval for runtime health checks.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    parser.add_argument("--probe-once", action="store_true", help="Perform a single startup probe and exit.")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return run(config_path=args.config, interval_seconds=max(3.0, float(args.interval_seconds)), verbose=bool(args.verbose), probe_once=bool(args.probe_once))


if __name__ == "__main__":
    raise SystemExit(main())
