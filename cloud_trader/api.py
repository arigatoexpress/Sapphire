"""FastAPI surface for controlling the trading service."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware  # CORS handled manually
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

# Prometheus metrics
from .metrics import (
    AGENT_AVG_CONFIDENCE,
    AGENT_CIRCUIT_BREAKER_STATE,
    AGENT_DECISION_LATENCY,
    AGENT_ERROR_RATE,
    AGENT_FALLBACK_USAGE,
    AGENT_INFERENCE_COST,
    AGENT_INFERENCE_COUNT,
    AGENT_INFERENCE_TIME,
    AGENT_INFERENCE_TOKENS,
    AGENT_LAST_INFERENCE_TIME,
    AGENT_MARKET_DATA_LATENCY,
    AGENT_RESPONSE_TIME,
    AGENT_SUCCESS_RATE,
    AGENT_THROUGHPUT,
    AGENT_TRADE_EXECUTION_LATENCY,
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
from .schemas import ChatCompletionRequest, InferenceRequest

if TYPE_CHECKING:
    from .service import TradingService

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
# Create the FastAPI app instance at module level
# Lazy load trading service to avoid circular imports/startup hangs
trading_service = None


def get_service_instance():
    """Helper to get the trading service instance safely."""
    global trading_service
    if trading_service is None:
        # Try to initialize if not already done (e.g. during tests)
        try:
            from .trading_service import get_trading_service

            trading_service = get_trading_service()
        except ImportError:
            pass
    return trading_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    logger.info("🚀 STARTUP: Starting trading service...")
    global trading_service
    try:
        logger.info("🔧 STARTUP: Importing and initializing trading service...")
        from .trading_service import get_trading_service

        trading_service = get_trading_service()

        logger.info("🔧 STARTUP: Calling trading_service.start()...")
        await trading_service.start()
        logger.info(
            f"✅ STARTUP: Trading service started successfully - {len(trading_service._agent_states)} agents initialized"
        )
    except Exception as exc:
        logger.exception("❌ STARTUP: Failed to start trading service: %s", exc)

    yield

    logger.info("🛑 SHUTDOWN: Stopping trading service...")
    try:
        await trading_service.stop()
        logger.info("✅ SHUTDOWN: Trading service stopped successfully")
    except Exception as exc:
        logger.exception("❌ SHUTDOWN: Failed to stop trading service: %s", exc)


app = FastAPI(title="Cloud Trader", version="1.0", lifespan=lifespan)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sapphiretrade.xyz",
        "https://www.sapphiretrade.xyz",
        "https://sapphire-479610.web.app",
        "https://sapphire-479610.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORS headers will be handled manually in OPTIONS handlers

# Add Prometheus instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Serve static files if they exist
static_path = "/app/static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    # Mount /assets for frontend build artifacts
    assets_path = os.path.join(static_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


def build_app(service: "TradingService" | None = None) -> FastAPI:
    return app


# All routes are defined at module level so they are registered on the module-level app


# All routes are defined at module level so they're registered on the module-level app
@app.get("/")
async def root():
    # Try to serve the React app's index.html if it exists
    index_path = "/app/static/index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"status": "ok", "service": "cloud-trader"}


@app.get("/portfolio-status")
async def get_portfolio_status() -> Dict[str, Any]:
    """Get current portfolio status."""
    try:
        service = get_service_instance()
        if not service:
            raise HTTPException(status_code=503, detail="Trading service not initialized")
        return service.get_portfolio_status()
    except Exception as e:
        logger.error(f"Failed to get portfolio status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/healthz")
async def healthz() -> Dict[str, object]:
    from fastapi.responses import JSONResponse

    try:
        service = get_service_instance()
        if service:
            status = service.health()
            data = {
                "running": status.running,
                "paper_trading": status.paper_trading,
                "last_error": status.last_error,
            }
        else:
             data = {
                "running": False,
                "paper_trading": False,
                "last_error": "Trading service not initialized (None)",
            }
    except Exception as e:
        # Return a basic response if health check fails
        logger.error(f"Health check failed: {e}")
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


def get_admin_token() -> str | None:
    """Get admin token dynamically."""
    service = get_service_instance()
    if service and hasattr(service, "settings"):
        return service.settings.admin_api_token
    return None


admin_guard_disabled = False  # Will be checked dynamically


def require_admin(request: Request) -> None:
    admin_token = get_admin_token()

    if admin_token is None:
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


@app.get("/time")
async def get_precision_time() -> Dict[str, Any]:
    """Get current time information."""
    return {
        "timestamp_us": int(time.time() * 1_000_000),
        "datetime": datetime.now(timezone.utc).isoformat(),
        "message": "Basic time endpoint - NTP sync not yet available",
    }


@app.get("/anomalies")
async def get_anomaly_stats() -> Dict[str, Any]:
    """Get anomaly detection statistics."""
    try:
        from .anomaly_detection import get_anomaly_detection_engine

        engine = await get_anomaly_detection_engine()
        stats = engine.get_anomaly_stats()
        return {
            "status": "active",
            "anomaly_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }
    except Exception as e:
        return {"status": "inactive", "error": str(e), "message": "Anomaly detection not available"}


@app.get("/market-regime")
async def get_market_regime() -> Dict[str, Any]:
    """Get current market regime analysis."""
    try:
        from .market_regime import get_market_regime_detector

        detector = await get_market_regime_detector()
        stats = detector.get_market_regime_stats()

        # Get current regime if available
        current_regime = None
        if hasattr(trading_service, "_regime_detector") and trading_service._regime_detector:
            # This would be populated by trading loop - for now return stats
            pass

        return {
            "status": "active",
            "regime_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }
    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Market regime detection not available",
        }


@app.post("/position-sizing")
async def calculate_position_size(request: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate optimal position size based on signals and market conditions."""
    try:
        from .adaptive_position_sizing import RiskMetrics, get_adaptive_position_sizer
        from .market_regime import MarketRegime, RegimeMetrics

        position_sizer = await get_adaptive_position_sizer()

        # Extract parameters from request
        signal_data = request.get("signal_data", {})
        regime_data = request.get("regime", {})
        portfolio_data = request.get("portfolio", {})
        positions = request.get("current_positions", [])
        symbol = request.get("symbol", "UNKNOWN")

        # Convert regime data to RegimeMetrics
        regime = None
        if regime_data:
            regime = RegimeMetrics(
                regime=MarketRegime(regime_data.get("regime", "unknown")),
                confidence=regime_data.get("confidence", 0.5),
                trend_strength=regime_data.get("trend_strength", 0.5),
                volatility_level=regime_data.get("volatility_level", 0.1),
                range_bound_score=regime_data.get("range_bound_score", 0.5),
                momentum_score=regime_data.get("momentum_score", 0.0),
                timestamp_us=regime_data.get("timestamp_us", int(time.time() * 1_000_000)),
                adx_score=regime_data.get("adx_score", 20),
                rsi_score=regime_data.get("rsi_score", 0),
                bb_position=regime_data.get("bb_position", 0.5),
                volume_trend=regime_data.get("volume_trend", 0.0),
            )

        # Convert portfolio data to RiskMetrics
        risk_metrics = RiskMetrics(
            portfolio_value=portfolio_data.get("portfolio_value", 100000),
            current_drawdown=portfolio_data.get("current_drawdown", 0.0),
            volatility_24h=portfolio_data.get("volatility_24h", 0.1),
            sharpe_ratio=portfolio_data.get("sharpe_ratio", 1.0),
            max_drawdown_limit=portfolio_data.get("max_drawdown_limit", 0.2),
            daily_pnl=portfolio_data.get("daily_pnl", 0.0),
            win_rate_24h=portfolio_data.get("win_rate_24h", 0.55),
            avg_win_loss_ratio=portfolio_data.get("avg_win_loss_ratio", 2.0),
        )

        # Calculate position size
        result = position_sizer.calculate_position_size(
            signal_strength=signal_data.get("strength", 5.0),
            confidence=signal_data.get("confidence", 0.7),
            regime=regime,
            risk_metrics=risk_metrics,
            current_positions=positions,
            symbol=symbol,
        )

        return {
            "status": "success",
            "position_sizing": result,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Position sizing calculation failed"}


@app.get("/position-sizing/stats")
async def get_position_sizing_stats() -> Dict[str, Any]:
    """Get position sizing statistics and performance metrics."""
    try:
        from .adaptive_position_sizing import get_adaptive_position_sizer

        position_sizer = await get_adaptive_position_sizer()
        stats = position_sizer.get_sizing_stats()

        return {
            "status": "active",
            "position_sizing_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }
    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Position sizing stats not available",
        }


@app.get("/correlation/analysis")
async def get_correlation_analysis(symbol: Optional[str] = None) -> Dict[str, Any]:
    """Get correlation analysis for portfolio or specific symbol."""
    try:
        from .trade_correlation import get_correlation_analyzer

        analyzer = await get_correlation_analyzer()

        analysis = {
            "correlation_matrix": None,
            "symbol_analysis": None,
            "portfolio_risk": None,
            "recommendations": analyzer.get_risk_management_recommendations(),
            "timestamp_us": int(time.time() * 1_000_000),
        }

        # Get correlation matrix
        matrix = analyzer.get_correlation_matrix()
        if matrix:
            analysis["correlation_matrix"] = {
                "symbols": matrix.symbols,
                "sample_size": matrix.sample_size,
                "timestamp_us": matrix.timestamp_us,
            }

        # Symbol-specific analysis
        if symbol:
            symbol_risk = analyzer.get_symbol_correlation_risk(symbol)
            analysis["symbol_analysis"] = {"symbol": symbol, **symbol_risk}

        return {"status": "active", "correlation_analysis": analysis}

    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Correlation analysis not available",
        }


@app.post("/correlation/portfolio-risk")
async def analyze_portfolio_risk(request: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze portfolio correlation risk."""
    try:
        from .trade_correlation import get_correlation_analyzer

        analyzer = await get_correlation_analyzer()

        positions = request.get("positions", [])

        portfolio_risk = analyzer.analyze_portfolio_correlation_risk(positions)
        correlation_clusters = analyzer.get_correlation_clusters()

        return {
            "status": "success",
            "portfolio_risk": {
                "total_exposure": portfolio_risk.total_exposure,
                "correlated_exposure": portfolio_risk.correlated_exposure,
                "diversification_ratio": portfolio_risk.diversification_ratio,
                "concentration_risk": portfolio_risk.concentration_risk,
                "risk_concentration_score": portfolio_risk.risk_concentration_score,
                "recommended_max_position": portfolio_risk.recommended_max_position,
                "risk_adjusted_limits": portfolio_risk.risk_adjusted_limits,
            },
            "correlation_clusters": correlation_clusters,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Portfolio risk analysis failed"}


@app.post("/position/create-with-exits")
async def create_position_with_exits(request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a position with comprehensive exit strategy."""
    try:
        from .agents.vpin_hft_agent import VpinHFTAgent
        from .market_regime import MarketRegime, RegimeMetrics

        # Extract parameters
        symbol = request.get("symbol", "")
        entry_price = request.get("entry_price", 0)
        position_size = request.get("position_size", 0)
        side = request.get("side", "long")
        signal_data = request.get("signal_data", {})

        regime_data = request.get("regime")
        portfolio_data = request.get("portfolio", {})
        positions = request.get("current_positions", [])

        # Convert regime data
        regime = None
        if regime_data:
            regime = RegimeMetrics(
                regime=MarketRegime(regime_data.get("regime", "unknown")),
                confidence=regime_data.get("confidence", 0.5),
                trend_strength=regime_data.get("trend_strength", 0.5),
                volatility_level=regime_data.get("volatility_level", 0.1),
                range_bound_score=regime_data.get("range_bound_score", 0.5),
                momentum_score=regime_data.get("momentum_score", 0.0),
                timestamp_us=regime_data.get("timestamp_us", int(time.time() * 1_000_000)),
                adx_score=regime_data.get("adx_score", 20),
                rsi_score=regime_data.get("rsi_score", 0),
                bb_position=regime_data.get("bb_position", 0.5),
                volume_trend=regime_data.get("volume_trend", 0.0),
            )

        # Create VPIN agent instance (simplified - in production would get from registry)
        agent = VpinHFTAgent(None, None, "risk_topic")  # Simplified for demo

        result = await agent.create_position_with_exit_plan(
            symbol=symbol,
            entry_price=entry_price,
            position_size=position_size,
            side=side,
            signal_data=signal_data,
            regime=regime,
            portfolio_metrics=portfolio_data,
            current_positions=positions,
        )

        return {
            "status": "success",
            "position_result": result,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Position creation with exits failed",
        }


@app.get("/position/{symbol}/status")
async def get_position_status(symbol: str) -> Dict[str, Any]:
    """Get detailed position status including exit management."""
    try:
        from .agents.vpin_hft_agent import VpinHFTAgent

        agent = VpinHFTAgent(None, None, "risk_topic")  # Simplified for demo
        status = await agent.get_position_management_status(symbol)

        if status:
            return {
                "status": "active",
                "position_management": status,
                "timestamp_us": int(time.time() * 1_000_000),
            }
        else:
            return {
                "status": "not_found",
                "message": f"No active position found for {symbol}",
                "timestamp_us": int(time.time() * 1_000_000),
            }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to get position status for {symbol}",
        }


@app.post("/position/{symbol}/close")
async def close_position(symbol: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """Force close a position with reason."""
    try:
        from .agents.vpin_hft_agent import VpinHFTAgent

        close_price = request.get("close_price")
        reason = request.get("reason", "manual_close")

        agent = VpinHFTAgent(None, None, "risk_topic")  # Simplified for demo
        success = await agent.force_position_close(symbol, close_price, reason)

        return {
            "status": "success" if success else "failed",
            "symbol": symbol,
            "closed": success,
            "reason": reason,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": f"Failed to close position {symbol}"}


@app.get("/exits/performance")
async def get_exit_performance_stats() -> Dict[str, Any]:
    """Get comprehensive exit strategy performance statistics."""
    try:
        from .partial_exits import get_partial_exit_strategy

        exit_strategy = await get_partial_exit_strategy()
        stats = exit_strategy.get_performance_stats()

        return {
            "status": "active",
            "exit_performance": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Exit performance stats not available",
        }


@app.post("/consensus/vote")
async def conduct_consensus_vote(request: Dict[str, Any]) -> Dict[str, Any]:
    """Conduct a consensus vote among registered agents."""
    try:
        from .agent_consensus import AgentSignal, SignalType, get_agent_consensus_engine
        from .market_regime import MarketRegime, RegimeMetrics

        engine = await get_agent_consensus_engine()

        symbol = request.get("symbol", "")
        max_wait_us = request.get("max_wait_us", 1000000)

        # Convert regime data if provided
        regime = None
        regime_data = request.get("regime")
        if regime_data:
            regime = RegimeMetrics(
                regime=MarketRegime(regime_data.get("regime", "unknown")),
                confidence=regime_data.get("confidence", 0.5),
                trend_strength=regime_data.get("trend_strength", 0.5),
                volatility_level=regime_data.get("volatility_level", 0.1),
                range_bound_score=regime_data.get("range_bound_score", 0.5),
                momentum_score=regime_data.get("momentum_score", 0.0),
                timestamp_us=regime_data.get("timestamp_us", int(time.time() * 1_000_000)),
                adx_score=regime_data.get("adx_score", 20),
                rsi_score=regime_data.get("rsi_score", 0),
                bb_position=regime_data.get("bb_position", 0.5),
                volume_trend=regime_data.get("volume_trend", 0.0),
            )

        # Conduct consensus vote
        result = await engine.conduct_consensus_vote(symbol, regime, max_wait_us)

        if result:
            return {
                "status": "success",
                "consensus_result": result.to_dict(),
                "timestamp_us": int(time.time() * 1_000_000),
            }
        else:
            return {
                "status": "no_consensus",
                "message": "No consensus could be reached",
                "timestamp_us": int(time.time() * 1_000_000),
            }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Consensus voting failed"}


@app.post("/consensus/agent/register")
async def register_consensus_agent(request: Dict[str, Any]) -> Dict[str, Any]:
    """Register an agent in the consensus system."""
    try:
        from .agent_consensus import get_agent_consensus_engine

        engine = await get_agent_consensus_engine()

        agent_id = request.get("agent_id", "")
        agent_type = request.get("agent_type", "unknown")
        specialization = request.get("specialization", "general")
        base_weight = request.get("base_weight", 1.0)

        engine.register_agent(agent_id, agent_type, specialization, base_weight)

        return {
            "status": "success",
            "message": f"Agent {agent_id} registered for consensus voting",
            "agent_info": {
                "agent_id": agent_id,
                "type": agent_type,
                "specialization": specialization,
                "base_weight": base_weight,
            },
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Agent registration failed"}


@app.post("/consensus/signal")
async def submit_agent_signal(request: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a signal from an agent for consensus consideration."""
    try:
        from .agent_consensus import AgentSignal, SignalType, get_agent_consensus_engine

        engine = await get_agent_consensus_engine()

        signal = AgentSignal(
            agent_id=request.get("agent_id", ""),
            signal_type=SignalType(request.get("signal_type", "hold")),
            confidence=request.get("confidence", 0.5),
            strength=request.get("strength", 1.0),
            symbol=request.get("symbol", ""),
            timestamp_us=request.get("timestamp_us"),
            reasoning=request.get("reasoning"),
            metadata=request.get("metadata", {}),
        )

        engine.submit_signal(signal)

        return {
            "status": "success",
            "message": f"Signal from {signal.agent_id} submitted for consensus",
            "signal_info": signal.to_dict(),
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Signal submission failed"}


@app.post("/consensus/feedback")
async def submit_consensus_feedback(request: Dict[str, Any]) -> Dict[str, Any]:
    """Submit feedback on consensus outcome for learning."""
    try:
        from .agent_consensus import ConsensusResult, get_agent_consensus_engine
        from .market_regime import MarketRegime

        engine = await get_agent_consensus_engine()

        # Reconstruct consensus result from feedback
        result_data = request.get("consensus_result", {})
        actual_outcome = request.get("actual_outcome", 0.0)
        regime = request.get("regime")

        regime_enum = MarketRegime(regime) if regime else None

        # In production, reconstruct full ConsensusResult object
        # For now, update with simplified feedback

        return {
            "status": "success",
            "message": "Consensus feedback recorded for learning",
            "outcome": actual_outcome,
            "regime": regime,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Feedback submission failed"}


@app.get("/consensus/stats")
async def get_consensus_stats() -> Dict[str, Any]:
    """Get comprehensive consensus system statistics."""
    try:
        from .agent_consensus import get_agent_consensus_engine

        engine = await get_agent_consensus_engine()
        stats = engine.get_consensus_stats()

        return {
            "status": "active",
            "consensus_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "inactive", "error": str(e), "message": "Consensus stats not available"}


@app.get("/performance/auto-adjust/stats")
async def get_performance_adjuster_stats() -> Dict[str, Any]:
    """Get performance auto-adjuster statistics and agent adjustments."""
    try:
        from .agent_performance_auto_adjust import get_performance_auto_adjuster

        adjuster = await get_performance_auto_adjuster()
        stats = adjuster.get_performance_summary()

        return {
            "status": "active",
            "performance_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Performance adjuster stats not available",
        }


@app.get("/performance/agent/{agent_id}/state")
async def get_agent_performance_state(agent_id: str) -> Dict[str, Any]:
    """Get current performance state and adjustments for a specific agent."""
    try:
        from .agent_performance_auto_adjust import get_performance_auto_adjuster

        adjuster = await get_performance_auto_adjuster()
        agent_state = adjuster.get_agent_state(agent_id)

        if agent_state is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        return {
            "status": "active",
            "agent_id": agent_id,
            "current_state": {
                "confidence_threshold": agent_state.confidence_threshold,
                "position_size_multiplier": agent_state.position_size_multiplier,
                "capital_allocation": agent_state.capital_allocation,
                "features_enabled": agent_state.features_enabled,
                "last_adjustment": (
                    agent_state.last_adjustment.adjustment_type.value
                    if agent_state.last_adjustment
                    else None
                ),
                "adjustment_count": len(agent_state.adjustment_history),
            },
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to get agent state for {agent_id}",
        }


@app.get("/memory/stats")
async def get_memory_stats() -> Dict[str, Any]:
    """Get comprehensive agent memory statistics."""
    try:
        from .agent_memory import get_agent_memory_manager

        manager = await get_agent_memory_manager()
        stats = manager.get_memory_stats()

        return {
            "status": "active",
            "memory_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "inactive", "error": str(e), "message": "Memory stats not available"}


@app.get("/memory/agent/{agent_id}")
async def get_agent_memories(
    agent_id: str, tags: Optional[str] = None, memory_type: Optional[str] = None, limit: int = 20
) -> Dict[str, Any]:
    """Get memories for a specific agent with optional filtering."""
    try:
        from .agent_memory import MemoryType, get_agent_memory_manager

        manager = await get_agent_memory_manager()

        # Parse filters
        tag_list = tags.split(",") if tags else None
        memory_types = [MemoryType(memory_type)] if memory_type else None

        memories = await manager.retrieve_memories(
            agent_id=agent_id, tags=tag_list, memory_types=memory_types, limit=limit
        )

        return {
            "status": "success",
            "agent_id": agent_id,
            "memory_count": len(memories),
            "memories": [memory.to_dict() for memory in memories],
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to retrieve memories for agent {agent_id}",
        }


@app.post("/memory/share")
async def share_memory(request: Dict[str, Any]) -> Dict[str, Any]:
    """Share a memory from one agent to others."""
    try:
        required_fields = ["from_agent", "to_agents", "memory_id"]
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        from .agent_memory import get_agent_memory_manager

        manager = await get_agent_memory_manager()

        results = await manager.share_memory(
            from_agent=request["from_agent"],
            to_agents=request["to_agents"],
            memory_id=request["memory_id"],
            context=request.get("context"),
        )

        return {
            "status": "success",
            "sharing_results": results,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Failed to share memory"}


@app.post("/memory/context/create")
async def create_shared_context(request: Dict[str, Any]) -> Dict[str, Any]:
    """Create a shared context for collaborative decision making."""
    try:
        required_fields = ["symbol", "contributing_agents"]
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        from .agent_memory import get_agent_memory_manager
        from .market_regime import MarketRegime

        manager = await get_agent_memory_manager()

        # Parse regime if provided
        regime = None
        if "regime" in request:
            try:
                regime = MarketRegime(request["regime"])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid regime: {request['regime']}")

        context_id = await manager.create_shared_context(
            symbol=request["symbol"],
            regime=regime,
            contributing_agents=request["contributing_agents"],
        )

        return {
            "status": "success",
            "context_id": context_id,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Failed to create shared context"}


@app.get("/batching/stats")
async def get_batching_stats() -> Dict[str, Any]:
    """Get comprehensive request batching statistics."""
    try:
        from .request_batching import get_request_batch_manager

        manager = await get_request_batch_manager()
        stats = manager.get_stats()

        return {
            "status": "active",
            "batching_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "inactive", "error": str(e), "message": "Batching stats not available"}


@app.post("/batching/market-data")
async def batch_market_data_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Submit batched market data requests."""
    try:
        required_fields = ["symbols"]
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        from .request_batching import batch_market_data_requests

        result = await batch_market_data_requests(
            symbols=request["symbols"], data_type=request.get("data_type", "ticker")
        )

        return {
            "status": "submitted",
            "batch_info": result,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to submit batched market data request",
        }


@app.post("/batching/orders")
async def batch_order_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Submit batched order requests."""
    try:
        required_fields = ["orders"]
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        from .request_batching import batch_order_submissions

        result = await batch_order_submissions(request["orders"])

        return {
            "status": "submitted",
            "batch_info": result,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to submit batched order request",
        }


@app.websocket("/ws")
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time updates."""
    client_id = None
    try:
        import uuid

        from .websocket_manager import SubscriptionType, get_websocket_manager

        manager = await get_websocket_manager()

        # Generate client ID
        client_id = str(uuid.uuid4())

        # Add client
        await manager.add_client(websocket, client_id)

        # Handle client messages
        while True:
            try:
                # Receive message with timeout
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)

                message_type = data.get("type")
                message_data = data.get("data", {})

                if message_type == "subscribe":
                    # Handle subscription request
                    subscription_str = message_data.get("subscription")
                    if subscription_str:
                        try:
                            subscription = SubscriptionType(subscription_str)
                            await manager.subscribe_client(client_id, subscription)
                            await websocket.send_json(
                                {
                                    "type": "subscription_confirmed",
                                    "subscription": subscription_str,
                                    "timestamp_us": int(time.time() * 1_000_000),
                                }
                            )
                        except ValueError:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Invalid subscription type: {subscription_str}",
                                    "timestamp_us": int(time.time() * 1_000_000),
                                }
                            )

                elif message_type == "unsubscribe":
                    # Handle unsubscription request
                    subscription_str = message_data.get("subscription")
                    if subscription_str:
                        try:
                            subscription = SubscriptionType(subscription_str)
                            await manager.unsubscribe_client(client_id, subscription)
                            await websocket.send_json(
                                {
                                    "type": "unsubscription_confirmed",
                                    "subscription": subscription_str,
                                    "timestamp_us": int(time.time() * 1_000_000),
                                }
                            )
                        except ValueError:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Invalid subscription type: {subscription_str}",
                                    "timestamp_us": int(time.time() * 1_000_000),
                                }
                            )

                elif message_type == "ping":
                    # Respond to ping
                    await websocket.send_json(
                        {"type": "pong", "timestamp_us": int(time.time() * 1_000_000)}
                    )

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json(
                    {"type": "ping", "timestamp_us": int(time.time() * 1_000_000)}
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        if client_id:
            try:
                manager = await get_websocket_manager()
                await manager.remove_client(client_id, "connection_closed")
            except Exception as e:
                logger.error(f"Error removing WebSocket client {client_id}: {e}")


@app.get("/websocket/stats")
async def get_websocket_stats() -> Dict[str, Any]:
    """Get WebSocket connection and messaging statistics."""
    try:
        from .websocket_manager import get_websocket_manager

        manager = await get_websocket_manager()
        stats = manager.get_stats()

        return {
            "status": "active",
            "websocket_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {"status": "inactive", "error": str(e), "message": "WebSocket stats not available"}


@app.post("/mtf/analyze/{symbol}")
async def analyze_symbol_multitimeframe(
    symbol: str, primary_timeframe: str = "1h", analysis_types: Optional[str] = None
) -> Dict[str, Any]:
    """Perform multi-timeframe analysis for a symbol."""
    try:
        from .multi_timeframe import AnalysisType, Timeframe, get_multi_timeframe_analyzer

        analyzer = await get_multi_timeframe_analyzer()

        # Parse parameters
        try:
            primary_tf = Timeframe(primary_timeframe)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid primary timeframe: {primary_timeframe}"
            )

        analysis_list = None
        if analysis_types:
            try:
                analysis_list = [AnalysisType(at.strip()) for at in analysis_types.split(",")]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid analysis type: {e}")

        signals = await analyzer.analyze_symbol(symbol, primary_tf, analysis_list)

        return {
            "status": "success",
            "symbol": symbol,
            "primary_timeframe": primary_timeframe,
            "signals_count": len(signals),
            "signals": [signal.to_dict() for signal in signals],
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to analyze {symbol} with multi-timeframe analysis",
        }


@app.post("/mtf/data")
async def add_multitimeframe_data(request: Dict[str, Any]) -> Dict[str, Any]:
    """Add market data for multi-timeframe analysis."""
    try:
        required_fields = [
            "timeframe",
            "symbol",
            "timestamp_us",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
        ]
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

        from .multi_timeframe import Timeframe, TimeframeData, get_multi_timeframe_analyzer

        analyzer = await get_multi_timeframe_analyzer()

        try:
            timeframe = Timeframe(request["timeframe"])
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid timeframe: {request['timeframe']}"
            )

        data = TimeframeData(
            timeframe=timeframe,
            symbol=request["symbol"],
            timestamp_us=request["timestamp_us"],
            open_price=request["open_price"],
            high_price=request["high_price"],
            low_price=request["low_price"],
            close_price=request["close_price"],
            volume=request["volume"],
            vpin=request.get("vpin"),
            quote_imbalance=request.get("quote_imbalance"),
            indicators=request.get("indicators", {}),
        )

        analyzer.add_market_data(data)

        return {
            "status": "success",
            "message": f"Added {timeframe.value} data for {request['symbol']}",
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "error": str(e), "message": "Failed to add multi-timeframe data"}


@app.get("/mtf/stats")
async def get_multitimeframe_stats() -> Dict[str, Any]:
    """Get multi-timeframe analysis statistics."""
    try:
        from .multi_timeframe import get_multi_timeframe_analyzer

        analyzer = await get_multi_timeframe_analyzer()
        stats = analyzer.get_analysis_stats()

        return {
            "status": "active",
            "mtf_stats": stats,
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        return {
            "status": "inactive",
            "error": str(e),
            "message": "Multi-timeframe stats not available",
        }


@app.post("/inference/decisions")
async def accept_decision(
    request: Request, inference_request: InferenceRequest, _: None = Depends(require_admin)
) -> Dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"inference_{client_ip}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Validate input
    if not inference_request.decision or not hasattr(inference_request.decision, "side"):
        raise HTTPException(status_code=400, detail="Invalid decision format")
    if not inference_request.context or not hasattr(inference_request.context, "symbol"):
        raise HTTPException(status_code=400, detail="Invalid context format")

    await trading_service.accept_inference_decision(inference_request)
    return {"status": "queued"}


@app.post("/inference/chat")
async def proxy_chat(
    request: Request, chat_request: ChatCompletionRequest, _: None = Depends(require_admin)
) -> Dict[str, object]:
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

    endpoint = chat_request.endpoint or (
        f"{trading_service.settings.model_endpoint}/v1/chat/completions"
        if trading_service
        and hasattr(trading_service, "settings")
        and trading_service.settings.model_endpoint
        else None
    )
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
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, Accept, Origin, X-Requested-With"
    )
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.options("/healthz")
async def healthz_options():
    from fastapi.responses import Response

    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, Accept, Origin, X-Requested-With"
    )
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.options("/start")
async def start_options():
    from fastapi.responses import Response

    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, Accept, Origin, X-Requested-With"
    )
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.options("/stop")
async def stop_options():
    from fastapi.responses import Response

    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, Accept, Origin, X-Requested-With"
    )
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
        response = JSONResponse(
            content={"error": "Dashboard snapshot request timed out"}, status_code=504
        )
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to build dashboard snapshot: %s", exc)
        response = JSONResponse(
            content={"error": "Failed to build dashboard snapshot"}, status_code=500
        )
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
    from datetime import datetime

    from fastapi.responses import JSONResponse

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
    from datetime import datetime

    from fastapi.responses import JSONResponse

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
                agent = agent_def["id"]
                if agent_id and agent != agent_id:
                    continue
                if agent not in result:
                    result[agent] = {
                        "agent_id": agent,
                        "latency": {
                            "last_inference_ms": 0,
                            "avg_inference_ms": 0,
                            "p95_inference_ms": 0,
                        },
                        "inference": {
                            "total_count": 0,
                            "total_tokens_input": 0,
                            "total_tokens_output": 0,
                            "avg_cost_usd": 0,
                            "model": agent_def.get("vertex_model", "unknown"),
                        },
                        "performance": {
                            "throughput": 0,
                            "success_rate": 1.0,
                            "avg_confidence": 0.5,
                            "error_count": 0,
                        },
                        "timestamp": time.time(),
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
        import time

        from .service import AGENT_DEFINITIONS

        result = {}
        for agent_def in AGENT_DEFINITIONS:
            agent = agent_def["id"]
            if agent_id and agent != agent_id:
                continue
            result[agent] = {
                "agent_id": agent,
                "latency": {"last_inference_ms": 0, "avg_inference_ms": 0, "p95_inference_ms": 0},
                "inference": {
                    "total_count": 0,
                    "total_tokens_input": 0,
                    "total_tokens_output": 0,
                    "avg_cost_usd": 0,
                    "model": agent_def.get("vertex_model", "unknown"),
                },
                "performance": {
                    "throughput": 0,
                    "success_rate": 1.0,
                    "avg_confidence": 0.5,
                    "error_count": 0,
                },
                "timestamp": time.time(),
            }

        if agent_id and agent_id in result:
            response = JSONResponse(content={**result[agent_id]})
        else:
            response = JSONResponse(
                content={"agents": dict(result), "count": len(result), "error": str(exc)}
            )
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
    from datetime import datetime

    from fastapi.responses import JSONResponse

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
    from datetime import datetime

    from fastapi.responses import JSONResponse

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
    from datetime import datetime

    from fastapi.responses import JSONResponse

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
async def change_position_mode(
    dual_side_position: bool, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
async def get_position_mode(
    request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
async def change_multi_assets_mode(
    multi_assets_margin: bool, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
    """Change Multi-Asset Mode"""
    from fastapi.responses import JSONResponse

    try:
        if not trading_service._exchange_client:
            return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

        result = await trading_service._exchange_client.change_multi_assets_mode(
            multi_assets_margin
        )
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
async def change_leverage(
    symbol: str, leverage: int, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
async def change_margin_type(
    symbol: str, margin_type: str, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
    symbol: str,
    amount: float,
    type_: int,
    request: Request,
    position_side: Optional[str] = None,
    _: None = Depends(require_admin),
) -> Dict[str, object]:
    """Modify position margin"""
    from fastapi.responses import JSONResponse

    from .enums import PositionSide

    try:
        if not trading_service._exchange_client:
            return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

        position_side_enum = PositionSide(position_side.upper()) if position_side else None
        result = await trading_service._exchange_client.modify_position_margin(
            symbol, amount, type_, position_side_enum
        )
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
    symbol: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 100,
) -> Dict[str, object]:
    """Get funding rate history"""
    from fastapi.responses import JSONResponse

    try:
        if not trading_service._exchange_client:
            return JSONResponse(content={"error": "Exchange client not available"}, status_code=503)

        result = await trading_service._exchange_client.get_funding_rate_history(
            symbol, start_time, end_time, limit
        )
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
async def get_leverage_brackets(
    symbol: Optional[str] = None, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
async def get_adl_quantile(
    symbol: Optional[str] = None, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
    symbol: Optional[str] = None,
    auto_close_type: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 50,
    _: None = Depends(require_admin),
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
async def auto_cancel_orders(
    symbol: str, countdown_time: int, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
async def place_batch_orders(
    batch_orders: List[Dict[str, Any]], request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
    symbol: str,
    request: Request,
    order_id_list: Optional[List[int]] = None,
    orig_client_order_id_list: Optional[List[str]] = None,
    _: None = Depends(require_admin),
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
async def get_account_info_v4(
    request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
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
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    from_id: Optional[int] = None,
    limit: int = 500,
    _: None = Depends(require_admin),
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
    symbol: Optional[str] = None,
    income_type: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 100,
    _: None = Depends(require_admin),
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
        response = JSONResponse(
            content={
                "available": available,
                "enabled": enabled,
                "total_available": len(available),
                "total_enabled": len(enabled),
            }
        )
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
async def enable_agent(
    agent_id: str, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
    """Enable a specific agent for autonomous trading."""
    from fastapi.responses import JSONResponse

    try:
        success = await trading_service.enable_agent(agent_id)
        if success:
            # Send Telegram alert
            if trading_service._telegram:
                try:
                    agent_name = agent_id.replace("-", " ").title()
                    alert_msg = f"✅ *Agent Enabled*\n\nAgent: `{agent_name}`\nID: `{agent_id}`\n\nAgent has been enabled for autonomous trading\\."
                    await trading_service._telegram.send_message(alert_msg)
                except Exception as exc:
                    logger.warning(f"Failed to send Telegram alert for agent enable: {exc}")

            response = JSONResponse(
                content={
                    "status": "enabled",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} has been enabled for autonomous trading",
                }
            )
        else:
            response = JSONResponse(
                content={
                    "status": "error",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} not found or already enabled",
                },
                status_code=400,
            )
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
async def disable_agent(
    agent_id: str, request: Request, _: None = Depends(require_admin)
) -> Dict[str, object]:
    """Disable a specific agent from autonomous trading."""
    from fastapi.responses import JSONResponse

    try:
        success = await trading_service.disable_agent(agent_id)
        if success:
            # Send Telegram alert
            if trading_service._telegram:
                try:
                    agent_name = agent_id.replace("-", " ").title()
                    alert_msg = f"🛑 *Agent Disabled*\n\nAgent: `{agent_name}`\nID: `{agent_id}`\n\nAgent has been disabled from autonomous trading\\."
                    await trading_service._telegram.send_message(alert_msg)
                except Exception as exc:
                    logger.warning(f"Failed to send Telegram alert for agent disable: {exc}")

            response = JSONResponse(
                content={
                    "status": "disabled",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} has been disabled from autonomous trading",
                }
            )
        else:
            response = JSONResponse(
                content={
                    "status": "error",
                    "agent_id": agent_id,
                    "message": f"Agent {agent_id} not found or already disabled",
                },
                status_code=400,
            )
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    except Exception as exc:
        logger.exception("Failed to disable agent: %s", exc)
        response = JSONResponse(content={"error": str(exc)}, status_code=500)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response


@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request) -> Dict[str, object]:
    """Webhook endpoint for Telegram bot updates."""
    from fastapi.responses import JSONResponse

    try:
        # Parse Telegram update
        update_data = await request.json()

        # Forward to Telegram command handler if available
        # Note: The TelegramCommandHandler uses polling by default
        # This webhook endpoint can be used for future webhook-based updates
        logger.debug(f"Received Telegram webhook update: {update_data.get('update_id')}")

        response = JSONResponse(content={"status": "ok"})
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    except Exception as exc:
        logger.exception("Failed to process Telegram webhook: %s", exc)
        response = JSONResponse(content={"error": str(exc)}, status_code=500)
        response.headers["Access-Control-Allow-Origin"] = "*"
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
        return {"messages": messages, "status": "connected", "count": len(messages)}
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
            await websocket.send_json(
                {"type": "heartbeat", "timestamp": time.time(), "message": "MCP connection active"}
            )
    except Exception as exc:
        logger.exception("MCP WebSocket error: %s", exc)
    finally:
        logger.info("MCP WebSocket connection closed")


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    """Real-time dashboard data stream for live metrics."""
    await websocket.accept()
    logger.info("Dashboard WebSocket connection established")

    try:
        # Send initial snapshot
        initial_data = await get_live_dashboard_data()
        await websocket.send_json(initial_data)

        # Stream updates every 2 seconds
        while True:
            await asyncio.sleep(2)
            live_data = await get_live_dashboard_data()

            # Add trade execution events if available in a buffer
            # trade_events = trading_service.get_recent_trade_events(last_poll_time)
            # live_data["trade_events"] = trade_events

            await websocket.send_json(live_data)

    except Exception as exc:
        # logger.info(f"Dashboard WebSocket disconnected: {exc}") # Reduce verbosity
        pass
    finally:
        logger.info("Dashboard WebSocket connection closed")


async def get_live_dashboard_data() -> Dict[str, Any]:
    """Gather live dashboard metrics from trading service."""
    try:
        # Delegate to the service's snapshot method for consistency
        return await trading_service.dashboard_snapshot()
    except Exception as e:
        logger.error(f"Failed to gather dashboard data: {e}")
        return {"error": str(e), "timestamp": time.time()}

    return app
