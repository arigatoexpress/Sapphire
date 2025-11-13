"""
Simplified API - Emergency Fallback

Minimal FastAPI application that uses the simplified trading service
to provide basic functionality when the main service fails to start.
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .simplified_service import SimplifiedTradingService

logger = logging.getLogger(__name__)

# Create simplified service instance
service = SimplifiedTradingService()

# Create FastAPI app
app = FastAPI(
    title="Sapphire Trade - Simplified API",
    description="Emergency fallback API with basic trading functionality",
    version="1.0.0-simplified"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Start the simplified trading service on startup"""
    try:
        await service.start()
        logger.info("✅ Simplified API started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start simplified service: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the service on shutdown"""
    await service.stop()
    logger.info("🛑 Simplified API shut down")

@app.get("/healthz")
async def health_check():
    """Basic health check endpoint"""
    return {"status": "healthy", "service": "simplified_api"}

@app.get("/portfolio-status")
async def get_portfolio_status():
    """Get portfolio status"""
    try:
        return await service.get_portfolio_status()
    except Exception as e:
        logger.error(f"Portfolio status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get portfolio status")

@app.get("/agent-activity")
async def get_agent_activities():
    """Get agent activities"""
    try:
        activities = await service.get_agent_activities()
        return activities
    except Exception as e:
        logger.error(f"Agent activities error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get agent activities")

@app.get("/system-status")
async def get_system_status():
    """Get system status"""
    try:
        return await service.get_system_status()
    except Exception as e:
        logger.error(f"System status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system status")

@app.get("/trading-signals")
async def get_trading_signals():
    """Get recent trading signals (simplified version)"""
    return {
        "signals": [],
        "message": "Simplified service - no active trading signals",
        "timestamp": "2025-01-01T00:00:00Z"
    }

# For compatibility with existing frontend
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Sapphire Trade Simplified API", "status": "operational"}
