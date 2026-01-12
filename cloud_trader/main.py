"""
Sapphire V2 Trading System - Main Entry Point
Entry point for Cloud Run deployment.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


class SapphireApp:
    """Main application class for Sapphire V2."""

    def __init__(self):
        self.orchestrator = None
        self.server = None
        self._shutdown_event = asyncio.Event()
        
        # Kill switches
        self._paused = False
        self._kill_switch_active = False
        self._volatility_threshold = float(os.getenv("VOLATILITY_KILL_THRESHOLD", 0.10))  # 10%
        self._drawdown_kill_threshold = float(os.getenv("DRAWDOWN_KILL_THRESHOLD", 0.15))  # 15%
        self._mode = os.getenv("TRADING_MODE", "live")  # live, paper, staging

    async def start(self):
        """Start the trading system."""
        logger.info("🚀 Starting Sapphire V2 Trading System...")

        # Import here to avoid circular imports
        from cloud_trader.core.orchestrator import TradingOrchestrator

        # Initialize orchestrator
        self.orchestrator = TradingOrchestrator()
        await self.orchestrator.start()

        # Start health check server
        await self._start_health_server()

        logger.info("✅ Sapphire V2 is running!")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    async def _start_health_server(self):
        """Start HTTP health check server for Cloud Run."""
        from aiohttp import web

        async def health_handler(request):
            status = self.orchestrator.get_status() if self.orchestrator else {}
            return web.json_response({
                "status": "healthy",
                "running": status.get("running", False),
                "uptime_seconds": status.get("uptime_seconds", 0),
            })

        async def metrics_handler(request):
            """Expose metrics for monitoring."""
            if not self.orchestrator:
                return web.json_response({"error": "not initialized"})

            # Get trading metrics
            metrics = {
                "metric_name": "sapphire_metrics",
                "running": self.orchestrator._running,
            }

            # Add risk manager metrics if available
            if hasattr(self.orchestrator, "risk_manager"):
                rm_status = self.orchestrator.risk_manager.get_status()
                metrics["drawdown"] = rm_status.get("current_drawdown", 0)
                metrics["risk_level"] = rm_status.get("risk_level", "unknown")

            return web.json_response(metrics)

        app = web.Application()
        app.router.add_get("/health", health_handler)
        app.router.add_get("/metrics", metrics_handler)
        app.router.add_post("/kill", self._kill_handler)
        app.router.add_post("/pause", self._pause_handler)
        app.router.add_post("/resume", self._resume_handler)

        port = int(os.getenv("PORT", 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        logger.info(f"🌐 Health server running on port {port}")
        logger.info(f"🎮 Trading mode: {self._mode}")

    async def stop(self):
        """Stop the trading system."""
        logger.info("🛑 Stopping Sapphire V2...")

        if self.orchestrator:
            await self.orchestrator.stop()

        self._shutdown_event.set()
        logger.info("✅ Sapphire V2 stopped gracefully")

    def handle_signal(self, sig):
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig}")
        asyncio.create_task(self.stop())

    async def _kill_handler(self, request):
        """Emergency kill switch endpoint."""
        from aiohttp import web
        logger.warning("🚨 KILL SWITCH ACTIVATED")
        self._kill_switch_active = True
        await self.stop()
        return web.json_response({"status": "killed", "message": "All trading halted"})

    async def _pause_handler(self, request):
        """Pause trading endpoint."""
        from aiohttp import web
        logger.warning("⏸️ TRADING PAUSED")
        self._paused = True
        return web.json_response({"status": "paused"})

    async def _resume_handler(self, request):
        """Resume trading endpoint."""
        from aiohttp import web
        logger.info("▶️ TRADING RESUMED")
        self._paused = False
        return web.json_response({"status": "resumed"})

    async def check_volatility_kill(self, volatility: float):
        """Check if volatility triggers kill switch."""
        if volatility > self._volatility_threshold:
            logger.warning(f"🚨 High volatility detected ({volatility:.2%}), activating kill switch")
            self._paused = True
            return True
        return False

    async def check_drawdown_kill(self, drawdown: float):
        """Check if drawdown triggers kill switch."""
        if drawdown > self._drawdown_kill_threshold:
            logger.warning(f"🚨 Max drawdown exceeded ({drawdown:.2%}), activating kill switch")
            self._kill_switch_active = True
            await self.stop()
            return True
        return False

    @property
    def is_trading_enabled(self) -> bool:
        """Check if trading is currently enabled."""
        return not self._paused and not self._kill_switch_active


async def main():
    """Main entry point."""
    app = SapphireApp()

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: app.handle_signal(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await app.start()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
