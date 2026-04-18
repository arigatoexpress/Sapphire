"""Inbound API gateway for hermes-agent and OpenClaw execution commands.

Exposes unified health/readiness endpoints plus a POST /execute command buffer
used by the alpha engine to accept high-priority directives from upstream
agents. Replaces the earlier rudimentary health.py surface.
"""

import asyncio
import inspect
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)


class ExecutionGateway:
    """
    Unified Server for Health Checks & High-Priority Execution Commands.
    Replaces rudimentary health.py
    """

    def __init__(self, status_provider: Callable[[], dict[str, Any]] | None = None):
        self.app = web.Application()
        self.app.router.add_get("/", self.health_check)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/readiness", self.readiness_check)
        self.app.router.add_post("/execute", self.handle_execution)
        # Compatibility endpoint: some edge agents may still post TV payloads here.
        # This gateway only accepts normalized /execute commands, so we ack+ignore.
        self.app.router.add_post("/tradingview/webhook", self.handle_legacy_tradingview)

        # Command Buffer
        self.command_queue: asyncio.Queue = asyncio.Queue()
        self.runner: web.AppRunner | None = None
        self._http_session = None
        self.status_provider = status_provider
        self.legacy_tv_forward_url = str(
            os.getenv("SAPPHIRE_LEGACY_TV_FORWARD_URL", "")
        ).strip()

    async def _get_http_session(self):
        try:
            import aiohttp
        except Exception:
            return None
        if self._http_session is None or getattr(self._http_session, "closed", False):
            timeout = aiohttp.ClientTimeout(total=10)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    async def _status_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "ok",
            "service": "execution-gateway",
            "ready": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if self.status_provider is None:
            return payload
        try:
            details = self.status_provider()
            if inspect.isawaitable(details):
                details = await details
            if isinstance(details, dict):
                payload.update(details)
        except Exception as exc:
            payload["ready"] = False
            payload["status"] = "degraded"
            payload["status_error"] = f"{type(exc).__name__}: {exc}"
        return payload

    async def health_check(self, request):
        payload = await self._status_payload()
        return web.json_response(payload, status=200)

    async def readiness_check(self, request):
        payload = await self._status_payload()
        ready = bool(payload.get("ready", True))
        if ready:
            payload.setdefault("status", "ready")
        else:
            payload.setdefault("status", "not_ready")
        return web.json_response(payload, status=200 if ready else 503)

    async def handle_execution(self, request):
        """Handle high-priority execution command from Alpha Hub."""
        try:
            data = await request.json()
            logger.info(f"⚡ Received Command: {data}")

            # fast-put to queue
            self.command_queue.put_nowait(data)

            return web.json_response(
                {"status": "accepted", "queue_size": self.command_queue.qsize()}
            )
        except Exception as e:
            logger.error(f"Command Error: {e}")
            return web.json_response({"error": str(e)}, status=400)

    async def handle_legacy_tradingview(self, request):
        """Accept legacy TV webhook posts; optionally forward to canonical cloud ingress."""
        data: dict[str, Any] = {}
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                data = payload
        except Exception:
            logger.info("Ignoring legacy TradingView webhook on local gateway; non-JSON payload")
            return web.json_response({"status": "ignored", "reason": "non_json_payload"}, status=202)

        if self.legacy_tv_forward_url:
            try:
                session = await self._get_http_session()
                if session is None:
                    raise RuntimeError("aiohttp session unavailable")
                headers = {"Content-Type": "application/json"}
                secret = str(data.get("secret") or "").strip()
                if secret:
                    headers["X-Sapphire-Webhook-Secret"] = secret
                async with session.post(
                    self.legacy_tv_forward_url,
                    json=data,
                    headers=headers,
                ) as resp:
                    body = await resp.text()
                    if resp.status >= 400:
                        logger.warning(
                            "Legacy TV forward failed (%s): %s",
                            resp.status,
                            body[:240],
                        )
                        return web.json_response(
                            {"status": "forward_failed", "code": resp.status},
                            status=502,
                        )
                    logger.info(
                        "Forwarded legacy TradingView webhook to canonical ingress | keys=%s status=%s",
                        sorted(list(data.keys()))[:12],
                        resp.status,
                    )
                    return web.json_response(
                        {"status": "forwarded", "code": resp.status},
                        status=202,
                    )
            except Exception as exc:
                logger.warning("Legacy TV forward error: %s", exc)
                return web.json_response(
                    {"status": "forward_error", "error": str(exc)[:180]},
                    status=502,
                )

        logger.info(
            "Ignoring legacy TradingView webhook on local gateway; forwarding disabled | keys=%s",
            sorted(list(data.keys()))[:12],
        )
        return web.json_response({"status": "ignored", "reason": "forwarding_disabled"}, status=202)

    async def start(self) -> asyncio.Queue:
        """Start the server and return the command queue for the bot to consume."""
        port = int(os.getenv("PORT", "8080"))

        # If already running, reuse the existing queue.
        if self.runner is not None:
            return self.command_queue

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", port)

        logger.info(f"🏥⚡ Gateway Server starting on port {port} (Health + Exec)")
        try:
            await site.start()
        except Exception as e:
            logger.error(f"Failed to start Gateway Server: {e}")

        return self.command_queue

    async def stop(self) -> None:
        """Stop the gateway runner and release aiohttp resources."""
        runner = self.runner
        self.runner = None
        if runner is None:
            return
        try:
            await runner.cleanup()
        except Exception as exc:
            logger.debug("Gateway cleanup error: %s", exc)
        try:
            if self._http_session is not None:
                await self._http_session.close()
                self._http_session = None
        except Exception as exc:
            logger.debug("Gateway session close error: %s", exc)


# Singleton instance for easy import
gateway = ExecutionGateway()


async def start_gateway_server(
    status_provider: Callable[[], dict[str, Any]] | None = None,
) -> asyncio.Queue:
    if status_provider is not None:
        gateway.status_provider = status_provider
    return await gateway.start()


async def stop_gateway_server() -> None:
    await gateway.stop()
