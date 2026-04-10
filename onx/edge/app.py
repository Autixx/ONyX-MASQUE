from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from onx.edge.config import EdgeRuntimeConfig, load_edge_config
from onx.edge.runtime import edge_session_manager
from onx.edge.upstream import UpstreamGatewayRelay
from onx.schemas.client_lust import LustClientSessionRead


def _extract_bearer_token(authorization: str | None) -> str | None:
    value = str(authorization or "").strip()
    if not value:
        return None
    parts = value.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))


def _verify_signed_token(config: EdgeRuntimeConfig, token: str) -> dict:
    parts = str(token or "").strip().split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed LuST token.")
    signing_input = ".".join(parts[:2]).encode("ascii")
    actual = _b64decode(parts[2])
    expected = hmac.new(config.access_token_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, actual):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LuST token signature.")
    payload = json.loads(_b64decode(parts[1]).decode("utf-8"))
    now = int(datetime.now(timezone.utc).timestamp())
    if str(payload.get("iss") or "") != config.trust.token_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected LuST token issuer.")
    if int(payload.get("nbf") or 0) > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LuST token is not active yet.")
    if int(payload.get("exp") or 0) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LuST token has expired.")
    return payload


def _normalize_fingerprint(value: str | None) -> str:
    return str(value or "").strip().replace(":", "").lower()


def _fingerprint_from_client_cert(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    pem = unquote(raw).strip()
    if not pem:
        return ""
    body = []
    for line in pem.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-----BEGIN ") or stripped.startswith("-----END "):
            continue
        body.append(stripped)
    if not body:
        return ""
    try:
        der = base64.b64decode("".join(body))
    except Exception:  # noqa: BLE001
        return ""
    return hashlib.sha256(der).hexdigest().lower()


def _resolve_client_claims(
    config: EdgeRuntimeConfig,
    *,
    authorization: str | None,
    client_verify: str | None,
    client_fingerprint: str | None,
    client_cert: str | None,
):
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing LuST bearer token.")
    if str(client_verify or "").strip().upper() != "SUCCESS":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client certificate verification failed.")
    claims = _verify_signed_token(config, token)
    if str(claims.get("aud") or "") != config.trust.token_audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected LuST token audience.")
    if str(claims.get("typ") or "") != "lust_access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected LuST token type.")
    presented_fingerprint = _fingerprint_from_client_cert(client_cert) or _normalize_fingerprint(client_fingerprint)
    expected_fingerprint = _normalize_fingerprint(claims.get("cert_fingerprint_sha256"))
    if not presented_fingerprint or presented_fingerprint != expected_fingerprint:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client certificate fingerprint mismatch.")
    if str(claims.get("service_id") or "") != config.service.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LuST service id is not valid for this edge.")
    return claims


def _resolve_upstream_claims(
    config: EdgeRuntimeConfig,
    *,
    authorization: str | None,
):
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing LuST upstream bearer token.")
    claims = _verify_signed_token(config, token)
    if str(claims.get("aud") or "") != config.trust.upstream_token_audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected LuST upstream token audience.")
    if str(claims.get("typ") or "") != "lust_upstream":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected LuST upstream token type.")
    if str(claims.get("target_service_id") or "") != config.service.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LuST upstream target service mismatch.")
    return claims


def _serialize_session(config: EdgeRuntimeConfig, claims: dict) -> LustClientSessionRead:
    return LustClientSessionRead(
        peer_id=str(claims.get("peer_id") or ""),
        username="",
        service_id=config.service.id,
        service_name=config.service.name,
        node_id=config.service.node_id,
        stream_path=config.service.stream_path,
        dns_resolver=config.service.dns_resolver,
        connected_at=datetime.now(timezone.utc),
    )


def create_app(config: EdgeRuntimeConfig | None = None) -> FastAPI:
    startup_error = ""
    if config is None:
        try:
            edge_config = load_edge_config()
        except Exception as exc:  # noqa: BLE001
            startup_error = str(exc)
            edge_config = EdgeRuntimeConfig.model_validate(
                {
                    "service": {
                        "id": "unconfigured",
                        "name": "unconfigured",
                        "node_id": "unconfigured",
                        "public_host": "localhost",
                        "public_port": 443,
                        "tls_server_name": "localhost",
                        "path": "/lust",
                        "stream_path": "/lust/stream",
                        "dns_resolver": None,
                    }
                }
            )
    else:
        edge_config = config

    app = FastAPI(title="ONyX LuST edge", version="0.2.0")
    upstream_relay = UpstreamGatewayRelay(edge_config)

    def _require_configured() -> None:
        if startup_error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"LuST edge is not configured: {startup_error}")

    @app.get("/health")
    def health() -> dict:
        session_stats = edge_session_manager.stats()
        return {
            "status": "ok" if not startup_error else "unconfigured",
            "service_id": edge_config.service.id,
            "transport": edge_config.transport,
            "protocol": edge_config.protocol,
            "role": edge_config.service.role,
            **session_stats,
            "startup_error": startup_error or None,
        }

    @app.get(edge_config.service.path, response_model=LustClientSessionRead)
    def lust_session(
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ) -> LustClientSessionRead:
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        return _serialize_session(edge_config, claims)

    @app.post(f"{edge_config.service.path}/session/open", status_code=status.HTTP_200_OK)
    async def lust_open_session(
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ) -> dict:
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        session = edge_session_manager.open_session(claims)
        if upstream_relay.enabled():
            try:
                upstream = await upstream_relay.attach_session(session)
                if upstream is not None:
                    session.metadata["placement"] = {
                        "mode": "gateway-relay",
                        "egress_service_id": str(upstream["member"].get("service_id") or ""),
                        "egress_node_id": str(upstream["member"].get("node_id") or ""),
                    }
            except httpx.HTTPError as exc:
                await edge_session_manager.close_session(session.session_id)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LuST upstream open failed: {exc}") from exc
            except RuntimeError as exc:
                await edge_session_manager.close_session(session.session_id)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return {
            "session_id": session.session_id,
            "peer_id": claims.get("peer_id"),
            "service_id": claims.get("service_id"),
            "transport": edge_config.transport,
            "protocol": edge_config.protocol,
            "poll_timeout_seconds": 20,
            "placement": dict(session.metadata.get("placement") or {}),
        }

    @app.post(f"{edge_config.service.path}/frame", status_code=status.HTTP_200_OK)
    async def lust_post_frame(
        payload: dict,
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ) -> dict:
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        session_id = str(payload.get("session_id") or "").strip()
        session = edge_session_manager.get_session(session_id, claims)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST session not found.")
        try:
            if session.metadata.get("upstream"):
                return await upstream_relay.forward_frame(session, payload)
            return await edge_session_manager.handle_frame(session.session_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get(f"{edge_config.service.path}/frame/poll", status_code=status.HTTP_200_OK)
    async def lust_poll_frame(
        session_id: str = Query(...),
        timeout: float = Query(default=20.0, ge=1.0, le=60.0),
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ):
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        session = edge_session_manager.get_session(session_id, claims)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST session not found.")
        if session.metadata.get("upstream"):
            try:
                frame = await upstream_relay.poll_frame(session, timeout=timeout)
            except RuntimeError as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        else:
            frame = await edge_session_manager.poll_frame(session.session_id, timeout_seconds=timeout)
        if frame is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return JSONResponse(status_code=status.HTTP_200_OK, content=frame)

    @app.post(f"{edge_config.service.path}/session/close", status_code=status.HTTP_204_NO_CONTENT)
    async def lust_close_session(
        payload: dict,
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ) -> Response:
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        session_id = str(payload.get("session_id") or "").strip()
        session = edge_session_manager.get_session(session_id, claims)
        if session is not None:
            if session.metadata.get("upstream"):
                try:
                    await upstream_relay.close_session(session)
                except Exception:
                    pass
            await edge_session_manager.close_session(session.session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get(edge_config.service.stream_path, status_code=status.HTTP_200_OK)
    async def lust_stream_probe(
        authorization: str | None = Header(default=None),
        x_ssl_client_verify: str | None = Header(default=None),
        x_ssl_client_fingerprint: str | None = Header(default=None),
        x_ssl_client_cert: str | None = Header(default=None),
    ):
        _require_configured()
        claims = _resolve_client_claims(
            edge_config,
            authorization=authorization,
            client_verify=x_ssl_client_verify,
            client_fingerprint=x_ssl_client_fingerprint,
            client_cert=x_ssl_client_cert,
        )
        session = _serialize_session(edge_config, claims)

        async def _event_source():
            hello = {"type": "hello", **session.model_dump(mode="json")}
            yield "event: hello\n"
            yield f"data: {json.dumps(hello, separators=(',', ':'), ensure_ascii=True)}\n\n"
            while True:
                payload = {
                    "type": "ping",
                    "peer_id": session.peer_id,
                    "service_id": session.service_id,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                yield "event: ping\n"
                yield f"data: {json.dumps(payload, separators=(',', ':'), ensure_ascii=True)}\n\n"
                await asyncio.sleep(15)

        return StreamingResponse(
            _event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(f"{edge_config.service.path}/upstream/session/open", status_code=status.HTTP_200_OK)
    def lust_open_upstream_session(
        authorization: str | None = Header(default=None),
    ) -> dict:
        _require_configured()
        claims = _resolve_upstream_claims(edge_config, authorization=authorization)
        session = edge_session_manager.open_session(claims)
        return {
            "session_id": session.session_id,
            "gateway_service_id": claims.get("gateway_service_id"),
            "service_id": edge_config.service.id,
            "transport": edge_config.transport,
            "protocol": edge_config.protocol,
            "poll_timeout_seconds": 20,
        }

    @app.post(f"{edge_config.service.path}/upstream/frame", status_code=status.HTTP_200_OK)
    async def lust_post_upstream_frame(
        payload: dict,
        authorization: str | None = Header(default=None),
    ) -> dict:
        _require_configured()
        _resolve_upstream_claims(edge_config, authorization=authorization)
        session_id = str(payload.get("session_id") or "").strip()
        session = edge_session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST upstream session not found.")
        try:
            return await edge_session_manager.handle_frame(session.session_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get(f"{edge_config.service.path}/upstream/frame/poll", status_code=status.HTTP_200_OK)
    async def lust_poll_upstream_frame(
        session_id: str = Query(...),
        timeout: float = Query(default=20.0, ge=1.0, le=60.0),
        authorization: str | None = Header(default=None),
    ):
        _require_configured()
        _resolve_upstream_claims(edge_config, authorization=authorization)
        session = edge_session_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LuST upstream session not found.")
        frame = await edge_session_manager.poll_frame(session.session_id, timeout_seconds=timeout)
        if frame is None:
            return JSONResponse(status_code=status.HTTP_200_OK, content={"ok": True, "op": "noop"})
        return JSONResponse(status_code=status.HTTP_200_OK, content=frame)

    @app.post(f"{edge_config.service.path}/upstream/session/close", status_code=status.HTTP_204_NO_CONTENT)
    async def lust_close_upstream_session(
        payload: dict,
        authorization: str | None = Header(default=None),
    ) -> Response:
        _require_configured()
        _resolve_upstream_claims(edge_config, authorization=authorization)
        session_id = str(payload.get("session_id") or "").strip()
        session = edge_session_manager.get_session(session_id)
        if session is not None:
            await edge_session_manager.close_session(session.session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/{requested_path:path}")
    def deny_unknown(requested_path: str, request: Request):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Forbidden.", "path": "/" + requested_path.lstrip("/"), "host": request.headers.get("host")},
        )

    return app


app = create_app()
