"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from typing import Dict

import asyncio
import time
from collections import defaultdict
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .service import TradingService
from .schemas import ChatCompletionRequest, InferenceRequest

# Prometheus metrics
from .metrics import (
    ASTER_API_LATENCY,
    ASTER_API_REQUESTS,
    LLM_CONFIDENCE,
    LLM_INFERENCE_TIME,
    PORTFOLIO_BALANCE,
    PORTFOLIO_LEVERAGE,
    POSITION_SIZE,
    RATE_LIMIT_EVENTS,
    RISK_LIMITS_BREACHED,
    TRADING_DECISIONS,
)

logger = logging.getLogger(__name__)

# Rate limiting
class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        # Clean old requests
        self.requests[key] = [req_time for req_time in self.requests[key] if now - req_time < 60]

        if len(self.requests[key]) >= self.requests_per_minute:
            return False

        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter(requests_per_minute=60)  # 60 requests per minute per IP


def build_app(service: TradingService | None = None) -> FastAPI:
    trading_service = service or TradingService()
    app = FastAPI(title="Cloud Trader", version="1.0")

    # Add CORS middleware with production-safe configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://cloud-trader-880429861698.us-central1.run.app",
            "https://cloud-trader-cfxefrvooa-uc.a.run.app",
            "https://sapphiretrade.xyz",
            "https://www.sapphiretrade.xyz",
            "https://api.sapphiretrade.xyz",
            "https://trader.sapphiretrade.xyz",
            "http://localhost:3000",
            "http://localhost:5173",
        ],  # Explicitly allow known origins
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],  # Include OPTIONS for CORS preflight
        allow_headers=["Content-Type", "Authorization", "Accept", "Origin"],  # Include CORS headers
    )

    # Add Prometheus instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

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
        try:
            status = trading_service.health()
            return {
                "running": status.running,
                "paper_trading": status.paper_trading,
                "last_error": status.last_error,
            }
        except Exception as e:
            # Return a basic response if health check fails
            return {
                "running": False,
                "paper_trading": True,
                "last_error": str(e),
            }

    admin_token = trading_service.settings.admin_api_token
    admin_guard_disabled = admin_token is None

    def require_admin(request: Request) -> None:
        nonlocal admin_guard_disabled
        if admin_guard_disabled:
            if not hasattr(require_admin, "_warned"):
                logger.warning("ADMIN_API_TOKEN not configured; allowing admin endpoint access")
                setattr(require_admin, "_warned", True)
            return

        header_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            header_token = auth_header[7:].strip()
        if not header_token:
            header_token = request.headers.get("X-Admin-Token")

        if not header_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin token")

        if not secrets.compare_digest(header_token, admin_token or ""):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")

    @app.post("/start")
    async def start(request: Request, _: None = Depends(require_admin)) -> Dict[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(f"start_{client_ip}"):
            raise HTTPException(status_code=429, detail="Too many requests")

        await trading_service.start()
        return {"status": "started"}

    @app.post("/stop")
    async def stop(request: Request, _: None = Depends(require_admin)) -> Dict[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(f"stop_{client_ip}"):
            raise HTTPException(status_code=429, detail="Too many requests")

        if not trading_service.health().running:
            raise HTTPException(status_code=400, detail="Service not running")
        asyncio.create_task(trading_service.stop())
        return {"status": "stopping"}

    @app.post("/test-telegram")
    async def test_telegram(request: Request, _: None = Depends(require_admin)) -> Dict[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(f"test_telegram_{client_ip}"):
            raise HTTPException(status_code=429, detail="Too many requests")

        await trading_service.send_test_telegram_message()
        return {"status": "test message sent"}

    @app.post("/inference/decisions")
    async def accept_decision(request: Request, inference_request: InferenceRequest, _: None = Depends(require_admin)) -> Dict[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(f"inference_{client_ip}"):
            raise HTTPException(status_code=429, detail="Too many requests")

        # Validate input
        if not inference_request.decision or not hasattr(inference_request.decision, 'side'):
            raise HTTPException(status_code=400, detail="Invalid decision format")
        if not inference_request.context or not hasattr(inference_request.context, 'symbol'):
            raise HTTPException(status_code=400, detail="Invalid context format")

        await trading_service.accept_inference_decision(inference_request)
        return {"status": "queued"}

    @app.post("/inference/chat")
    async def proxy_chat(request: Request, chat_request: ChatCompletionRequest, _: None = Depends(require_admin)) -> Dict[str, object]:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(f"chat_{client_ip}"):
            raise HTTPException(status_code=429, detail="Too many requests")

        # Validate input
        if not chat_request.messages or len(chat_request.messages) == 0:
            raise HTTPException(status_code=400, detail="Messages cannot be empty")
        if chat_request.max_tokens and (chat_request.max_tokens < 1 or chat_request.max_tokens > 4096):
            raise HTTPException(status_code=400, detail="max_tokens must be between 1 and 4096")
        if chat_request.temperature and (chat_request.temperature < 0 or chat_request.temperature > 2):
            raise HTTPException(status_code=400, detail="temperature must be between 0 and 2")

        endpoint = chat_request.endpoint or f"{trading_service.settings.model_endpoint}/v1/chat/completions"
        payload = {
            "model": chat_request.model,
            "messages": [message.model_dump() for message in chat_request.messages],
            "max_tokens": chat_request.max_tokens,
            "temperature": chat_request.temperature,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(endpoint, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network defensive
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        return {"endpoint": endpoint, "response": response.json()}

    @app.get("/dashboard")
    async def dashboard() -> Dict[str, object]:
        """Get comprehensive dashboard data"""
        try:
            import asyncio
            # Add timeout to prevent hanging
            return await asyncio.wait_for(trading_service.dashboard_snapshot(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Dashboard snapshot timed out after 10 seconds")
            raise HTTPException(status_code=504, detail="Dashboard snapshot request timed out")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to build dashboard snapshot: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to build dashboard snapshot")

    return app
