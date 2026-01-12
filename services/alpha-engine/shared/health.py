import asyncio
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


async def health_check(request):
    """Liveness probe."""
    return web.Response(text="OK", status=200)


async def readiness_check(request):
    """Readiness probe."""
    return web.Response(text="READY", status=200)


async def start_health_server():
    """Start a lightweight HTTP server for Cloud Run health checks."""
    port = int(os.getenv("PORT", "8080"))

    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/readiness", readiness_check)

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
