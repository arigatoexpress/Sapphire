import asyncio
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable, List, Optional, Set

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


def _build_cors_allowlist() -> set[str]:
    raw = str(
        os.getenv(
            "ALPHA_API_CORS_ORIGINS",
            (
                "https://sapphirebook-web-s77j6bxyra-uc.a.run.app,"
                "https://sapphirealpha.xyz,"
                "https://sapphire-479610.web.app,"
                "http://localhost:5173,"
                "http://127.0.0.1:5173"
            ),
        )
    ).strip()
    values = [entry.strip() for entry in raw.replace(";", ",").split(",")]
    return {entry for entry in values if entry}


def _apply_cors_headers(request: web.Request, response: web.StreamResponse) -> None:
    origin = (request.headers.get("Origin") or "").strip()
    allowed = request.app.get("cors_allowlist", set())
    if not origin:
        return
    if "*" in allowed or origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type,Authorization,X-Sapphire-Webhook-Secret,X-Sapphire-Control-Token,X-Telegram-Bot-Api-Secret-Token"
        )


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    _apply_cors_headers(request, response)
    return response


async def health_check(request):
    """Liveness probe."""
    return web.Response(text="OK", status=200)


async def readiness_check(request):
    """Readiness probe."""
    return web.Response(text="READY", status=200)


async def telegram_webhook(request):
    """Receive Telegram webhook updates and pass them to the bot update handler."""
    expected_secret = str(request.app.get("telegram_webhook_secret") or "").strip()
    if not expected_secret:
        logger.warning("Telegram webhook rejected: secret not configured")
        return web.Response(text="WEBHOOK_SECRET_NOT_CONFIGURED", status=503)

    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if received_secret != expected_secret:
        return web.Response(text="FORBIDDEN", status=403)

    try:
        update = await request.json()
    except Exception:
        return web.Response(text="BAD_REQUEST", status=400)

    handler = request.app.get("telegram_update_handler")
    if handler:
        try:
            await handler(update)
        except Exception as exc:
            logger.error(f"Telegram webhook handler error: {exc}")

    return web.Response(text="OK", status=200)


def _extract_control_token(request: web.Request) -> str:
    token = (request.headers.get("X-Sapphire-Control-Token") or "").strip()
    if token:
        return token

    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        bearer_token = auth[7:].strip()
        if bearer_token:
            return bearer_token

    return ""


def _require_control_token(request: web.Request) -> Optional[web.Response]:
    """Require control token for admin/write operations."""
    expected_token = str(request.app.get("control_api_token") or "").strip()
    if not expected_token:
        return web.json_response({"ok": False, "error": "control_token_unconfigured"}, status=503)

    provided_token = _extract_control_token(request)
    if provided_token != expected_token:
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    return None


def _require_dashboard_access(request: web.Request) -> Optional[web.Response]:
    """Allow access if request comes from an allowed CORS origin OR has a valid control token.

    Read-only dashboard endpoints use this lighter check so the public frontend
    can fetch operational state without embedding the control token in the JS bundle.
    Requests without a recognized Origin header still need the control token (e.g. curl).
    """
    # Control token always grants access
    expected_token = str(request.app.get("control_api_token") or "").strip()
    if expected_token:
        provided_token = _extract_control_token(request)
        if provided_token == expected_token:
            return None

    # Allow requests from whitelisted dashboard origins
    origin = (request.headers.get("Origin") or "").strip()
    allowed = request.app.get("cors_allowlist", set())
    if origin and origin in allowed:
        return None

    # Referer fallback (for same-origin GET requests that don't send Origin)
    referer = (request.headers.get("Referer") or "").strip()
    if referer:
        for allowed_origin in allowed:
            if referer.startswith(allowed_origin):
                return None

    return web.json_response({"ok": False, "error": "forbidden"}, status=403)


def _extract_shared_secret(
    request: web.Request, payload: dict[str, Any], header_name: str
) -> str:
    header_secret = (request.headers.get(header_name) or "").strip()
    if header_secret:
        return header_secret

    for key in ("secret", "passphrase", "token", "webhook_secret"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""





async def market_ohlc(request: web.Request) -> web.Response:
    handler = request.app.get("market_ohlc_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    query = request.rel_url.query
    payload = {
        "venue": query.get("venue", "ASTER"),
        "symbol": query.get("symbol", "SOL"),
        "interval": query.get("interval", "1m"),
        "limit": query.get("limit", "120"),
    }
    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"OHLC handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)

    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def platform_status(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("platform_status_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Platform status handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def control_status(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("control_status_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Control status handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def routing_info(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("routing_info_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Routing handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def performance_stats(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("performance_stats_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Performance stats handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def system_logs(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("system_logs_handler")
    if handler is None:
        return web.json_response([], status=200)

    limit = request.rel_url.query.get("limit", "80")
    try:
        result = await handler({"limit": limit})
    except Exception as exc:
        logger.error(f"System logs handler error: {exc}")
        return web.json_response([], status=200)

    if isinstance(result, list):
        return web.json_response(result, status=200)
    if isinstance(result, dict):
        payload = result.get("logs")
        if isinstance(payload, list):
            return web.json_response(payload, status=200)
    return web.json_response([], status=200)





async def _read_json_payload(request: web.Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


async def forum_topics(request: web.Request) -> web.Response:
    if request.method == "GET":
        handler = request.app.get("forum_topics_handler")
        if handler is None:
            return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
        payload: dict[str, Any] = {
            "lane": request.rel_url.query.get("lane", ""),
            "state": request.rel_url.query.get("state", ""),
            "tag": request.rel_url.query.get("tag", ""),
            "q": request.rel_url.query.get("q", ""),
            "limit": request.rel_url.query.get("limit", "80"),
        }
    else:
        handler = request.app.get("forum_create_topic_handler")
        if handler is None:
            return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
        denied = _require_control_token(request)
        if denied is not None:
            return denied
        payload = await _read_json_payload(request)

    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Forum topics handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)

    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def forum_topic_detail(request: web.Request) -> web.Response:
    handler = request.app.get("forum_topic_detail_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    topic_id = str(request.match_info.get("topic_id", "")).strip()
    payload = {"topic_id": topic_id}
    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Forum topic detail handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)

    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def forum_replies(request: web.Request) -> web.Response:
    handler = request.app.get("forum_replies_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    denied = _require_control_token(request)
    if denied is not None:
        return denied
    payload = await _read_json_payload(request)
    payload["topic_id"] = str(request.match_info.get("topic_id", "")).strip()
    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Forum replies handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)

    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def forum_scout_status(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("forum_scout_status_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Forum scout status handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def forum_scout_register(request: web.Request) -> web.Response:
    handler = request.app.get("forum_scout_register_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    denied = _require_control_token(request)
    if denied is not None:
        return denied
    payload = await _read_json_payload(request)
    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Forum scout register handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def forum_scout_publish(request: web.Request) -> web.Response:
    handler = request.app.get("forum_scout_publish_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    denied = _require_control_token(request)
    if denied is not None:
        return denied
    payload = await _read_json_payload(request)
    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Forum scout publish handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def security_skills_status(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("security_skills_status_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Security skills status handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def security_skills_scan(request: web.Request) -> web.Response:
    handler = request.app.get("security_skills_scan_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    denied = _require_control_token(request)
    if denied is not None:
        return denied
    if request.method == "GET":
        upload_value = str(request.rel_url.query.get("upload_if_missing", "false")).strip().lower()
        payload = {
            "skill": request.rel_url.query.get("skill", ""),
            "upload_if_missing": upload_value in {"1", "true", "yes", "on"},
        }
    else:
        payload = await _read_json_payload(request)

    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"Security skills scan handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


async def prediction_dashboard(request: web.Request) -> web.Response:
    denied = _require_dashboard_access(request)
    if denied is not None:
        return denied
    handler = request.app.get("prediction_dashboard_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)
    try:
        result = await handler({})
    except Exception as exc:
        logger.error(f"Prediction dashboard handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)
    if isinstance(result, dict):
        status = 400 if result.get("error") else 200
        return web.json_response({"ok": status == 200, **result}, status=status)
    return web.json_response({"ok": True}, status=200)


# ── WebSocket Dashboard Push ─────────────────────────────────────────

_WS_PUSH_INTERVAL = float(os.getenv("WS_PUSH_INTERVAL", "5"))  # seconds
_WS_MAX_CLIENTS = int(os.getenv("WS_MAX_CLIENTS", "50"))


async def _ws_dashboard_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket endpoint that pushes dashboard snapshots to connected frontends.

    The frontend connects once, receives an initial snapshot immediately, then
    gets periodic pushes every WS_PUSH_INTERVAL seconds.  The client can send
    'ping' for keep-alive; all other incoming data is ignored.

    Origin is validated against the CORS allowlist to prevent abuse.
    """
    ws = web.WebSocketResponse(heartbeat=30.0)

    # Validate origin
    origin = (request.headers.get("Origin") or "").strip()
    allowed: set[str] = request.app.get("cors_allowlist", set())
    if origin and allowed and "*" not in allowed and origin not in allowed:
        return web.Response(text="FORBIDDEN", status=403)

    clients: list[web.WebSocketResponse] = request.app["_ws_clients"]
    if len(clients) >= _WS_MAX_CLIENTS:
        return web.Response(text="TOO_MANY_CONNECTIONS", status=503)

    await ws.prepare(request)
    clients.append(ws)
    logger.info(f"WS client connected (origin={origin}). Total: {len(clients)}")

    try:
        # Send initial snapshot immediately
        snapshot = await _build_dashboard_snapshot(request.app)
        await ws.send_json({"type": "init", **snapshot})

        # Keep alive: respond to pings, ignore other messages
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_str("pong")
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        if ws in clients:
            clients.remove(ws)
        logger.info(f"WS client disconnected. Total: {len(clients)}")

    return ws


async def _build_dashboard_snapshot(app: web.Application) -> dict[str, Any]:
    """Gather a full dashboard snapshot from registered handlers.

    Calls the same handlers the REST endpoints use so the frontend gets
    identical data structures.  Each handler is called with best-effort —
    if any fails the corresponding key is set to None.
    """
    async def _safe_call(key: str, payload: dict[str, Any] | None = None) -> Any:
        handler = app.get(key)
        if handler is None:
            return None
        try:
            return await handler(payload or {})
        except Exception as exc:
            logger.debug(f"WS snapshot handler '{key}' error: {exc}")
            return None

    control, perf, platforms = await asyncio.gather(
        _safe_call("control_status_handler"),
        _safe_call("performance_stats_handler"),
        _safe_call("platform_status_handler"),
        return_exceptions=True,
    )

    return {
        "control": control if isinstance(control, dict) else None,
        "performance": perf if isinstance(perf, dict) else None,
        "platforms": platforms if isinstance(platforms, dict) else None,
        "timestamp": time.time(),
    }


async def _ws_push_loop(app: web.Application) -> None:
    """Background task that pushes snapshots to all connected WS clients."""
    while True:
        await asyncio.sleep(_WS_PUSH_INTERVAL)
        clients: list[web.WebSocketResponse] = app.get("_ws_clients", [])
        if not clients:
            continue

        try:
            snapshot = await _build_dashboard_snapshot(app)
            payload = json.dumps({"type": "snapshot", **snapshot})
        except Exception as exc:
            logger.debug(f"WS push snapshot build error: {exc}")
            continue

        dead: list[web.WebSocketResponse] = []
        for ws in clients:
            if ws.closed:
                dead.append(ws)
                continue
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            if ws in clients:
                clients.remove(ws)


async def _start_ws_push(app: web.Application) -> None:
    app["_ws_push_task"] = asyncio.create_task(_ws_push_loop(app))


async def _stop_ws_push(app: web.Application) -> None:
    task = app.get("_ws_push_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    # Close any remaining WS connections
    for ws in list(app.get("_ws_clients", [])):
        if not ws.closed:
            await ws.close()


async def start_health_server(
    telegram_update_handler: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    telegram_webhook_secret: str = "",
    control_api_token: str = "",
    market_ohlc_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    platform_status_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    control_status_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    routing_info_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    performance_stats_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    system_logs_handler: Optional[Callable[[dict[str, Any]], Awaitable[Any]]] = None,
    forum_topics_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    forum_create_topic_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    forum_topic_detail_handler: Optional[
        Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    ] = None,
    forum_replies_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    forum_scout_status_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    forum_scout_register_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    forum_scout_publish_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    security_skills_status_handler: Optional[
        Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    ] = None,
    security_skills_scan_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    prediction_dashboard_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
):
    """Start a lightweight HTTP server for Cloud Run health checks."""
    port = int(os.getenv("PORT", "8080"))

    app = web.Application(middlewares=[cors_middleware])
    app["cors_allowlist"] = _build_cors_allowlist()
    app["control_api_token"] = (control_api_token or "").strip()
    app["_ws_clients"] = []
    app.on_startup.append(_start_ws_push)
    app.on_cleanup.append(_stop_ws_push)
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/readiness", readiness_check)
    app.router.add_get("/ws", _ws_dashboard_handler)
    if telegram_update_handler is not None:
        app["telegram_update_handler"] = telegram_update_handler
        app["telegram_webhook_secret"] = (telegram_webhook_secret or "").strip()
        app.router.add_post("/telegram/webhook", telegram_webhook)

    if market_ohlc_handler is not None:
        app["market_ohlc_handler"] = market_ohlc_handler
        app.router.add_get("/api/v2/market/ohlc", market_ohlc)
    if platform_status_handler is not None:
        app["platform_status_handler"] = platform_status_handler
        app.router.add_get("/api/v2/platforms/status", platform_status)
    if control_status_handler is not None:
        app["control_status_handler"] = control_status_handler
        app.router.add_get("/api/v2/control/status", control_status)
    if routing_info_handler is not None:
        app["routing_info_handler"] = routing_info_handler
        app.router.add_get("/api/v2/trade/routing", routing_info)
    if performance_stats_handler is not None:
        app["performance_stats_handler"] = performance_stats_handler
        app.router.add_get("/api/analytics/performance/stats", performance_stats)
    if system_logs_handler is not None:
        app["system_logs_handler"] = system_logs_handler
        app.router.add_get("/logs/system", system_logs)

    if forum_topics_handler is not None:
        app["forum_topics_handler"] = forum_topics_handler
        app.router.add_get("/api/v2/forum/topics", forum_topics)
    if forum_create_topic_handler is not None:
        app["forum_create_topic_handler"] = forum_create_topic_handler
        app.router.add_post("/api/v2/forum/topics", forum_topics)
    if forum_topic_detail_handler is not None:
        app["forum_topic_detail_handler"] = forum_topic_detail_handler
        app.router.add_get("/api/v2/forum/topics/{topic_id}", forum_topic_detail)
    if forum_replies_handler is not None:
        app["forum_replies_handler"] = forum_replies_handler
        app.router.add_post("/api/v2/forum/topics/{topic_id}/replies", forum_replies)
    if forum_scout_status_handler is not None:
        app["forum_scout_status_handler"] = forum_scout_status_handler
        app.router.add_get("/api/v2/forum/scout/status", forum_scout_status)
    if forum_scout_register_handler is not None:
        app["forum_scout_register_handler"] = forum_scout_register_handler
        app.router.add_post("/api/v2/forum/scout/register", forum_scout_register)
    if forum_scout_publish_handler is not None:
        app["forum_scout_publish_handler"] = forum_scout_publish_handler
        app.router.add_post("/api/v2/forum/scout/publish", forum_scout_publish)
    if security_skills_status_handler is not None:
        app["security_skills_status_handler"] = security_skills_status_handler
        app.router.add_get("/api/v2/security/skills/status", security_skills_status)
    if security_skills_scan_handler is not None:
        app["security_skills_scan_handler"] = security_skills_scan_handler
        app.router.add_get("/api/v2/security/skills/scan", security_skills_scan)
        app.router.add_post("/api/v2/security/skills/scan", security_skills_scan)
    if prediction_dashboard_handler is not None:
        app["prediction_dashboard_handler"] = prediction_dashboard_handler
        app.router.add_get("/api/v2/predictions/dashboard", prediction_dashboard)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)

    logger.info(f"🏥 Health server starting on port {port}")
    try:
        await site.start()
        # Keep running
        return runner
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")
        # Don't crash the bot if health server fails, but log it critical
        return None
