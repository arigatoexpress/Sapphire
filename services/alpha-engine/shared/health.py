import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)


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


async def start_health_server(
    telegram_update_handler: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
    telegram_webhook_secret: str = "",
    tradingview_update_handler: Optional[
        Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    ] = None,
    tradingview_webhook_secret: str = "",
):
    """Start a lightweight HTTP server for Cloud Run health checks."""
    port = int(os.getenv("PORT", "8080"))

    app = web.Application()
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
