import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# Control token for protecting mutable endpoints
_CONTROL_TOKEN = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "")


async def _check_control_token(request: web.Request) -> Optional[web.Response]:
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
async def control_token_middleware(request: web.Request, handler: Callable) -> web.Response:
    """Middleware to validate control token on mutable endpoints."""
    auth_response = await _check_control_token(request)
    if auth_response is not None:
        return auth_response
    return await handler(request)


async def start_health_server(
    telegram_update_handler: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    telegram_webhook_secret: str = "",
    control_api_token: str = "",
    market_ohlc_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    platform_status_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    routing_info_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    performance_stats_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    system_logs_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    control_status_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    security_skills_status_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    security_skills_scan_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_topics_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_topic_detail_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_create_topic_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_replies_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_scout_status_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_scout_register_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    forum_scout_publish_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
    prediction_dashboard_handler: Optional[Callable[[Any, Dict[str, Any]], Awaitable[Any]]] = None,
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
