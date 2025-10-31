#!/usr/bin/env python3
"""
Simple Trading Dashboard Service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import os
from datetime import datetime
import random

app = FastAPI(title="Trading Dashboard", version="1.0.0")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if they exist
static_path = "/app/static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "https://wallet-orchestrator-880429861698.us-central1.run.app")
CLOUD_TRADER_URL = os.getenv("CLOUD_TRADER_URL", "https://cloud-trader-880429861698.us-central1.run.app")

@app.get("/")
async def root():
    # Try to serve the React app's index.html if it exists
    index_path = "/app/static/index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"status": "running", "service": "trading-dashboard"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/dashboard")
async def dashboard():
    """Get dashboard data"""
    try:
        # Try to get portfolio data
        portfolio = {"error": "Could not fetch portfolio"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ORCHESTRATOR_URL}/portfolio")
                if response.status_code == 200:
                    portfolio = response.json()
        except:
            pass

        # Mock comprehensive dashboard data
        return {
            "portfolio": portfolio,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "side": "LONG",
                    "size": 0.05,
                    "entry_price": 45000,
                    "current_price": 46500,
                    "pnl": 750,
                    "pnl_percent": 3.33,
                    "leverage": 5,
                    "model_used": "DeepSeek-Coder-V2",
                    "timestamp": datetime.utcnow().isoformat()
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SHORT",
                    "size": 1.2,
                    "entry_price": 2800,
                    "current_price": 2750,
                    "pnl": 600,
                    "pnl_percent": 2.14,
                    "leverage": 3,
                    "model_used": "Qwen2.5-Coder",
                    "timestamp": datetime.utcnow().isoformat()
                }
            ],
            "recent_trades": [
                {
                    "id": f"trade_{i}",
                    "symbol": "BTCUSDT" if i % 2 == 0 else "ETHUSDT",
                    "side": "BUY" if i % 3 == 0 else "SELL",
                    "quantity": round(random.uniform(0.01, 0.1), 4),
                    "price": round(random.uniform(40000, 50000), 2),
                    "timestamp": datetime.utcnow().isoformat(),
                    "model_used": random.choice(["DeepSeek-Coder-V2", "Qwen2.5-Coder", "FinGPT", "Phi-3"]),
                    "confidence": round(random.uniform(0.7, 0.95), 2),
                    "status": "completed"
                } for i in range(5)
            ],
            "model_performance": [
                {
                    "model_name": "DeepSeek-Coder-V2",
                    "total_decisions": 45,
                    "successful_trades": 32,
                    "avg_confidence": 0.82,
                    "avg_response_time": 1.2,
                    "win_rate": 0.71,
                    "total_pnl": 1250.50,
                    "last_decision": datetime.utcnow().isoformat()
                },
                {
                    "model_name": "Qwen2.5-Coder",
                    "total_decisions": 38,
                    "successful_trades": 26,
                    "avg_confidence": 0.79,
                    "avg_response_time": 1.5,
                    "win_rate": 0.68,
                    "total_pnl": 890.25,
                    "last_decision": datetime.utcnow().isoformat()
                },
                {
                    "model_name": "FinGPT",
                    "total_decisions": 22,
                    "successful_trades": 15,
                    "avg_confidence": 0.85,
                    "avg_response_time": 0.9,
                    "win_rate": 0.68,
                    "total_pnl": 675.80,
                    "last_decision": datetime.utcnow().isoformat()
                },
                {
                    "model_name": "Phi-3",
                    "total_decisions": 18,
                    "successful_trades": 12,
                    "avg_confidence": 0.77,
                    "avg_response_time": 1.8,
                    "win_rate": 0.67,
                    "total_pnl": 445.60,
                    "last_decision": datetime.utcnow().isoformat()
                }
            ],
            "model_reasoning": [
                {
                    "model_name": random.choice(["DeepSeek-Coder-V2", "Qwen2.5-Coder", "FinGPT", "Phi-3"]),
                    "decision": random.choice(["BUY", "SELL", "HOLD"]),
                    "reasoning": f"Market analysis shows {random.choice(['bullish momentum', 'bearish signals', 'neutral conditions'])} based on volume and price action",
                    "confidence": round(random.uniform(0.7, 0.95), 2),
                    "context": {"rsi": round(random.uniform(30, 70), 1), "volume": round(random.uniform(1000, 5000), 0)},
                    "timestamp": datetime.utcnow().isoformat(),
                    "symbol": random.choice(["BTCUSDT", "ETHUSDT"])
                } for _ in range(3)
            ],
            "system_status": {
                "services": {
                    "cloud_trader": "healthy",
                    "orchestrator": "healthy"
                },
                "models": {
                    "deepseek": "unreachable",
                    "qwen": "unreachable",
                    "fingpt": "unreachable",
                    "phi3": "unreachable"
                },
                "redis_connected": False,
                "timestamp": datetime.utcnow().isoformat()
            },
            "targets": {
                "daily_pnl_target": 50.0,
                "max_drawdown_limit": -100.0,
                "min_confidence_threshold": 0.7,
                "target_win_rate": 0.55,
                "alerts": ["🎯 Daily P&L target achieved", "⚠️ Max drawdown limit exceeded"]
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/portfolio")
async def get_portfolio():
    """Get portfolio data"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{ORCHESTRATOR_URL}/portfolio")
            if response.status_code == 200:
                return response.json()
    except:
        pass
    return {"error": "Could not fetch portfolio"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simple_dashboard:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
