"""HTTP health, readiness, and dashboard WebSocket surface for services.

Provides /health and /readiness endpoints plus a push-broadcast WebSocket
(max 50 clients, 5s interval) used by the dashboard for live telemetry.
Mutating endpoints are gated by the SAPPHIRE_CONTROL_API_TOKEN header.
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

# Control token for protecting mutable endpoints
_CONTROL_TOKEN = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "")

# ---------------------------------------------------------------------------
# WebSocket dashboard constants
# ---------------------------------------------------------------------------

_WS_MAX_CLIENTS: int = 50
_WS_PUSH_INTERVAL: float = 5.0  # seconds between push broadcasts


async def _check_control_token(request: web.Request) -> web.Response | None:
    """Validate X-Sapphire-Control-Token header for mutable endpoints.
    
    Returns None if valid or token not configured, Response if invalid.
    """
    # Skip for safe methods
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    
    # If token not configured, warn but allow (dev mode only)
    if not _CONTROL_TOKEN:
        logger.warning("⚠️  SAPPHIRE_CONTROL_API_TOKEN not set — mutable endpoint unprotected!")
        return None
    
    # Check header
    received_token = request.headers.get("X-Sapphire-Control-Token", "")
    if not received_token:
        return web.Response(
            text='{"error": "X-Sapphire-Control-Token header required"}',
            status=401,
            content_type="application/json"
        )
    if received_token != _CONTROL_TOKEN:
        return web.Response(
            text='{"error": "Invalid control token"}',
            status=403,
            content_type="application/json"
        )
    return None


async def health_check(request):
    """Liveness probe."""
    return web.Response(text="OK", status=200)


async def readiness_check(request):
    """Readiness probe."""
    return web.Response(text="READY", status=200)


async def telegram_webhook(request):
    """Receive Telegram webhook updates and pass them to the bot update handler."""
    expected_secret = request.app.get("telegram_webhook_secret")
    if expected_secret:
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


@web.middleware
async def cors_middleware(request: web.Request, handler: Callable) -> web.Response:
    """CORS middleware that validates Origin against app['cors_allowlist']."""
    origin = request.headers.get("Origin", "")
    allowlist: set[str] = request.app.get("cors_allowlist", set())

    response = await handler(request)

    if origin and allowlist and origin in allowlist:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Sapphire-Control-Token, Authorization"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ---------------------------------------------------------------------------
# WebSocket dashboard
# ---------------------------------------------------------------------------

async def _build_dashboard_snapshot(app: web.Application) -> dict[str, Any]:
    """Build a snapshot dict from registered handler callbacks."""
    snapshot: dict[str, Any] = {"timestamp": time.time()}
    for key in ("control", "performance", "platforms"):
        handler_key = f"{key}_status_handler" if key != "performance" else "performance_stats_handler"
        if key == "control":
            handler_key = "control_status_handler"
        elif key == "platforms":
            handler_key = "platform_status_handler"
        handler = app.get(handler_key)
        if handler is None:
            snapshot[key] = None
            continue
        try:
            snapshot[key] = await handler({})
        except Exception:
            snapshot[key] = None
    return snapshot


async def _ws_dashboard_handler(request: web.Request) -> web.WebSocketResponse:
    """WebSocket endpoint for the live dashboard."""
    origin = request.headers.get("Origin", "")
    allowlist: set[str] = request.app.get("cors_allowlist", set())

    # Origin check: reject if origin is present and not in allowlist
    if origin and allowlist and origin not in allowlist:
        return web.Response(text="Forbidden origin", status=403)

    # Max clients check
    clients: list = request.app.get("_ws_clients", [])
    if len(clients) >= _WS_MAX_CLIENTS:
        return web.Response(text="Too many clients", status=503)

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.append(ws)

    try:
        # Send init message with snapshot
        snapshot = await _build_dashboard_snapshot(request.app)
        snapshot["type"] = "init"
        await ws.send_json(snapshot)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_str("pong")
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        if ws in clients:
            clients.remove(ws)

    return ws


async def _ws_push_loop(app: web.Application) -> None:
    """Periodically push snapshots to all connected WS clients."""
    try:
        while True:
            await asyncio.sleep(_WS_PUSH_INTERVAL)
            clients: list = app.get("_ws_clients", [])
            if not clients:
                continue
            snapshot = await _build_dashboard_snapshot(app)
            snapshot["type"] = "snapshot"
            payload = json.dumps(snapshot)
            dead: list = []
            for ws in clients:
                try:
                    await ws.send_str(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in clients:
                    clients.remove(ws)
    except asyncio.CancelledError:
        return


async def _start_ws_push(app: web.Application) -> None:
    """Lifecycle hook: start the WS push background task."""
    app["_ws_push_task"] = asyncio.create_task(_ws_push_loop(app))


async def _stop_ws_push(app: web.Application) -> None:
    """Lifecycle hook: stop the WS push background task."""
    task = app.get("_ws_push_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Forum API handlers (CORS + token guarded)
# ---------------------------------------------------------------------------

def _is_authorized(request: web.Request) -> bool:
    """Check if request is authorized via CORS origin or control token."""
    origin = request.headers.get("Origin", "")
    allowlist: set[str] = request.app.get("cors_allowlist", set())
    if origin and allowlist and origin in allowlist:
        return True

    # Check control token in header
    control_token = request.app.get("control_api_token", "")
    if control_token:
        # Check X-Sapphire-Control-Token header
        if request.headers.get("X-Sapphire-Control-Token", "") == control_token:
            return True
        # Check Authorization: Bearer <token>
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == control_token:
            return True

    return False


async def forum_topics(request: web.Request) -> web.Response:
    """GET /api/v2/forum/topics — list forum topics."""
    if not _is_authorized(request):
        return web.Response(text='{"error":"forbidden"}', status=403, content_type="application/json")
    handler = request.app.get("forum_topics_handler")
    if handler is None:
        return web.json_response({"error": "not configured"}, status=501)
    result = await handler(dict(request.query))
    return web.json_response(result)


async def forum_topic_detail(request: web.Request) -> web.Response:
    """GET /api/v2/forum/topics/{topic_id} — get single topic."""
    if not _is_authorized(request):
        return web.Response(text='{"error":"forbidden"}', status=403, content_type="application/json")
    handler = request.app.get("forum_topic_detail_handler")
    if handler is None:
        return web.json_response({"error": "not configured"}, status=501)
    topic_id = request.match_info.get("topic_id", "")
    result = await handler({"topic_id": topic_id})
    return web.json_response(result)


@web.middleware
async def control_token_middleware(request: web.Request, handler: Callable) -> web.Response:
    """Middleware to validate control token on mutable endpoints."""
    auth_response = await _check_control_token(request)
    if auth_response is not None:
        return auth_response
    return await handler(request)


async def start_health_server(
    telegram_update_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    telegram_webhook_secret: str = "",
    control_api_token: str = "",
    market_ohlc_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    platform_status_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    routing_info_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    performance_stats_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    system_logs_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    control_status_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    security_skills_status_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    security_skills_scan_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_topics_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_topic_detail_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_create_topic_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_replies_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_scout_status_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_scout_register_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    forum_scout_publish_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    prediction_dashboard_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
    intel_feed_handler: Callable[[Any, dict[str, Any]], Awaitable[Any]] | None = None,
):
    """Start a lightweight HTTP server for Cloud Run health checks."""
    port = int(os.getenv("PORT", "8080"))
    # Update global control token from passed argument
    global _CONTROL_TOKEN
    if control_api_token:
        _CONTROL_TOKEN = control_api_token

    app = web.Application(middlewares=[control_token_middleware])
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/readiness", readiness_check)
    app.router.add_get("/status", health_check)
    
    if telegram_update_handler is not None:
        app["telegram_update_handler"] = telegram_update_handler
        app["telegram_webhook_secret"] = (telegram_webhook_secret or "").strip()
        app.router.add_post("/telegram/webhook", telegram_webhook)

    # Add API routes if handlers provided
    # The handlers are bound methods on the engine, so they already have access to self
    # We just need to adapt from aiohttp Request to the handler signature
    
    async def adapt_get(handler, request: web.Request) -> web.Response:
        """Adapt GET request to handler(engine, query_dict)."""
        if handler is None:
            return web.json_response({"error": "Not implemented"}, status=501)
        try:
            query = dict(request.query)
            result = await handler(query)
            return web.json_response(result)
        except Exception as exc:
            logger.error(f"Handler error: {exc}")
            return web.json_response({"error": str(exc)}, status=500)
    
    async def adapt_post(handler, request: web.Request) -> web.Response:
        """Adapt POST request to handler(engine, payload_dict)."""
        if handler is None:
            return web.json_response({"error": "Not implemented"}, status=501)
        try:
            payload = await request.json() if request.can_read_body else {}
            result = await handler(payload or {})
            return web.json_response(result)
        except Exception as exc:
            logger.error(f"Handler error: {exc}")
            return web.json_response({"error": str(exc)}, status=500)
    
    # Market Data (GET)
    if market_ohlc_handler:
        app.router.add_get("/market/ohlc", lambda r: adapt_get(market_ohlc_handler, r))
    
    # Platform Status (GET)
    if platform_status_handler:
        app.router.add_get("/platforms/status", lambda r: adapt_get(platform_status_handler, r))
    
    # Routing Info (GET)
    if routing_info_handler:
        app.router.add_get("/routing", lambda r: adapt_get(routing_info_handler, r))
    
    # Performance Stats (GET)
    if performance_stats_handler:
        app.router.add_get("/performance/stats", lambda r: adapt_get(performance_stats_handler, r))
    
    # System Logs (POST - mutable, requires token)
    if system_logs_handler:
        app.router.add_post("/system/logs", lambda r: adapt_post(system_logs_handler, r))
    
    # Control Status (GET)
    if control_status_handler:
        app.router.add_get("/control/status", lambda r: adapt_get(control_status_handler, r))
    
    # Security Skills (GET + POST)
    if security_skills_status_handler:
        app.router.add_get("/security/skills/status", lambda r: adapt_get(security_skills_status_handler, r))
    if security_skills_scan_handler:
        app.router.add_post("/security/skills/scan", lambda r: adapt_post(security_skills_scan_handler, r))
    
    # Forum (GET + POST endpoints)
    if forum_topics_handler:
        app.router.add_get("/forum/topics", lambda r: adapt_get(forum_topics_handler, r))
    if forum_create_topic_handler:
        app.router.add_post("/forum/topics", lambda r: adapt_post(forum_create_topic_handler, r))
    if forum_topic_detail_handler:
        app.router.add_get("/forum/topics/{topic_id}", lambda r: adapt_get(forum_topic_detail_handler, r))
    if forum_replies_handler:
        app.router.add_post("/forum/replies", lambda r: adapt_post(forum_replies_handler, r))
    if forum_scout_status_handler:
        app.router.add_get("/forum/scout/status", lambda r: adapt_get(forum_scout_status_handler, r))
    if forum_scout_register_handler:
        app.router.add_post("/forum/scout/register", lambda r: adapt_post(forum_scout_register_handler, r))
    if forum_scout_publish_handler:
        app.router.add_post("/forum/scout/publish", lambda r: adapt_post(forum_scout_publish_handler, r))
    
    # Prediction Dashboard (GET)
    if prediction_dashboard_handler:
        app.router.add_get("/prediction/dashboard", lambda r: adapt_get(prediction_dashboard_handler, r))

    # Intel Feed (GET)
    if intel_feed_handler:
        app.router.add_get("/intel/feed", lambda r: adapt_get(intel_feed_handler, r))

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
