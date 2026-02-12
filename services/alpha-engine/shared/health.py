import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)


def _build_cors_allowlist() -> set[str]:
    raw = str(
        os.getenv(
            "ALPHA_API_CORS_ORIGINS",
            "https://sapphirebook-web-s77j6bxyra-uc.a.run.app,http://localhost:5173,http://127.0.0.1:5173",
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
            "Content-Type,Authorization,X-Sapphire-Webhook-Secret,X-Telegram-Bot-Api-Secret-Token"
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


async def tradingview_webhook(request: web.Request) -> web.Response:
    """Receive TradingView alerts and pass them to the alpha handler."""
    payload: dict[str, Any]
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {"payload": payload}
    except Exception:
        raw = (await request.text()).strip()
        if not raw:
            return web.json_response({"ok": False, "error": "empty_payload"}, status=400)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"payload": parsed}
        except Exception:
            payload = {"message": raw}

    expected_secret = request.app.get("tradingview_webhook_secret", "")
    if expected_secret:
        received_secret = _extract_shared_secret(
            request,
            payload,
            header_name="X-Sapphire-Webhook-Secret",
        )
        if received_secret != expected_secret:
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    handler = request.app.get("tradingview_update_handler")
    if handler is None:
        return web.json_response({"ok": False, "error": "handler_unavailable"}, status=503)

    try:
        result = await handler(payload)
    except Exception as exc:
        logger.error(f"TradingView webhook handler error: {exc}")
        return web.json_response({"ok": False, "error": "handler_failed"}, status=500)

    if isinstance(result, dict):
        response_payload = {"ok": True, **result}
    else:
        response_payload = {"ok": True}
    return web.json_response(response_payload, status=200)


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


async def routing_info(request: web.Request) -> web.Response:
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


async def start_health_server(
    telegram_update_handler: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    telegram_webhook_secret: str = "",
    tradingview_update_handler: Optional[
        Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    ] = None,
    tradingview_webhook_secret: str = "",
    market_ohlc_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    platform_status_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    routing_info_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    performance_stats_handler: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None,
    system_logs_handler: Optional[Callable[[dict[str, Any]], Awaitable[Any]]] = None,
):
    """Start a lightweight HTTP server for Cloud Run health checks."""
    port = int(os.getenv("PORT", "8080"))

    app = web.Application(middlewares=[cors_middleware])
    app["cors_allowlist"] = _build_cors_allowlist()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/readiness", readiness_check)
    if telegram_update_handler is not None:
        app["telegram_update_handler"] = telegram_update_handler
        app["telegram_webhook_secret"] = (telegram_webhook_secret or "").strip()
        app.router.add_post("/telegram/webhook", telegram_webhook)
    if tradingview_update_handler is not None:
        app["tradingview_update_handler"] = tradingview_update_handler
        app["tradingview_webhook_secret"] = (tradingview_webhook_secret or "").strip()
        app.router.add_post("/tradingview/webhook", tradingview_webhook)
    if market_ohlc_handler is not None:
        app["market_ohlc_handler"] = market_ohlc_handler
        app.router.add_get("/api/v2/market/ohlc", market_ohlc)
    if platform_status_handler is not None:
        app["platform_status_handler"] = platform_status_handler
        app.router.add_get("/api/v2/platforms/status", platform_status)
    if routing_info_handler is not None:
        app["routing_info_handler"] = routing_info_handler
        app.router.add_get("/api/v2/trade/routing", routing_info)
    if performance_stats_handler is not None:
        app["performance_stats_handler"] = performance_stats_handler
        app.router.add_get("/api/analytics/performance/stats", performance_stats)
    if system_logs_handler is not None:
        app["system_logs_handler"] = system_logs_handler
        app.router.add_get("/logs/system", system_logs)

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
