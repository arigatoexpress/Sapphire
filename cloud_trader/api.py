"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .service import TradingService
from .schemas import ChatCompletionRequest, InferenceRequest

# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

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

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add Prometheus instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

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
            return await trading_service.dashboard_snapshot()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to build dashboard snapshot: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to build dashboard snapshot")

    return app
