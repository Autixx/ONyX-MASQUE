from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str | None) -> bytes:
    raw = str(value or "").encode("ascii")
    return base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))


@dataclass(slots=True)
class EdgeChannel:
    channel_id: str
    network: str
    host: str
    port: int
    tcp_writer: asyncio.StreamWriter | None = None
    tcp_reader_task: asyncio.Task | None = None
    udp_transport: asyncio.DatagramTransport | None = None


@dataclass(slots=True)
class EdgeSession:
    session_id: str
    claims: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    downstream: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    channels: dict[str, EdgeChannel] = field(default_factory=dict)


class _UdpRelayProtocol(asyncio.DatagramProtocol):
    def __init__(self, manager: "EdgeSessionManager", session_id: str, channel_id: str, host: str, port: int) -> None:
        self._manager = manager
        self._session_id = session_id
        self._channel_id = channel_id
        self._host = host
        self._port = port

    def datagram_received(self, data: bytes, _addr) -> None:
        frame = {
            "op": "udp_data",
            "channel_id": self._channel_id,
            "host": self._host,
            "port": self._port,
            "data_b64": _b64encode(data),
        }
        self._manager.queue_frame(self._session_id, frame)

    def error_received(self, exc: Exception) -> None:
        frame = {
            "op": "error",
            "channel_id": self._channel_id,
            "network": "udp",
            "detail": str(exc),
        }
        self._manager.queue_frame(self._session_id, frame)


_LOG = logging.getLogger("onx.lust.edge")


class EdgeSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, EdgeSession] = {}

    def open_session(self, claims: dict[str, Any]) -> EdgeSession:
        session_id = secrets.token_urlsafe(18)
        session = EdgeSession(session_id=session_id, claims=dict(claims))
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str, claims: dict[str, Any] | None = None) -> EdgeSession | None:
        session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            return None
        if claims is None:
            return session
        for key in ("user_id", "device_id", "peer_id", "service_id", "node_id", "cert_fingerprint_sha256"):
            if str(session.claims.get(key) or "") != str(claims.get(key) or ""):
                return None
        return session

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(str(session_id or "").strip(), None)
        if session is None:
            return
        for channel in list(session.channels.values()):
            await self._close_channel(session, channel.channel_id)

    def queue_frame(self, session_id: str, frame: dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.updated_at = datetime.now(timezone.utc)
        session.downstream.put_nowait(frame)

    def stats(self) -> dict[str, Any]:
        sessions = list(self._sessions.values())
        upstream_sessions = sum(1 for item in sessions if item.metadata.get("upstream"))
        return {
            "active_sessions": len(sessions),
            "upstream_sessions": upstream_sessions,
        }

    async def poll_frame(self, session_id: str, *, timeout_seconds: float = 20.0) -> dict[str, Any] | None:
        session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            return None
        try:
            frame = await asyncio.wait_for(session.downstream.get(), timeout=max(1.0, float(timeout_seconds)))
        except TimeoutError:
            return None
        session.updated_at = datetime.now(timezone.utc)
        return frame

    async def handle_frame(self, session_id: str, frame: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(session_id or "").strip())
        if session is None:
            raise ValueError("Unknown LuST session.")
        session.updated_at = datetime.now(timezone.utc)
        op = str(frame.get("op") or "").strip().lower()
        if op == "open_tcp":
            return await self._open_tcp(session, frame)
        if op == "tcp_data":
            return await self._tcp_data(session, frame)
        if op == "open_udp":
            return await self._open_udp(session, frame)
        if op == "udp_data":
            return await self._udp_data(session, frame)
        if op == "close":
            return await self._close(session, frame)
        if op == "ping":
            return {"ok": True, "op": "pong"}
        raise ValueError(f"Unsupported LuST frame op: {op}")

    async def _open_tcp(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        channel_id = self._channel_id(frame)
        host = self._host(frame)
        port = self._port(frame)
        if channel_id in session.channels:
            return {"ok": True, "channel_id": channel_id, "network": "tcp", "reused": True}
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError as exc:
            message = f"open_tcp {host}:{port} channel={channel_id} failed: {exc}"
            _LOG.warning(message)
            raise OSError(message) from exc
        channel = EdgeChannel(channel_id=channel_id, network="tcp", host=host, port=port, tcp_writer=writer)
        channel.tcp_reader_task = asyncio.create_task(self._tcp_reader_loop(session.session_id, channel_id, reader, host, port))
        session.channels[channel_id] = channel
        return {"ok": True, "channel_id": channel_id, "network": "tcp"}

    async def _tcp_data(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        channel = self._require_channel(session, frame, expected_network="tcp")
        data = _b64decode(frame.get("data_b64"))
        if channel.tcp_writer is None:
            raise ValueError("TCP channel is not writable.")
        try:
            channel.tcp_writer.write(data)
            await channel.tcp_writer.drain()
        except OSError as exc:
            message = (
                f"tcp_data {channel.channel_id} {channel.host}:{channel.port} "
                f"bytes={len(data)} failed: {exc}"
            )
            _LOG.warning(message)
            raise OSError(message) from exc
        return {"ok": True, "channel_id": channel.channel_id, "bytes": len(data)}

    async def _open_udp(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        channel_id = self._channel_id(frame)
        host = self._host(frame)
        port = self._port(frame)
        if channel_id in session.channels:
            return {"ok": True, "channel_id": channel_id, "network": "udp", "reused": True}
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UdpRelayProtocol(self, session.session_id, channel_id, host, port),
                remote_addr=(host, port),
            )
        except OSError as exc:
            message = f"open_udp {host}:{port} channel={channel_id} failed: {exc}"
            _LOG.warning(message)
            raise OSError(message) from exc
        channel = EdgeChannel(
            channel_id=channel_id,
            network="udp",
            host=host,
            port=port,
            udp_transport=transport,
        )
        session.channels[channel_id] = channel
        return {"ok": True, "channel_id": channel_id, "network": "udp"}

    async def _udp_data(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        channel = self._require_channel(session, frame, expected_network="udp")
        data = _b64decode(frame.get("data_b64"))
        if channel.udp_transport is None:
            raise ValueError("UDP channel is not writable.")
        try:
            channel.udp_transport.sendto(data)
        except OSError as exc:
            message = (
                f"udp_data {channel.channel_id} {channel.host}:{channel.port} "
                f"bytes={len(data)} failed: {exc}"
            )
            _LOG.warning(message)
            raise OSError(message) from exc
        return {"ok": True, "channel_id": channel.channel_id, "bytes": len(data)}

    async def _close(self, session: EdgeSession, frame: dict[str, Any]) -> dict[str, Any]:
        channel_id = self._channel_id(frame)
        await self._close_channel(session, channel_id)
        return {"ok": True, "channel_id": channel_id, "closed": True}

    async def _close_channel(self, session: EdgeSession, channel_id: str) -> None:
        channel = session.channels.pop(channel_id, None)
        if channel is None:
            return
        if channel.tcp_writer is not None:
            channel.tcp_writer.close()
            try:
                await channel.tcp_writer.wait_closed()
            except Exception:
                pass
        if channel.tcp_reader_task is not None:
            channel.tcp_reader_task.cancel()
        if channel.udp_transport is not None:
            channel.udp_transport.close()

    async def _tcp_reader_loop(self, session_id: str, channel_id: str, reader: asyncio.StreamReader, host: str, port: int) -> None:
        bytes_read = 0
        close_detail = "eof"
        try:
            while True:
                chunk = await reader.read(65535)
                if not chunk:
                    break
                bytes_read += len(chunk)
                self.queue_frame(
                    session_id,
                    {
                        "op": "tcp_data",
                        "channel_id": channel_id,
                        "host": host,
                        "port": port,
                        "data_b64": _b64encode(chunk),
                    },
                )
        except Exception as exc:
            close_detail = f"error:{exc}"
            self.queue_frame(
                session_id,
                {
                    "op": "error",
                    "channel_id": channel_id,
                    "network": "tcp",
                    "detail": str(exc),
                },
            )
        finally:
            self.queue_frame(
                session_id,
                {
                    "op": "close",
                    "channel_id": channel_id,
                    "network": "tcp",
                    "detail": close_detail,
                    "bytes": bytes_read,
                },
            )
            session = self._sessions.get(session_id)
            if session is not None:
                await self._close_channel(session, channel_id)

    @staticmethod
    def _channel_id(frame: dict[str, Any]) -> str:
        value = str(frame.get("channel_id") or "").strip()
        if not value:
            raise ValueError("channel_id is required.")
        return value

    @staticmethod
    def _host(frame: dict[str, Any]) -> str:
        value = str(frame.get("host") or "").strip()
        if not value:
            raise ValueError("host is required.")
        return value

    @staticmethod
    def _port(frame: dict[str, Any]) -> int:
        value = int(frame.get("port") or 0)
        if value <= 0:
            raise ValueError("port must be positive.")
        return value

    @staticmethod
    def _require_channel(session: EdgeSession, frame: dict[str, Any], *, expected_network: str) -> EdgeChannel:
        channel_id = EdgeSessionManager._channel_id(frame)
        channel = session.channels.get(channel_id)
        if channel is None:
            raise ValueError(f"Unknown {expected_network} channel: {channel_id}")
        if channel.network != expected_network:
            raise ValueError(f"Channel {channel_id} is not a {expected_network} channel.")
        return channel


edge_session_manager = EdgeSessionManager()
