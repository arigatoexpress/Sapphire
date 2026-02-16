"""
Health Server for Background Worker Services

Provides a minimal HTTP health endpoint for Cloud Run compatibility.
Background workers (bots, scanners) need this to pass health checks.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthServer:
    """Minimal HTTP server for health checks in background workers."""

    def __init__(self, service_name: str, get_status: Optional[Callable] = None):
        self.service_name = service_name
        self.get_status = get_status
        self.port = int(os.getenv("PORT", 8080))
        self.app = web.Application()
        self.runner = None

        # Register routes
        self.app.router.add_get("/", self.health_handler)
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/status", self.status_handler)

    async def health_handler(self, request: web.Request) -> web.Response:
        """Basic health check - always returns healthy if running."""
        return web.json_response(
            {
                "status": "healthy",
                "service": self.service_name,
            }
        )

    async def status_handler(self, request: web.Request) -> web.Response:
        """Detailed status from the service."""
        if self.get_status:
            try:
                status = self.get_status()
                return web.json_response(status)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"service": self.service_name})

    async def start(self):
        """Start the health server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"🏥 Health server running on port {self.port}")

    async def stop(self):
        """Stop the health server."""
        if self.runner:
            await self.runner.cleanup()


async def run_with_health_server(
    service_name: str, main_coroutine: Callable, get_status: Optional[Callable] = None
):
    """
    Run a background worker with an HTTP health server.

    Usage:
        await run_with_health_server("my-service", my_bot.start, my_bot.get_status)
    """
    health_server = HealthServer(service_name, get_status)
    await health_server.start()

    try:
        await main_coroutine()
    finally:
        await health_server.stop()
