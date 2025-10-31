"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from prometheus_fastapi_instrumentator import Instrumentator

from .service import TradingService
from .schemas import ChatCompletionRequest, InferenceRequest

# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

# Trading metrics
TRADING_DECISIONS = Counter('trading_decisions_total', 'Total trading decisions made', ['bot_id', 'symbol', 'action'])
PORTFOLIO_BALANCE = Gauge('trading_portfolio_balance', 'Current portfolio balance in USDT')
PORTFOLIO_LEVERAGE = Gauge('trading_portfolio_leverage', 'Current portfolio leverage ratio')
LLM_CONFIDENCE = Histogram('trading_llm_confidence', 'LLM decision confidence distribution', buckets=[0.1, 0.3, 0.5, 0.7, 0.9])
LLM_INFERENCE_TIME = Histogram('trading_llm_inference_duration_seconds', 'LLM inference duration', buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
POSITION_SIZE = Gauge('trading_position_size', 'Current position size', ['symbol'])
RISK_LIMITS_BREACHED = Counter('trading_risk_limits_breached', 'Risk limit breach events', ['limit_type'])


def build_app(service: TradingService | None = None) -> FastAPI:
    trading_service = service or TradingService()
    app = FastAPI(title="Cloud Trader", version="1.0")

    # Add Prometheus instrumentation
    instrumentator = Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    stream_names = {
        "decisions": trading_service.settings.decisions_stream,
        "positions": trading_service.settings.positions_stream,
        "reasoning": trading_service.settings.reasoning_stream,
    }

    # Serve static files if they exist
    static_path = "/app/static"
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/")
    async def root():
        # Try to serve the React app's index.html if it exists
        index_path = "/app/static/index.html"
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return {"status": "ok", "service": "cloud-trader"}

    @app.get("/healthz")
    async def healthz() -> Dict[str, object]:
        status = trading_service.health()
        return {
            "running": status.running,
            "paper_trading": status.paper_trading,
            "last_error": status.last_error,
        }

    @app.post("/start")
    async def start() -> Dict[str, str]:
        asyncio.create_task(trading_service.start())
        return {"status": "starting"}

    @app.post("/stop")
    async def stop() -> Dict[str, str]:
        if not trading_service.health().running:
            raise HTTPException(status_code=400, detail="Service not running")
        asyncio.create_task(trading_service.stop())
        return {"status": "stopping"}

    @app.post("/inference/decisions")
    async def accept_decision(request: InferenceRequest) -> Dict[str, str]:
        await trading_service.accept_inference_decision(request)
        return {"status": "queued"}

    @app.post("/inference/chat")
    async def proxy_chat(request: ChatCompletionRequest) -> Dict[str, object]:
        endpoint = request.endpoint or f"{trading_service.settings.model_endpoint}/v1/chat/completions"
        payload = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(endpoint, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network defensive
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        return {"endpoint": endpoint, "response": response.json()}

    Instrumentator().instrument(app).expose(app)

    @app.get("/streams/{stream_name}")
    async def stream_snapshot(stream_name: str, limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, object]:
        target = stream_names.get(stream_name)
        if not target:
            raise HTTPException(status_code=404, detail="Unknown stream")
        entries = await trading_service.stream_events(target, limit)
        return {"stream": stream_name, "entries": entries}

    @app.get("/dashboard")
    async def dashboard() -> Dict[str, object]:
        """Get comprehensive dashboard data"""
        try:
            # Get portfolio data from orchestrator
            portfolio = {}
            try:
                orchestrator_url = trading_service.settings.orchestrator_url
                if orchestrator_url:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"{orchestrator_url}/portfolio")
                        if response.status_code == 200:
                            portfolio = response.json()
            except Exception as e:
                logger.warning(f"Could not fetch portfolio: {e}")

            # Mock comprehensive dashboard data
            import random
            from datetime import datetime

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
            logger.error(f"Error getting dashboard data: {e}")
            return {"error": str(e)}

    return app
