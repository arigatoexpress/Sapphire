#!/usr/bin/env python3
"""
Live Trading Dashboard Service
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import httpx
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sapphire AI Trading Dashboard", version="1.0.0")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the live React app
@app.get("/")
async def serve_root():
    """Serve the main index.html"""
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sapphire AI - Live Trading</title>
    <script type="module" crossorigin src="/assets/index-D_HfLUBI.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-P-5Vxrcg.css">
  </head>
  <body class="bg-gray-100">
    <div id="root"></div>
  </body>
</html>
    """)

# API routes for real-time data
@app.get("/api/v1/trader/status")
async def get_trader_status():
    """Get trader service status"""
    try:
        cloud_trader_url = os.getenv("CLOUD_TRADER_URL", "https://cloud-trader-880429861698.us-central1.run.app")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{cloud_trader_url}/health")
            if response.status_code == 200:
                data = response.json()
                # Add live trading indicator
                data["status"] = "online"
                data["trading_enabled"] = True
                data["mode"] = "LIVE"
                return data
            else:
                return {
                    "status": "degraded",
                    "trading_enabled": True,
                    "mode": "LIVE",
                    "message": "Service responding with non-200 status"
                }
    except Exception as e:
        logger.error(f"Error getting trader status: {e}")
        return {
            "status": "offline",
            "trading_enabled": False,
            "mode": "MAINTENANCE",
            "message": str(e)
        }

@app.get("/api/v1/trader/performance")
async def get_performance():
    """Get trading performance metrics"""
    cloud_trader_url = os.getenv("CLOUD_TRADER_URL", "https://cloud-trader-880429861698.us-central1.run.app")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{cloud_trader_url}/metrics")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error getting performance: {e}")
    
    # Return mock data if service is down
    return {
        "daily_pnl": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
        "portfolio_value": 100000.0,
        "active_positions": 0,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/trader/positions")
async def get_positions():
    """Get current trading positions"""
    cloud_trader_url = os.getenv("CLOUD_TRADER_URL", "https://cloud-trader-880429861698.us-central1.run.app")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{cloud_trader_url}/positions")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
    
    return {"positions": [], "total": 0}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "sapphire-dashboard",
        "mode": "LIVE",
        "trading_enabled": True
    }

# Mount static files if they exist
static_path = os.getenv("STATIC_PATH", "/app/static")
if os.path.exists(static_path):
    assets_path = os.path.join(static_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    app.mount("/static", StaticFiles(directory=static_path), name="static")
else:
    logger.warning(f"Static path {static_path} does not exist, serving dynamic content only")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

