"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException, Query
from prometheus_fastapi_instrumentator import Instrumentator

from .service import TradingService
from .schemas import ChatCompletionRequest, InferenceRequest


def build_app(service: TradingService | None = None) -> FastAPI:
    trading_service = service or TradingService()
    app = FastAPI(title="Cloud Trader", version="1.0")
    stream_names = {
        "decisions": trading_service.settings.decisions_stream,
        "positions": trading_service.settings.positions_stream,
        "reasoning": trading_service.settings.reasoning_stream,
    }

    @app.get("/")
    async def root() -> Dict[str, str]:
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

    return app
