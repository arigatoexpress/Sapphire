"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from typing import Dict, Optional, List, Any

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
# from fastapi.middleware.cors import CORSMiddleware  # CORS handled manually
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
    AGENT_INFERENCE_TIME,
    AGENT_DECISION_LATENCY,
    AGENT_THROUGHPUT,
    AGENT_INFERENCE_TOKENS,
    AGENT_INFERENCE_COST,
    AGENT_ERROR_RATE,
    AGENT_SUCCESS_RATE,
    AGENT_AVG_CONFIDENCE,
    AGENT_LAST_INFERENCE_TIME,
    AGENT_INFERENCE_COUNT,
    AGENT_RESPONSE_TIME,
    AGENT_MARKET_DATA_LATENCY,
    AGENT_TRADE_EXECUTION_LATENCY,
    AGENT_CIRCUIT_BREAKER_STATE,
    AGENT_FALLBACK_USAGE,
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

# Create the FastAPI app instance at module level
trading_service = TradingService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    print("🚀 STARTUP: Starting trading service...")
    logger.info("🚀 STARTUP: Starting trading service...")
    try:
        await trading_service.start()
        print("✅ STARTUP: Trading service started successfully")
        logger.info("✅ STARTUP: Trading service started successfully")
    except Exception as exc:
        print(f"❌ STARTUP: Failed to start trading service: {exc}")
        logger.exception("❌ STARTUP: Failed to start trading service: %s", exc)

    yield

    logger.info("🛑 SHUTDOWN: Stopping trading service...")
    try:
        await trading_service.stop()
        logger.info("✅ SHUTDOWN: Trading service stopped successfully")
    except Exception as exc:
        logger.exception("❌ SHUTDOWN: Failed to stop trading service: %s", exc)

app = FastAPI(title="Cloud Trader", version="1.0", lifespan=lifespan)

# CORS headers will be handled manually in OPTIONS handlers

# Add Prometheus instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Serve static files if they exist
static_path = "/app/static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


def build_app(service: TradingService | None = None) -> FastAPI:
    trading_service = service or TradingService()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Handle application startup and shutdown."""
        print("🚀 STARTUP: Starting trading service...")
        logger.info("🚀 STARTUP: Starting trading service...")
        try:
            await trading_service.start()
            print("✅ STARTUP: Trading service started successfully")
            logger.info("✅ STARTUP: Trading service started successfully")
        except Exception as exc:
            print(f"❌ STARTUP: Failed to start trading service: {exc}")
            logger.exception("❌ STARTUP: Failed to start trading service: %s", exc)

        yield

        logger.info("🛑 SHUTDOWN: Stopping trading service...")
        try:
            await trading_service.stop()
            logger.info("✅ SHUTDOWN: Trading service stopped successfully")
        except Exception as exc:
            logger.exception("❌ SHUTDOWN: Failed to stop trading service: %s", exc)

    app = FastAPI(title="Cloud Trader", version="1.0", lifespan=lifespan)

    # CORS headers will be handled manually in OPTIONS handlers

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
        from fastapi.responses import JSONResponse
        try:
            status = trading_service.health()
            data = {
                "running": status.running,
                "paper_trading": status.paper_trading,
                "last_error": status.last_error,
            }
        except Exception as e:
            # Return a basic response if health check fails
            data = {
                "running": False,
                "paper_trading": True,
                "last_error": str(e),
            }
        response = JSONResponse(content=data)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.get("/health")
    async def health() -> Dict[str, object]:
        """Alias for /healthz for compatibility"""
        return await healthz()

    admin_token = trading_service.settings.admin_api_token if trading_service and hasattr(trading_service, 'settings') else None
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

        endpoint = chat_request.endpoint or (f"{trading_service.settings.model_endpoint}/v1/chat/completions" if trading_service and hasattr(trading_service, 'settings') and trading_service.settings.model_endpoint else None)
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

    @app.options("/dashboard")
    async def dashboard_options():
        from fastapi.responses import Response
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.options("/healthz")
    async def healthz_options():
        from fastapi.responses import Response
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.options("/start")
    async def start_options():
        from fastapi.responses import Response
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.options("/stop")
    async def stop_options():
        from fastapi.responses import Response
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    @app.get("/dashboard")
    async def dashboard() -> Dict[str, object]:
        """Get comprehensive dashboard data"""
        from fastapi.responses import JSONResponse
        try:
            import asyncio
            # Add timeout to prevent hanging
            data = await asyncio.wait_for(trading_service.dashboard_snapshot(), timeout=10.0)
            response = JSONResponse(content=data)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except asyncio.TimeoutError:
            logger.error("Dashboard snapshot timed out after 10 seconds")
            response = JSONResponse(content={"error": "Dashboard snapshot request timed out"}, status_code=504)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to build dashboard snapshot: %s", exc)
            response = JSONResponse(content={"error": "Failed to build dashboard snapshot"}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/trades/history")
    async def get_trade_history(
        agent_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, object]:
        """Get historical trades with filters"""
        from fastapi.responses import JSONResponse
        from datetime import datetime
        try:
            if not trading_service._storage:
                return JSONResponse(content={"error": "Storage not available"}, status_code=503)
            
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
            
            trades = await trading_service._storage.get_trades(
                agent_id=agent_id,
                symbol=symbol,
                start_date=start,
                end_date=end,
                limit=limit,
            )
            
            response = JSONResponse(content={"trades": trades, "count": len(trades)})
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get trade history: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/agents/performance")
    async def get_agent_performance(
        agent_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, object]:
        """Get agent performance history"""
        from fastapi.responses import JSONResponse
        from datetime import datetime
        try:
            if not trading_service._storage:
                return JSONResponse(content={"error": "Storage not available"}, status_code=503)
            
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
            
            performance = await trading_service._storage.get_agent_performance(
                agent_id=agent_id,
                start_date=start,
                end_date=end,
                limit=limit,
            )
            
            response = JSONResponse(content={"performance": performance, "count": len(performance)})
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get agent performance: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/agents/metrics")
    async def get_agent_metrics(
        agent_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Get real-time performance metrics for agents"""
        from fastapi.responses import JSONResponse
        from .metrics_tracker import get_metrics_tracker
        
        try:
            import time
            metrics_tracker = get_metrics_tracker()
            result = metrics_tracker.get_metrics(agent_id)
            
            # If no metrics found, return default structure for known agents
            # Check if result is empty or if agent_id was requested but not found
            from .service import AGENT_DEFINITIONS
            if not result or (agent_id and agent_id not in result):
                # Ensure result is a dict
                if not result:
                    result = {}
                # Add default structure for all agents or just the requested one
                for agent_def in AGENT_DEFINITIONS:
                    agent = agent_def['id']
                    if agent_id and agent != agent_id:
                        continue
                    if agent not in result:
                        result[agent] = {
                            'agent_id': agent,
                            'latency': {
                                'last_inference_ms': 0,
                                'avg_inference_ms': 0,
                                'p95_inference_ms': 0,
                            },
                            'inference': {
                                'total_count': 0,
                                'total_tokens_input': 0,
                                'total_tokens_output': 0,
                                'avg_cost_usd': 0,
                                'model': agent_def.get('vertex_model', 'unknown'),
                            },
                            'performance': {
                                'throughput': 0,
                                'success_rate': 1.0,
                                'avg_confidence': 0.5,
                                'error_count': 0,
                            },
                            'timestamp': time.time(),
                        }
            
            # Return response
            if agent_id and agent_id in result:
                response = JSONResponse(content={**result[agent_id]})
            else:
                response = JSONResponse(content={"agents": dict(result), "count": len(result)})
            
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
            
        except Exception as exc:
            logger.exception("Failed to get agent metrics: %s", exc)
            # Return default structure on error
            from .service import AGENT_DEFINITIONS
            import time
            result = {}
            for agent_def in AGENT_DEFINITIONS:
                agent = agent_def['id']
                if agent_id and agent != agent_id:
                    continue
                result[agent] = {
                    'agent_id': agent,
                    'latency': {'last_inference_ms': 0, 'avg_inference_ms': 0, 'p95_inference_ms': 0},
                    'inference': {
                        'total_count': 0,
                        'total_tokens_input': 0,
                        'total_tokens_output': 0,
                        'avg_cost_usd': 0,
                        'model': agent_def.get('vertex_model', 'unknown'),
                    },
                    'performance': {'throughput': 0, 'success_rate': 1.0, 'avg_confidence': 0.5, 'error_count': 0},
                    'timestamp': time.time(),
                }
            
            if agent_id and agent_id in result:
                response = JSONResponse(content={**result[agent_id]})
            else:
                response = JSONResponse(content={"agents": dict(result), "count": len(result), "error": str(exc)})
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/analytics/attribution")
    async def get_performance_attribution(
        agent_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, object]:
        """Get performance attribution by strategy, symbol, and period"""
        from fastapi.responses import JSONResponse
        from datetime import datetime
        from .analytics import get_analytics
        try:
            if not trading_service._storage:
                return JSONResponse(content={"error": "Storage not available"}, status_code=503)
            
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
            
            analytics = get_analytics(trading_service._storage)
            attribution = await analytics.performance_attribution(agent_id, start, end)
            
            response = JSONResponse(content=attribution)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get performance attribution: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/analytics/risk-metrics")
    async def get_risk_metrics(
        agent_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, object]:
        """Get risk-adjusted performance metrics"""
        from fastapi.responses import JSONResponse
        from datetime import datetime
        from .analytics import get_analytics
        try:
            if not trading_service._storage:
                return JSONResponse(content={"error": "Storage not available"}, status_code=503)
            
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
            
            analytics = get_analytics(trading_service._storage)
            metrics = await analytics.risk_adjusted_metrics(agent_id, start, end)
            
            response = JSONResponse(content=metrics)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get risk metrics: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
    
    @app.get("/api/analytics/daily-report")
    async def get_daily_report(
        agent_id: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Dict[str, object]:
        """Get daily performance report"""
        from fastapi.responses import JSONResponse
        from datetime import datetime
        from .analytics import get_analytics
        try:
            if not trading_service._storage:
                return JSONResponse(content={"error": "Storage not available"}, status_code=503)

            report_date = datetime.fromisoformat(date) if date else None

            analytics = get_analytics(trading_service._storage)
            report = await analytics.generate_daily_report(agent_id, report_date)

            response = JSONResponse(content=report)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get daily report: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    # Enhanced Aster API endpoints
    @app.post("/api/exchange/position-mode")
    async def change_position_mode(dual_side_position: bool, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Change position mode (Hedge Mode or One-way Mode)"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.change_position_mode(dual_side_position)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to change position mode: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/position-mode")
    async def get_position_mode(request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Get current position mode"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_position_mode()
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get position mode: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/multi-assets-mode")
    async def change_multi_assets_mode(multi_assets_margin: bool, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Change Multi-Asset Mode"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.change_multi_assets_mode(multi_assets_margin)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to change multi-assets mode: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/leverage")
    async def change_leverage(symbol: str, leverage: int, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Change leverage for a symbol"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.change_leverage(symbol, leverage)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to change leverage: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/margin-type")
    async def change_margin_type(symbol: str, margin_type: str, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Change margin type for a symbol"""
        from fastapi.responses import JSONResponse
        from .enums import MarginType
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            margin_type_enum = MarginType(margin_type.upper())
            result = await trading_service._exchange_client.change_margin_type(symbol, margin_type_enum)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to change margin type: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/position-margin")
    async def modify_position_margin(
        symbol: str, amount: float, type_: int, request: Request,
        position_side: Optional[str] = None, _: None = Depends(require_admin)
    ) -> Dict[str, object]:
        """Modify position margin"""
        from fastapi.responses import JSONResponse
        from .enums import PositionSide
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            position_side_enum = PositionSide(position_side.upper()) if position_side else None
            result = await trading_service._exchange_client.modify_position_margin(symbol, amount, type_, position_side_enum)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to modify position margin: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/mark-price")
    async def get_mark_price(symbol: Optional[str] = None) -> Dict[str, object]:
        """Get mark price and funding rate"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_mark_price(symbol)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get mark price: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/funding-rate")
    async def get_funding_rate_history(
        symbol: Optional[str] = None, start_time: Optional[int] = None,
        end_time: Optional[int] = None, limit: int = 100
    ) -> Dict[str, object]:
        """Get funding rate history"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_funding_rate_history(symbol, start_time, end_time, limit)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get funding rate history: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/leverage-brackets")
    async def get_leverage_brackets(symbol: Optional[str] = None, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Get leverage brackets"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_leverage_brackets(symbol)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get leverage brackets: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/adl-quantile")
    async def get_adl_quantile(symbol: Optional[str] = None, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Get ADL quantile estimation"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_adl_quantile(symbol)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get ADL quantile: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/force-orders")
    async def get_force_orders(
        symbol: Optional[str] = None, auto_close_type: Optional[str] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 50, _: None = Depends(require_admin)
    ) -> Dict[str, object]:
        """Get user's force orders (liquidations)"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_force_orders(
                symbol, auto_close_type, start_time, end_time, limit
            )
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get force orders: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/auto-cancel")
    async def auto_cancel_orders(symbol: str, countdown_time: int, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Auto-cancel all open orders after countdown"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.auto_cancel_orders(symbol, countdown_time)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to set auto-cancel: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/exchange/batch-orders")
    async def place_batch_orders(batch_orders: List[Dict[str, Any]], request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Place multiple orders in batch"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.place_batch_orders(batch_orders)
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to place batch orders: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.delete("/api/exchange/batch-orders")
    async def cancel_batch_orders(
        symbol: str, request: Request,
        order_id_list: Optional[List[int]] = None,
        orig_client_order_id_list: Optional[List[str]] = None,
        _: None = Depends(require_admin)
    ) -> Dict[str, object]:
        """Cancel multiple orders"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.cancel_batch_orders(
                symbol, order_id_list, orig_client_order_id_list
            )
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to cancel batch orders: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/account/v4")
    async def get_account_info_v4(request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Get enhanced account information V4"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_account_info_v4()
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get account info V4: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/trades")
    async def get_account_trades(
        symbol: str, start_time: Optional[int] = None, end_time: Optional[int] = None,
        from_id: Optional[int] = None, limit: int = 500, _: None = Depends(require_admin)
    ) -> Dict[str, object]:
        """Get account trade list"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_account_trades(
                symbol, start_time, end_time, from_id, limit
            )
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get account trades: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.get("/api/exchange/income")
    async def get_income_history(
        symbol: Optional[str] = None, income_type: Optional[str] = None,
        start_time: Optional[int] = None, end_time: Optional[int] = None,
        limit: int = 100, _: None = Depends(require_admin)
    ) -> Dict[str, object]:
        """Get income history"""
        from fastapi.responses import JSONResponse
        try:
            if not trading_service._exchange_client:
                return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

            result = await trading_service._exchange_client.get_income_history(
                symbol, income_type, start_time, end_time, limit
            )
            response = JSONResponse(content=result)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get income history: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    # Agent Management Endpoints
    @app.get("/api/agents")
    async def get_agents(request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Get all available and enabled agents."""
        from fastapi.responses import JSONResponse
        try:
            available = trading_service.get_available_agents()
            enabled = trading_service.get_enabled_agents()
            response = JSONResponse(content={
                "available": available,
                "enabled": enabled,
                "total_available": len(available),
                "total_enabled": len(enabled)
            })
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to get agents: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/agents/{agent_id}/enable")
    async def enable_agent(agent_id: str, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Enable a specific agent for autonomous trading."""
        from fastapi.responses import JSONResponse
        try:
            success = await trading_service.enable_agent(agent_id)
            if success:
                response = JSONResponse(content={
                    "status": "enabled",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} has been enabled for autonomous trading"
                })
            else:
                response = JSONResponse(content={
                    "status": "error",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} not found or already enabled"
                }, status_code=400)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to enable agent: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.post("/api/agents/{agent_id}/disable")
    async def disable_agent(agent_id: str, request: Request, _: None = Depends(require_admin)) -> Dict[str, object]:
        """Disable a specific agent from autonomous trading."""
        from fastapi.responses import JSONResponse
        try:
            success = await trading_service.disable_agent(agent_id)
            if success:
                response = JSONResponse(content={
                    "status": "disabled",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} has been disabled from autonomous trading"
                })
            else:
                response = JSONResponse(content={
                    "status": "error",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} not found or already disabled"
                }, status_code=400)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as exc:
            logger.exception("Failed to disable agent: %s", exc)
            response = JSONResponse(content={"error": str(exc)}, status_code=500)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    # Vertex AI endpoints temporarily disabled for service stability
    # @app.get("/api/models/health")
    # async def get_models_health() -> Dict[str, object]:
    #     """Get health status of all Vertex AI models."""
    #     try:
    #         if not trading_service._vertex_client:
    #             return {"status": "Vertex AI not configured", "models": {}}
    #
    #         models_health = await trading_service._vertex_client.list_all_models()
    #         return {
    #             "status": "success",
    #             "models": models_health,
    #             "timestamp": time.time()
    #         }
    #     except Exception as exc:
    #         logger.exception("Failed to get models health: %s", exc)
    #         return {"status": "error", "error": str(exc)}

    # @app.get("/api/models/{agent_id}")
    # async def get_model_info(agent_id: str) -> Dict[str, object]:
    #     """Get detailed information about a specific Vertex AI model."""
    #     return {"status": "Vertex AI temporarily disabled", "agent_id": agent_id}

    # @app.post("/api/models/{agent_id}/test")
    # async def test_model_inference(agent_id: str, _: None = Depends(require_admin)) -> Dict[str, object]:
    #     """Test inference with a specific Vertex AI model."""
    #     return {"status": "Vertex AI temporarily disabled", "agent_id": agent_id}

    # @app.get("/api/models/status")
    # async def get_models_status() -> Dict[str, object]:
    #     """Get overall Vertex AI system status."""
    #     return {"status": "Vertex AI temporarily disabled"}

    # @app.get("/api/models/circuit-breakers")
    # async def get_circuit_breakers() -> Dict[str, object]:
    #     """Get circuit breaker status for all agents."""
    #     return {"status": "Vertex AI temporarily disabled", "circuit_breakers": {}}

    # @app.get("/api/models/performance")
    # async def get_models_performance() -> Dict[str, object]:
    #     """Get performance metrics for all agents."""
    #     return {"status": "Vertex AI temporarily disabled", "performance": {}}

    # @app.post("/api/models/{agent_id}/reset-circuit")
    # async def reset_agent_circuit_breaker(agent_id: str, _: None = Depends(require_admin)) -> Dict[str, object]:
    #     """Reset circuit breaker for a specific agent."""
    #     return {"status": "Vertex AI temporarily disabled", "agent_id": agent_id}

    # @app.get("/api/models/health-detailed")
    # async def get_detailed_health() -> Dict[str, object]:
    #     """Get comprehensive health status including circuit breakers and performance."""
    #     return {"status": "Vertex AI temporarily disabled"}

    # MCP endpoints for agent council
    @app.get("/api/mcp/messages")
    async def get_mcp_messages(limit: int = 50) -> Dict[str, object]:
        """Get recent MCP messages for agent council display."""
        try:
            if not trading_service._mcp:
                return {"messages": [], "status": "mcp_disabled"}

            messages = await trading_service._mcp.get_recent_messages(limit)
            return {
                "messages": messages,
                "status": "connected",
                "count": len(messages)
            }
        except Exception as exc:
            logger.exception("Failed to get MCP messages: %s", exc)
            return {"messages": [], "status": "error", "error": str(exc)}

    @app.websocket("/ws/mcp")
    async def mcp_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time MCP messages."""
        await websocket.accept()
        logger.info("MCP WebSocket connection established")

        try:
            while True:
                # Send heartbeat every 30 seconds
                await asyncio.sleep(30)
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "message": "MCP connection active"
                })
        except Exception as exc:
            logger.exception("MCP WebSocket error: %s", exc)
        finally:
            logger.info("MCP WebSocket connection closed")


    return app
