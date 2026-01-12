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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sapphire.v2")


# --- Application State ---
orchestrator = None


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

    # Telegram Diagnostics
    masked_token = settings.telegram_bot_token[:4] + "..." if settings.telegram_bot_token else "None"
    logger.info(f"📱 Telegram Config: Enabled={settings.enable_telegram}, Token={masked_token}, ChatID={settings.telegram_chat_id}")

    # Initialize orchestrator
    from cloud_trader.core import TradingOrchestrator

    orchestrator = TradingOrchestrator(settings)

    # Start trading system
    await orchestrator.start()

    logger.info("✅ Sapphire V2 is ONLINE")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Sapphire V2...")
    if orchestrator:
        await orchestrator.stop()
    logger.info("✅ Sapphire V2 shutdown complete")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Sapphire V2",
        description="Autonomous AI Trading System - Powered by ElizaOS Patterns",
        version="2.0.0",
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
            "version": "2.0.0",
            "orchestrator": orchestrator.get_status() if orchestrator else None,
        }

    # System status
    @app.get("/")
    async def root():
        return {
            "name": "Sapphire V2",
            "status": "running",
            "architecture": "ElizaOS-inspired modular design",
            "components": [
                "TradingOrchestrator",
                "AgentOrchestrator",
                "ElizaAgents (4x)",
                "PlatformRouter",
                "PositionTracker",
                "DegenIntel",
            ],
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("cloud_trader.main_v2:app", host="0.0.0.0", port=port, reload=True)
