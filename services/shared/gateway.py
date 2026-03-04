import asyncio
import json
import logging
import os
from typing import Callable, List, Optional

from aiohttp import web

logger = logging.getLogger(__name__)


class ExecutionGateway:
    """
    Unified Server for Health Checks & High-Priority Execution Commands.
    Replaces rudimentary health.py
    """

    def __init__(self):
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
        self.runner: Optional[web.AppRunner] = None

    async def health_check(self, request):
        return web.Response(text="OK", status=200)

    async def readiness_check(self, request):
        return web.Response(text="READY", status=200)

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
        """Accept legacy TV webhook posts and intentionally no-op."""
        try:
            data = await request.json()
            logger.info(
                "Ignoring legacy TradingView webhook on local gateway; expected normalized /execute command | keys=%s",
                sorted(list(data.keys()))[:12],
            )
        except Exception:
            logger.info(
                "Ignoring legacy TradingView webhook on local gateway; non-JSON payload"
            )
        return web.json_response({"status": "ignored", "reason": "use /execute"}, status=202)

    async def start(self) -> asyncio.Queue:
        """Start the server and return the command queue for the bot to consume."""
        port = int(os.getenv("PORT", "8080"))

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", port)

        logger.info(f"🏥⚡ Gateway Server starting on port {port} (Health + Exec)")
        try:
            await site.start()
        except Exception as e:
            logger.error(f"Failed to start Gateway Server: {e}")

        return self.command_queue


# Singleton instance for easy import
gateway = ExecutionGateway()


async def start_gateway_server() -> asyncio.Queue:
    return await gateway.start()
