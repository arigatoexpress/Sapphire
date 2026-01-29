"""
Sapphire V2 Main Entry Point
Clean, modular trading system inspired by ElizaOS architecture.

This is the new entry point that replaces the monolithic app initialization.
Seamlessly integrates with existing GCloud secrets and configurations.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
# Configure logging
from .platform_logger import PlatformLogHandler

handler = logging.StreamHandler(sys.stdout)
platform_handler = PlatformLogHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[handler, platform_handler],
)
logger = logging.getLogger("sapphire.v2")


# --- Application State ---
orchestrator = None


async def _keep_alive_loop():
    """
    Background task that keeps the Cloud Run container alive.
    Cloud Run scales down containers with no HTTP traffic.
    This makes periodic internal requests to prevent shutdown.
    """
    import httpx

    await asyncio.sleep(10)  # Initial wait for startup

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                # Ping health endpoint to keep container active
                response = await client.get("http://localhost:8080/health")
                logger.debug(f"💓 Keep-alive ping: {response.status_code}")
            except Exception as e:
                logger.debug(f"💓 Keep-alive ping failed (normal during startup): {e}")

            await asyncio.sleep(30)  # Ping every 30 seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with GCloud integration."""
    global orchestrator

    logger.info("🚀 Starting Sapphire V2...")

    # Use existing config and credentials
    from cloud_trader.config import get_settings
    from cloud_trader.credentials import load_credentials

    settings = get_settings()
    credentials = load_credentials()

    logger.info(f"📋 Loaded settings for project: {settings.gcp_project_id}")
    if credentials.api_key:
        logger.info(f"🔑 Aster API Key loaded: {credentials.api_key[:4]}...")

    # Inject Credentials into Settings (Runtime Secret Hydration)
    if credentials.telegram_bot_token and not settings.telegram_bot_token:
        settings.telegram_bot_token = credentials.telegram_bot_token
        logger.info("💉 Injected Telegram Bot Token from Secret Manager")

    if credentials.telegram_chat_id and not settings.telegram_chat_id:
        settings.telegram_chat_id = credentials.telegram_chat_id
        logger.info("💉 Injected Telegram Chat ID from Secret Manager")

    # Telegram Diagnostics
    masked_token = (
        settings.telegram_bot_token[:4] + "..." if settings.telegram_bot_token else "None"
    )
    logger.info(
        f"📱 Telegram Config: Enabled={settings.enable_telegram}, Token={masked_token}, ChatID={settings.telegram_chat_id}"
    )

    # Initialize orchestrator
    from cloud_trader.core import TradingOrchestrator

    orchestrator = TradingOrchestrator(settings)

    # MICROSERVICES: Skip trading system if this is the web-only service
    serve_frontend = os.getenv("SERVE_FRONTEND", "false").lower() == "true"
    if serve_frontend:
        logger.info("🌐 Running in web-only mode (SERVE_FRONTEND=true) - skipping trading orchestrator")
    else:
        # Start trading system
        await orchestrator.start()

    # Start background keep-alive task to prevent Cloud Run shutdown
    keep_alive_task = asyncio.create_task(_keep_alive_loop())

    logger.info("✅ Sapphire V2 is ONLINE")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Sapphire V2...")
    keep_alive_task.cancel()
    if orchestrator:
        await orchestrator.stop()
    logger.info("✅ Sapphire V2 shutdown complete")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Sapphire V2",
        description="Autonomous AI Trading System - Powered by ElizaOS Patterns",
        version="2.2.8",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    from cloud_trader.api.routers.agents import router as agents_router
    from cloud_trader.api.routers.analytics import router as analytics_router
    from cloud_trader.api.routers.portfolio import router as portfolio_router
    from cloud_trader.api.routers.trading import router as trading_router

    app.include_router(trading_router)
    app.include_router(agents_router)
    app.include_router(portfolio_router)
    app.include_router(analytics_router)

    # Health check
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": "2.1.0",
            "orchestrator": orchestrator.get_status() if orchestrator else None,
        }

    # System status - serves frontend if available, otherwise returns JSON status
    @app.get("/")
    async def root():
        import os
        from fastapi.responses import FileResponse

        # Try to serve the Vue.js frontend if it exists
        index_path = "/app/static/index.html"
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")

        # Fallback to JSON status if frontend not built
        return {
            "name": "Sapphire V2",
            "status": "running",
            "architecture": "ElizaOS-inspired modular design",
            "platforms": [
                "Aster (CEX)",
                "Drift (Solana Perps)",
                "Hyperliquid (L1 Perps)",
                "Jupiter (Solana DEX)",
                "Lighter (Ethereum L2)",
                "Symphony Monad (Spot Swaps)",
                "Symphony Base (Perps)",
            ],
            "components": [
                "TradingOrchestrator",
                "AgentOrchestrator",
                "ElizaAgents (4x)",
                "PlatformRouter",
                "PositionTracker",
                "DegenIntel",
            ],
            "frontend": "not_built",
            "dashboard_url": "https://sapphirealpha.xyz",
        }

    # Emergency close all positions
    @app.post("/emergency/close-all")
    async def emergency_close_all(dry_run: bool = False):
        """Emergency close all positions across all platforms."""
        from cloud_trader.emergency_close import close_all_positions

        return await close_all_positions(dry_run=dry_run)

    # Get all open positions (dry run of emergency close)
    @app.get("/positions/all")
    async def get_all_positions():
        """Get all open positions across all platforms."""
        from cloud_trader.emergency_close import get_all_positions

        return await get_all_positions()

    # Platform-specific logs endpoint
    @app.get("/logs/{platform}")
    async def get_platform_logs(platform: str, limit: int = 50):
        """Get recent logs for a specific platform."""
        from cloud_trader.platform_logger import get_platform_logs

        return await get_platform_logs(platform, limit)

    # AI Circuit Breaker Management
    @app.get("/ai/circuit-breakers")
    async def get_circuit_breakers():
        """Get circuit breaker status for all AI agents."""
        from cloud_trader.vertex_ai_client import get_vertex_client

        try:
            client = get_vertex_client()
            return {
                "status": "ok",
                "circuit_breakers": client.get_all_circuit_breakers(),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/ai/circuit-breakers/reset")
    async def reset_circuit_breakers(agent_id: str = None):
        """Reset circuit breakers for AI agents."""
        from cloud_trader.vertex_ai_client import get_vertex_client

        try:
            client = get_vertex_client()
            if agent_id:
                success = client.reset_circuit_breaker(agent_id)
                return {
                    "status": "ok" if success else "not_found",
                    "agent_id": agent_id,
                    "reset": success,
                }
            else:
                # Reset all circuit breakers
                breakers = client.get_all_circuit_breakers()
                reset_count = 0
                for aid in breakers.keys():
                    if client.reset_circuit_breaker(aid):
                        reset_count += 1
                return {
                    "status": "ok",
                    "reset_count": reset_count,
                    "message": f"Reset {reset_count} circuit breakers",
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("cloud_trader.main_v2:app", host="0.0.0.0", port=port, reload=True)
