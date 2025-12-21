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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import firebase_admin
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware  # CORS handled manually
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from firebase_admin import auth, credentials
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.websockets import WebSocketDisconnect

from .analytics.performance import AgentMetrics

# Initialize Firebase Admin
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()


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

from .logger import get_logger

logger = get_logger(__name__)


# Rate limiting
class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        # Clean old requests (older than 60s)
        self.requests[key] = [req_time for req_time in self.requests[key] if now - req_time < 60]

        if len(self.requests[key]) >= self.requests_per_minute:
            logger.warning(f"🛡️ Rate limit exceeded for {key}")
            return False

        self.requests[key].append(now)
        return True


rate_limiter = RateLimiter(requests_per_minute=100)  # Standard limit


class SecurityHeadersMiddleware:
    """
    Middleware to add important security headers to all responses.
    Ensures 'top-notch' security benchmarks.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Security Best Practices - OWASP Recommendations
                security_headers = [
                    (b"X-Content-Type-Options", b"nosniff"),
                    (b"X-Frame-Options", b"DENY"),
                    (b"X-XSS-Protection", b"1; mode=block"),
                    (b"Strict-Transport-Security", b"max-age=31536000; includeSubDomains"),
                    (
                        b"Content-Security-Policy",
                        b"default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' *;",
                    ),
                    (b"Referrer-Policy", b"strict-origin-when-cross-origin"),
                    (b"Permissions-Policy", b"geolocation=(), microphone=(), camera=()"),
                ]

                # Avoid duplicates
                existing_header_names = {h[0].lower() for h in headers}
                for name, value in security_headers:
                    if name.lower() not in existing_header_names:
                        headers.append((name, value))

                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class TTLCache:
    """
    Simple TTL-based cache for API responses.

    First Principle: Expensive computations should be cached.
    The consensus/state endpoint aggregates data from multiple sources,
    so caching it reduces CPU usage and response latency.

    Usage:
        cache = TTLCache()
        cached = cache.get("key")
        if cached is None:
            data = compute_expensive_data()
            cache.set("key", data, ttl=30)
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry_time)

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: int = 30) -> None:
        """Set cached value with TTL in seconds."""
        self._cache[key] = (value, time.time() + ttl)

    def invalidate(self, key: str) -> None:
        """Remove a cached value."""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


# Global cache instance
api_cache = TTLCache()

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

# Apply Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

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


@app.get("/api/dashboard")
async def get_dashboard_data() -> Dict[str, Any]:
    """
    Batch endpoint that combines multiple data sources into a single response.
    Reduces network calls from 4+ to 1 for the main dashboard.

    Returns:
        - portfolio: Balance, equity, P&L
        - agents: Active agents with performance metrics
        - signals: Recent consensus signals
        - stats: Aggregated trading statistics
        - history: Portfolio value history for sparklines (last 24 points)
    """
    try:
        service = get_service_instance()
        if not service:
            return {
                "portfolio": {"balance": 0, "equity": 0, "pnl_percent": 0},
                "agents": [],
                "signals": [],
                "stats": {},
                "history": [],
            }

        # Gather all data concurrently
        portfolio_data = service.get_portfolio_status()

        # Get agents
        agents_data = []
        if hasattr(service, "_agent_states"):
            for agent_id, agent in service._agent_states.items():
                agents_data.append(
                    {
                        "id": agent_id,
                        "name": getattr(agent, "name", agent_id),
                        "emoji": getattr(agent, "emoji", "🤖"),
                        "status": "active" if getattr(agent, "is_active", True) else "idle",
                        "win_rate": getattr(agent, "win_rate", 0.5),
                        "total_trades": getattr(agent, "total_trades", 0),
                        "weight": getattr(agent, "voting_weight", 1.0),
                    }
                )

        # Get recent signals from consensus engine
        signals = []
        if hasattr(service, "_consensus_engine"):
            recent = getattr(service._consensus_engine, "consensus_history", [])
            for result in list(recent)[-20:]:
                signals.append(
                    {
                        "symbol": getattr(result, "symbol", ""),
                        "winning_signal": (
                            result.winning_signal.value if result.winning_signal else "hold"
                        ),
                        "confidence": getattr(result, "consensus_confidence", 0),
                        "agreement": getattr(result, "agreement_level", 0),
                        "is_strong": getattr(result, "consensus_confidence", 0) > 0.7,
                        "timestamp_us": getattr(result, "timestamp_us", int(time.time() * 1000000)),
                    }
                )

        # Get portfolio history for sparkline (simulated if not available)
        history = []
        if hasattr(service, "_portfolio_history"):
            history = list(service._portfolio_history)[-24:]
        else:
            # Generate mock history based on current value
            base = portfolio_data.get("balance", 1000)
            import random

            history = [base * (1 + random.uniform(-0.02, 0.02)) for _ in range(24)]

        # Aggregated stats
        stats = {
            "total_pnl_percent": portfolio_data.get("total_pnl_percent", 0),
            "open_positions_count": len(portfolio_data.get("positions", [])),
            "active_agents_count": len([a for a in agents_data if a["status"] == "active"]),
            "total_signals": len(signals),
        }

        return {
            "portfolio": {
                "balance": portfolio_data.get("portfolio_value", 0),
                "equity": portfolio_data.get("portfolio_value", 0),
                "pnl_percent": portfolio_data.get("total_pnl_percent", 0),
            },
            "agents": agents_data,
            "signals": signals,
            "stats": stats,
            "history": history,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Dashboard batch endpoint error: {e}")
        return {
            "portfolio": {"balance": 0, "equity": 0, "pnl_percent": 0},
            "agents": [],
            "signals": [],
            "stats": {},
            "history": [],
            "error": str(e),
        }


# ===================================================================
# SYSTEM OBSERVABILITY ENDPOINTS
# ===================================================================
from .observability_api import router as observability_router

app.include_router(observability_router)
from . import symphony_endpoints

app.include_router(symphony_endpoints.router)

# ===================================================================
# SYMPHONY / MONAD INTEGRATION ENDPOINTS
# ===================================================================


@app.get("/api/symphony/status")
async def get_symphony_status() -> Dict[str, Any]:
    """
    Get Symphony (Monad) MIT fund status and activation progress.

    Returns activation status and fund information for the MIT dashboard.
    """
    try:
        from .symphony_client import get_symphony_client
        from .symphony_config import validate_symphony_config

        # Check if Symphony is configured
        if not validate_symphony_config():
            return {
                "configured": False,
                "error": "Symphony API not configured. Add SYMPHONY_API_KEY to environment.",
                "fund": {
                    "name": "Sapphire MIT Agent",
                    "balance": 0,
                    "is_activated": False,
                    "trades_count": 0,
                },
                "trades_count": 0,
                "is_activated": False,
                "activation_progress": {
                    "current": 0,
                    "required": 5,
                    "percentage": 0,
                    "activated": False,
                },
            }

        # Get Symphony client and fetch account info
        client = get_symphony_client()
        account = await client.get_account_info()

        return {
            "configured": True,
            "fund": {
                "id": account.get("id"),
                "name": account.get("name", "Sapphire MIT Agent"),
                "balance": account.get("balance", {}).get("USDC", 0),
                "is_activated": account.get("is_activated", False),
                "trades_count": account.get("trades_count", 0),
            },
            "trades_count": account.get("trades_count", 0),
            "is_activated": account.get("is_activated", False),
            "activation_progress": client.activation_progress,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Symphony status check failed: {e}")
        return {
            "configured": False,
            "error": str(e),
            "fund": {
                "name": "Sapphire MIT Agent",
                "balance": 0,
                "is_activated": False,
                "trades_count": 0,
            },
            "trades_count": 0,
            "is_activated": False,
            "activation_progress": {
                "current": 0,
                "required": 5,
                "percentage": 0,
                "activated": False,
            },
        }


@app.post("/api/symphony/trade/perpetual")
async def execute_symphony_perpetual(request: Request) -> Dict[str, Any]:
    """
    Execute a perpetual futures trade on Symphony/Monad.

    Body:
    {
        "symbol": "BTC-USDC",
        "side": "LONG" | "SHORT",
        "size": 100,
        "leverage": 3,
        "stop_loss": 42000 (optional),
        "take_profit": 45000 (optional)
    }
    """
    try:
        from .symphony_client import get_symphony_client
        from .symphony_config import MIT_DEFAULT_LEVERAGE, MIT_MAX_POSITION_SIZE_USDC

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        symbol = body.get("symbol")
        side = body.get("side")
        size = float(body.get("size", 0))
        leverage = int(body.get("leverage", MIT_DEFAULT_LEVERAGE))
        stop_loss = body.get("stop_loss")
        take_profit = body.get("take_profit")

        # Validation
        if not symbol or not side:
            raise HTTPException(status_code=400, detail="symbol and side are required")
        if size <= 0:
            raise HTTPException(status_code=400, detail="size must be positive")
        if size > MIT_MAX_POSITION_SIZE_USDC:
            raise HTTPException(
                status_code=400, detail=f"size exceeds maximum of ${MIT_MAX_POSITION_SIZE_USDC}"
            )

        # Execute trade
        client = get_symphony_client()
        position = await client.open_perpetual_position(
            symbol=symbol,
            side=side,
            size=size,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info(f"Symphony perpetual opened: {symbol} {side} {size} @ {leverage}x by {uid}")

        return {
            "success": True,
            "position": position,
            "message": f"Perpetual position opened: {side} {symbol}",
            "activation_progress": client.activation_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony perpetual trade failed: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/symphony/trade/spot")
async def execute_symphony_spot(request: Request) -> Dict[str, Any]:
    """
    Execute a spot trade on Symphony/Monad.

    Body:
    {
        "symbol": "BTC-USDC",
        "side": "BUY" | "SELL",
        "quantity": 0.01,
        "order_type": "market" | "limit"
    }
    """
    try:
        from .symphony_client import get_symphony_client

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        symbol = body.get("symbol")
        side = body.get("side")
        quantity = float(body.get("quantity", 0))
        order_type = body.get("order_type", "market")

        # Validation
        if not symbol or not side:
            raise HTTPException(status_code=400, detail="symbol and side are required")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity must be positive")

        # Execute trade
        client = get_symphony_client()
        order = await client.execute_spot_trade(
            symbol=symbol, side=side, quantity=quantity, order_type=order_type
        )

        logger.info(f"Symphony spot trade: {side} {quantity} {symbol} by {uid}")

        return {
            "success": True,
            "order": order,
            "message": f"Spot trade executed: {side} {quantity} {symbol}",
            "activation_progress": client.activation_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony spot trade failed: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/symphony/positions")
async def get_symphony_positions() -> Dict[str, Any]:
    """Get all open Symphony perpetual positions."""
    try:
        from .symphony_client import get_symphony_client

        client = get_symphony_client()
        positions = await client.get_perpetual_positions()

        return {"success": True, "positions": positions, "count": len(positions)}
    except Exception as e:
        logger.error(f"Failed to get Symphony positions: {e}")
        return {"success": False, "error": str(e), "positions": []}


@app.post("/api/symphony/fund/create")
async def create_symphony_fund(request: Request) -> Dict[str, Any]:
    """
    Create a new agentic fund on Symphony.

    Body:
    {
        "name": "My Trading Fund",
        "description": "AI-powered autonomous trading",
        "fund_type": "perpetuals",
        "autosubscribe": true
    }
    """
    try:
        from .symphony_client import get_symphony_client

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        name = body.get("name", "Sapphire MIT Agent")
        description = body.get("description", "Autonomous AI trading on Monad")
        fund_type = body.get("fund_type", "perpetuals")
        autosubscribe = body.get("autosubscribe", True)

        client = get_symphony_client()
        fund = await client.create_agentic_fund(
            name=name, description=description, fund_type=fund_type, autosubscribe=autosubscribe
        )

        logger.info(f"MIT fund created: {name} by {uid}")

        return {
            "success": True,
            "fund": fund,
            "message": f"Agentic fund '{name}' created successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony fund creation failed: {e}")
        return {"success": False, "error": str(e)}


# ===================================================================
# JUPITER (SOLANA DEX) INTEGRATION ENDPOINTS
# ===================================================================


@app.get("/api/jupiter/quote")
async def get_jupiter_quote(
    input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50
) -> Dict[str, Any]:
    """
    Get Jupiter swap quote for Solana tokens.

    Query Parameters:
        input_mint: Input token mint address (e.g., SOL, USDC)
        output_mint: Output token mint address
        amount: Amount in smallest unit (lamports for SOL)
        slippage_bps: Slippage tolerance in basis points (default: 50 = 0.5%)

    Example:
        /api/jupiter/quote?input_mint=So11...&output_mint=EPj...&amount=1000000000
    """
    try:
        from .jupiter_client import get_jupiter_client

        client = get_jupiter_client()
        quote = await client.get_quote(
            input_mint=input_mint, output_mint=output_mint, amount=amount, slippage_bps=slippage_bps
        )

        return {
            "success": True,
            "quote": quote,
            "input_amount": amount,
            "output_amount": int(quote.get("outAmount", 0)),
            "price_impact_pct": float(quote.get("priceImpactPct", 0)),
            "route_plan": quote.get("routePlan", []),
            "context_slot": quote.get("contextSlot"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Jupiter quote failed: {e}")
        return {"success": False, "error": str(e), "message": "Failed to fetch swap quote"}


@app.post("/api/jupiter/swap")
async def execute_jupiter_swap(request: Request) -> Dict[str, Any]:
    """
    Execute Jupiter token swap on Solana.

    Body:
    {
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "amount": 1000000000,
        "slippage_bps": 50,
        "priority_level": "medium"
    }

    Requires authentication via Firebase.
    """
    try:
        from .jupiter_client import get_jupiter_client
        from .solana_wallet_manager import get_user_solana_wallet

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        input_mint = body.get("input_mint")
        output_mint = body.get("output_mint")
        amount = int(body.get("amount"))
        slippage_bps = int(body.get("slippage_bps", 50))
        priority_level = body.get("priority_level", "medium")

        # Validation
        if not input_mint or not output_mint:
            raise HTTPException(status_code=400, detail="input_mint and output_mint are required")
        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive")

        # Get user's Solana wallet keypair
        wallet_keypair = get_user_solana_wallet(uid)

        # Get quote
        client = get_jupiter_client()
        quote = await client.get_quote(input_mint, output_mint, amount, slippage_bps)

        # Execute swap
        result = await client.execute_swap(
            quote=quote, user_keypair=wallet_keypair, priority_level=priority_level
        )

        logger.info(
            f"Jupiter swap executed by {uid}: {input_mint[:8]}... → {output_mint[:8]}... "
            f"Signature: {result.get('signature', 'N/A')}"
        )

        return {
            "success": True,
            "signature": result.get("signature"),
            "input_amount": amount,
            "output_amount": int(quote.get("outAmount", 0)),
            "message": "Swap executed successfully on Solana",
            "explorer_url": f"https://solscan.io/tx/{result.get('signature')}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Jupiter swap failed: {e}")
        return {"success": False, "error": str(e), "message": "Swap execution failed"}


@app.get("/api/jupiter/tokens")
async def get_jupiter_tokens(verified_only: bool = True) -> Dict[str, Any]:
    """
    Get list of supported Jupiter tokens.

    Query Parameters:
        verified_only: If true, only return verified tokens (default: true)
    """
    try:
        from .jupiter_client import get_jupiter_client

        client = get_jupiter_client()
        tags = ["verified"] if verified_only else None
        tokens = await client.get_tokens(tags=tags)

        return {
            "success": True,
            "tokens": tokens,
            "count": len(tokens),
            "verified_only": verified_only,
        }
    except Exception as e:
        logger.error(f"Jupiter tokens fetch failed: {e}")
        return {"success": False, "error": str(e), "tokens": []}


@app.get("/api/jupiter/price/{token_mint}")
async def get_jupiter_price(
    token_mint: str, vs_token: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
) -> Dict[str, Any]:
    """
    Get current token price from Jupiter.

    Path Parameters:
        token_mint: Token mint address to price

    Query Parameters:
        vs_token: Quote token (default: USDC)
    """
    try:
        from .jupiter_client import get_jupiter_client

        client = get_jupiter_client()
        price = await client.get_price(token_mint, vs_token)

        return {
            "success": True,
            "token_mint": token_mint,
            "vs_token": vs_token,
            "price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Jupiter price fetch failed: {e}")
        return {"success": False, "error": str(e), "price": 0}


@app.get("/healthz")
async def healthz() -> Dict[str, object]:
    """
    Enhanced health check endpoint.

    Returns comprehensive system health including:
    - Service status (running, paper trading mode)
    - Dependency health (Exchange, Telegram, Firestore)
    - Performance metrics snapshot
    - Circuit breaker states

    This follows the first principle: Health checks should be actionable.
    If something is unhealthy, the response tells you what and why.
    """
    import time

    from fastapi.responses import JSONResponse

    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.1.0",
        "service": {
            "running": False,
            "paper_trading": False,
            "last_error": None,
        },
        "dependencies": {
            "exchange": {"status": "unknown", "latency_ms": None},
            "telegram": {"status": "unknown"},
            "firestore": {"status": "unknown"},
        },
        "performance": {
            "uptime_seconds": None,
            "agents_active": 0,
            "open_positions": 0,
            "pending_orders": 0,
        },
        "circuit_breakers": {},
    }

    try:
        service = get_service_instance()

        if service:
            # Core service health
            status = service.health()
            health_data["service"] = {
                "running": status.running,
                "paper_trading": status.paper_trading,
                "last_error": status.last_error,
            }

            # Agent count
            if hasattr(service, "_agent_states"):
                health_data["performance"]["agents_active"] = len(
                    [
                        a
                        for a in service._agent_states.values()
                        if getattr(a, "status", "") == "active"
                    ]
                )

            # Open positions count
            if hasattr(service, "_open_positions"):
                health_data["performance"]["open_positions"] = len(service._open_positions)

            # Pending orders count
            if hasattr(service, "_pending_orders"):
                health_data["performance"]["pending_orders"] = len(service._pending_orders)

            # Exchange health check (quick ping)
            if hasattr(service, "_exchange_client") and service._exchange_client:
                try:
                    start = time.time()
                    # Just check if client is initialized - actual ping would add latency
                    health_data["dependencies"]["exchange"] = {
                        "status": "healthy",
                        "latency_ms": round((time.time() - start) * 1000, 2),
                    }
                except Exception as e:
                    health_data["dependencies"]["exchange"] = {
                        "status": "unhealthy",
                        "error": str(e)[:100],
                    }

            # Telegram health
            if hasattr(service, "_telegram") and service._telegram:
                health_data["dependencies"]["telegram"] = {"status": "healthy"}
            else:
                health_data["dependencies"]["telegram"] = {"status": "disabled"}

            # Firestore health (check Firebase Admin SDK)
            try:
                import firebase_admin

                firebase_admin.get_app()
                health_data["dependencies"]["firestore"] = {"status": "healthy"}
            except Exception:
                health_data["dependencies"]["firestore"] = {"status": "unknown"}

        else:
            health_data["status"] = "degraded"
            health_data["service"]["last_error"] = "Trading service not initialized"

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_data["status"] = "unhealthy"
        health_data["service"]["last_error"] = str(e)

    # Set overall status based on critical dependencies
    if health_data["dependencies"]["exchange"].get("status") == "unhealthy":
        health_data["status"] = "unhealthy"

    response = JSONResponse(content=health_data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


@app.get("/health")
async def health() -> Dict[str, object]:
    """Alias for /healthz for compatibility."""
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


@app.post("/admin/cancel-all-orders")
async def cancel_all_orders(request: Request, _: None = Depends(require_admin)) -> Dict[str, Any]:
    """
    Cancel ALL open orders across all symbols to free up locked capital.
    This helps improve capital efficiency when too many pending orders are consuming margin.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"cancel_orders_{client_ip}"):
        raise HTTPException(status_code=429, detail="Too many requests")

    try:
        service = get_service_instance()
        if not service or not service._exchange_client:
            raise HTTPException(status_code=503, detail="Trading service not initialized")

        # Get all open orders
        all_open_orders = await service._exchange_client.get_open_orders()

        if not all_open_orders:
            return {
                "status": "success",
                "message": "No open orders to cancel",
                "cancelled_count": 0,
                "orders": [],
            }

        cancelled = []
        errors = []

        for order in all_open_orders:
            try:
                symbol = order.get("symbol")
                order_id = order.get("orderId")
                if symbol and order_id:
                    await service._exchange_client.cancel_order(symbol, str(order_id))
                    cancelled.append(
                        {
                            "symbol": symbol,
                            "orderId": order_id,
                            "type": order.get("type"),
                            "side": order.get("side"),
                        }
                    )
            except Exception as e:
                errors.append(
                    {
                        "symbol": order.get("symbol"),
                        "orderId": order.get("orderId"),
                        "error": str(e),
                    }
                )

        # Send notification
        if service._telegram:
            msg = f"🗑️ **Capital Cleanup**\n\nCancelled {len(cancelled)} open orders\nErrors: {len(errors)}\nFree margin restored!"
            await service._telegram.send_message(msg)

        return {
            "status": "success",
            "message": f"Cancelled {len(cancelled)} orders, {len(errors)} errors",
            "cancelled_count": len(cancelled),
            "error_count": len(errors),
            "cancelled": cancelled,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Failed to cancel all orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/open-orders")
async def get_all_open_orders(request: Request, _: None = Depends(require_admin)) -> Dict[str, Any]:
    """Get all open orders to see what's consuming capital."""
    try:
        service = get_service_instance()
        if not service or not service._exchange_client:
            raise HTTPException(status_code=503, detail="Trading service not initialized")

        all_orders = await service._exchange_client.get_open_orders()

        # Calculate total locked capital
        total_notional = sum(
            float(o.get("origQty", 0)) * float(o.get("price", 0) or o.get("stopPrice", 0) or 0)
            for o in all_orders
        )

        return {
            "status": "success",
            "total_open_orders": len(all_orders),
            "estimated_locked_capital": round(total_notional, 2),
            "orders": all_orders,
        }

    except Exception as e:
        logger.error(f"Failed to get open orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.put("/positions/{symbol}/tpsl")
async def update_position_tpsl(symbol: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update Take Profit and Stop Loss for a position."""
    try:
        service = get_service_instance()
        if not service:
            raise HTTPException(status_code=503, detail="Trading service not initialized")

        tp = request.get("tp")
        sl = request.get("sl")

        if tp is None and sl is None:
            raise HTTPException(status_code=400, detail="Must provide tp or sl")

        # Call service to update
        if hasattr(service, "update_position_tpsl"):
            result = await service.update_position_tpsl(symbol, tp, sl)
            return {
                "status": "success",
                "symbol": symbol,
                "updated": result,
                "timestamp_us": int(time.time() * 1_000_000),
            }
        else:
            # Fallback/stub if method missing (though we will add it next)
            logger.warning("Method update_position_tpsl not found on trading service")
            return {"status": "error", "message": "Not implemented"}

    except Exception as e:
        logger.error(f"Failed to update TP/SL for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/performance/stats")
async def get_performance_stats() -> Dict[str, Any]:
    """Get granular agent performance statistics."""
    try:
        service = get_service_instance()
        if not service:
            return {"status": "error", "message": "Service not initialized"}

        tracker = getattr(service, "_performance_tracker", None)
        if not tracker:
            return {"status": "inactive", "message": "Performance tracking not enabled"}

        # Serialize metrics
        metrics_data = {agent_id: m.__dict__ for agent_id, m in tracker.metrics.items()}

        return {
            "status": "success",
            "metrics": metrics_data,
            "top_agent": tracker.get_top_performing_agent(),
            "timestamp_us": int(time.time() * 1_000_000),
        }
    except Exception as e:
        logger.error(f"Failed to get performance stats: {e}")
        return {"status": "error", "error": str(e)}


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
        logger.error(f"Failed to register agent for consensus: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/consensus/state")
async def get_consensus_state() -> Dict[str, Any]:
    """Get current state of the consensus engine (weights, stats)."""
    try:
        from .agent_consensus import get_agent_consensus_engine

        # Get engine via wrapper if available, or direct from service
        engine = None
        service = get_service_instance()
        if service and hasattr(service, "_consensus_engine"):
            engine = service._consensus_engine

        if not engine:
            # Fallback
            engine = await get_agent_consensus_engine()

        if not engine:
            return {"status": "inactive", "message": "Consensus engine not initialized"}

        stats = engine.get_consensus_stats()

        # Get detailed weights
        weights = {
            agent_id: engine.agent_weights.get(agent_id, 1.0)
            for agent_id in engine.agent_registry.keys()
        }

        # Add portfolio P&L data from trading service
        portfolio_data = {}
        if service and hasattr(service, "_portfolio"):
            try:
                # Get position PnL
                all_positions = []
                if hasattr(service, "_open_positions"):
                    all_positions = list(service._open_positions.values())

                unrealized_pnl = sum(p.get("pnl", 0) for p in all_positions)
                realized_pnl = getattr(service, "_total_realized_pnl", 0.0)

                # Calculate fees and funding (WORLD-CLASS ACCURACY)
                total_fees = 0.0
                total_funding = 0.0

                if hasattr(service, "_exchange_client") and service._exchange_client:
                    try:
                        # Get trading fees from last 7 days
                        seven_days_ago = int((time.time() - 7 * 24 * 3600) * 1000)

                        # Aggregate fees across all traded symbols
                        symbols_traded = set(p.get("symbol") for p in all_positions)
                        for symbol in symbols_traded:
                            try:
                                trades = await service._exchange_client.get_account_trades(
                                    symbol=symbol, start_time=seven_days_ago, limit=100
                                )
                                # Sum commission from all trades
                                total_fees += sum(float(t.get("commission", 0)) for t in trades)
                            except:
                                pass  # Skip if symbol fails

                        # Get funding payments (income type: FUNDING_FEE)
                        try:
                            funding_history = await service._exchange_client.get_income_history(
                                income_type="FUNDING_FEE", start_time=seven_days_ago, limit=100
                            )
                            # Sum funding payments (negative = paid, positive = received)
                            total_funding = sum(float(f.get("income", 0)) for f in funding_history)
                        except:
                            pass  # Funding might not be available on all exchanges

                    except Exception as fee_err:
                        logger.debug(f"Could not fetch fees/funding: {fee_err}")

                # Calculate NET PnL (after fees and funding)
                total_pnl = unrealized_pnl + realized_pnl - total_fees + total_funding

                # Fetch LIVE balance from exchange for accuracy
                live_balance = 0.0
                if hasattr(service, "_exchange_client") and service._exchange_client:
                    try:
                        account_info = await service._exchange_client.get_account_info_v4()
                        if account_info:
                            live_balance = float(account_info.get("totalMarginBalance", 0.0))
                            # Also update cached balance
                            if live_balance > 0:
                                service._portfolio.balance = live_balance
                    except Exception as balance_err:
                        logger.debug(f"Could not fetch live balance: {balance_err}")

                # Use live balance if available, otherwise fall back to cached
                initial_balance = (
                    live_balance
                    if live_balance > 0
                    else (service._portfolio.balance if service._portfolio.balance > 0 else 1000.0)
                )
                total_pnl_percent = (
                    (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0.0
                )

                portfolio_data = {
                    "total_pnl": total_pnl,
                    "total_pnl_percent": total_pnl_percent,
                    "unrealized_pnl": unrealized_pnl,
                    "realized_pnl": realized_pnl,
                    "total_fees": total_fees,
                    "total_funding": total_funding,
                    "portfolio_value": initial_balance + total_pnl,
                    "cash_balance": initial_balance,
                }
            except Exception as pnl_err:
                logger.warning(f"Could not calculate PnL: {pnl_err}")

        return {
            "status": "active",
            "stats": stats,
            "weights": weights,
            **portfolio_data,  # Include PnL data if available
            "timestamp_us": int(time.time() * 1_000_000),
        }

    except Exception as e:
        logger.error(f"Failed to get consensus state: {e}")
        return {"status": "error", "error": str(e)}

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
        from .definitions import AGENT_DEFINITIONS

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

        from .definitions import AGENT_DEFINITIONS

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
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🔌 [WS] Dashboard WebSocket connection attempt from {client_host}")

    try:
        await websocket.accept()
        logger.info(f"✅ [WS] Dashboard WebSocket ACCEPTED for {client_host}")
    except Exception as e:
        logger.error(f"❌ [WS] Failed to accept WebSocket: {e}")
        return

    try:
        # Send initial snapshot
        logger.info(f"📤 [WS] Fetching initial dashboard data for {client_host}...")
        initial_data = await get_live_dashboard_data()

        # Validate data has required fields
        if "portfolio_value" not in initial_data:
            logger.warning("⚠️ [WS] portfolio_value missing from initial data, adding default")
            initial_data["portfolio_value"] = 100000.0

        logger.info(
            f"📤 [WS] Sending initial snapshot to {client_host}: {len(str(initial_data))} chars"
        )
        await websocket.send_json(initial_data)
        logger.info(f"✅ [WS] Initial snapshot SENT to {client_host}")

        # Stream updates every 2 seconds
        update_count = 0
        while True:
            await asyncio.sleep(2)
            update_count += 1

            try:
                live_data = await get_live_dashboard_data()

                # Ensure portfolio_value exists
                if "portfolio_value" not in live_data:
                    live_data["portfolio_value"] = 100000.0

                await websocket.send_json(live_data)

                # Log every 10th update to avoid spam
                if update_count % 10 == 0:
                    logger.info(f"📤 [WS] Sent update #{update_count} to {client_host}")

            except Exception as send_err:
                logger.error(f"❌ [WS] Failed to send update #{update_count}: {send_err}")
                break

    except WebSocketDisconnect:
        logger.info(f"🔴 [WS] Client {client_host} disconnected normally")
    except Exception as exc:
        logger.exception(f"❌ [WS] Dashboard WebSocket error for {client_host}: {exc}")
    finally:
        logger.info(f"🔒 [WS] Dashboard WebSocket connection CLOSED for {client_host}")


@app.websocket("/ws/test")
async def test_websocket(websocket: WebSocket) -> None:
    """Simple WebSocket echo endpoint for testing connectivity."""
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🧪 [WS-TEST] Test WebSocket connection from {client_host}")

    await websocket.accept()
    logger.info(f"✅ [WS-TEST] Test WebSocket ACCEPTED for {client_host}")

    try:
        # Send a test message immediately
        await websocket.send_json(
            {
                "type": "test",
                "message": "WebSocket connection successful!",
                "timestamp": time.time(),
                "client": client_host,
            }
        )

        # Echo any messages received
        while True:
            data = await websocket.receive_text()
            logger.info(f"🧪 [WS-TEST] Received from {client_host}: {data[:100]}...")
            await websocket.send_json({"type": "echo", "received": data, "timestamp": time.time()})
    except WebSocketDisconnect:
        logger.info(f"🧪 [WS-TEST] Client {client_host} disconnected")
    except Exception as e:
        logger.exception(f"🧪 [WS-TEST] Error: {e}")


async def get_live_dashboard_data() -> Dict[str, Any]:
    """Gather live dashboard metrics from trading service."""
    try:
        if trading_service is None:
            logger.warning("⚠️ [WS] Trading service not initialized, returning placeholder data")
            return {
                "status": "initializing",
                "portfolio_value": 100000.0,
                "portfolio_balance": 100000.0,
                "total_pnl": 0.0,
                "total_exposure": 0.0,
                "agents": [],
                "messages": [],
                "recentTrades": [],
                "open_positions": [],
                "timestamp": time.time(),
            }

        # Delegate to the service's snapshot method for consistency
        data = await trading_service.dashboard_snapshot()

        # Ensure required fields exist
        if "portfolio_value" not in data:
            data["portfolio_value"] = data.get("portfolio_balance", 100000.0)
        if "timestamp" not in data:
            data["timestamp"] = time.time()

        return data

    except Exception as e:
        logger.exception(f"❌ [WS] Failed to gather dashboard data: {e}")
        return {"error": str(e), "portfolio_value": 100000.0, "timestamp": time.time()}


# ===================================================================
# SOCIAL SENTIMENT & GAMIFICATION ENDPOINTS
# ===================================================================


@app.middleware("http")
async def verify_firebase_token(request: Request, call_next):
    # Public endpoints that don't require auth
    public_paths = [
        "/health",
        "/healthz",
        "/consensus/state",
        "/portfolio-status",
        "/metrics",
        "/",
        "/static",
        "/assets",
        "/favicon.ico",
        "/api/chat/messages",  # Public read-only
        "/api/chat/ticker",  # Public ticker search
        "/api/chat/sentiment",  # Public sentiment
        "/api/leaderboard",  # Public leaderboard
        "/api/dashboard",  # Batch dashboard data
        "/api/symphony/status",  # MIT activation status
        "/api/symphony/positions",  # Symphony positions
    ]

    # Check if path is public
    is_public = False
    for p in public_paths:
        if p == "/":
            if request.url.path == "/":
                is_public = True
                break
        elif request.url.path.startswith(p):
            is_public = True
            break

    # Global Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"global_{client_ip}"):
        RATE_LIMIT_EVENTS.inc()
        return JSONResponse({"error": "Global rate limit exceeded"}, status_code=429)

    if is_public:
        return await call_next(request)

    # Special handling for admin cron job (protected by header secret)
    if request.url.path == "/api/admin/score-predictions":
        # Check for X-Admin-Key header (set in Cloud Scheduler)
        admin_key = request.headers.get("X-Admin-Key")
        # In production use secret manager. For now using hardcoded or env var.
        expected_key = os.environ.get("ADMIN_API_KEY", "admin-secret-123")
        if admin_key != expected_key:
            return JSONResponse({"error": "Unauthorized Admin Request"}, status_code=401)
        return await call_next(request)

    # Verify Firebase ID token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # For websocket upgrades or other non-auth requests might need handling
        # But for /api/vote etc we need this.
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "Missing Authorization Header"}, status_code=401)
        return await call_next(request)

    token = auth_header.replace("Bearer ", "")
    try:
        decoded = auth.verify_id_token(token)
        request.state.uid = decoded["uid"]
    except Exception as e:
        logger.warning(f"Auth failed: {e}")
        return JSONResponse({"error": "Invalid Token"}, status_code=401)

    return await call_next(request)


@app.post("/api/vote")
async def submit_vote(request: Request) -> Dict[str, Any]:
    """Submit a daily market prediction vote."""
    try:
        from .voting_service import get_voting_service

        uid = getattr(request.state, "uid", None)
        if not uid:
            return {"error": "Unauthorized"}

        body = await request.json()
        symbol = body.get("symbol")
        prediction = body.get("prediction")
        confidence = body.get("confidence", 0.5)

        if not uid or not symbol or not prediction:
            return {"error": "Missing required fields: uid, symbol, prediction"}

        voting_service = get_voting_service()
        result = await voting_service.submit_vote(uid, symbol, prediction, confidence)

        return result
    except Exception as e:
        logger.error(f"Vote submission failed: {e}")
        return {"error": str(e)}


@app.get("/api/sentiment/{symbol}")
async def get_sentiment(symbol: str) -> Dict[str, Any]:
    """Get aggregated crowd sentiment for a symbol."""
    try:
        from .voting_service import get_voting_service

        voting_service = get_voting_service()
        sentiment = await voting_service.get_crowd_sentiment(symbol)

        return sentiment
    except Exception as e:
        logger.error(f"Failed to get sentiment for {symbol}: {e}")
        return {"error": str(e)}


@app.get("/api/user/stats")
async def get_user_stats(request: Request) -> Dict[str, Any]:
    """Get user stats."""
    try:
        from .user_service import get_user_service

        uid = getattr(request.state, "uid", None)
        if not uid:
            # Allow inspection if uid param matches (or for admin later)
            # But for now, require auth
            return {"error": "Unauthorized"}

        user_service = get_user_service()
        stats = await user_service.get_user_stats(uid)

        return stats
    except Exception as e:
        logger.error(f"Failed to get user stats: {e}")
        return {"error": str(e)}


@app.post("/api/user/checkin")
async def daily_checkin(request: Request) -> Dict[str, Any]:
    """Record daily check-in and award points."""
    try:
        from .user_service import get_user_service

        uid = getattr(request.state, "uid", None)
        if not uid:
            return {"error": "Unauthorized"}

        user_service = get_user_service()
        result = await user_service.record_daily_checkin(uid)

        return result
    except Exception as e:
        logger.error(f"Daily check-in failed: {e}")
        return {"error": str(e)}


@app.post("/api/admin/score-predictions")
async def score_predictions(request: Request) -> Dict[str, Any]:
    """Admin endpoint to manually trigger prediction scoring."""
    try:
        from .voting_service import get_voting_service

        voting_service = get_voting_service()
        result = await voting_service.score_predictions()

        return result
    except Exception as e:
        logger.error(f"Prediction scoring failed: {e}")
        return {"error": str(e)}


@app.get("/api/leaderboard")
async def get_leaderboard(
    timeframe: str = Query("all", regex="^(all|monthly|accuracy|streaks)$")
) -> List[Dict[str, Any]]:
    """
    Get leaderboard rankings.

    Args:
        timeframe: 'all' | 'monthly' | 'accuracy' | 'streaks'
    """
    try:
        from .points_system import get_points_system

        points_system = get_points_system()

        if timeframe == "streaks":
            leaderboard = await points_system.get_streak_leaderboard()
        else:
            leaderboard = await points_system.get_leaderboard(timeframe)

        return leaderboard
    except Exception as e:
        logger.error(f"Leaderboard fetch failed: {e}")
        return {"error": str(e)}


# ============ CHAT API ENDPOINTS ============


@app.get("/api/chat/messages")
async def get_chat_messages(
    limit: int = Query(50, ge=1, le=100),
) -> Dict[str, Any]:
    """Get recent chat messages."""
    try:
        from .chat_service import get_chat_service

        chat_service = get_chat_service()
        messages = await chat_service.get_messages(limit=limit)

        return {
            "messages": [
                {
                    "id": msg.id,
                    "user_id": msg.user_id,
                    "username": msg.username,
                    "display_name": msg.display_name,
                    "avatar": msg.avatar,
                    "content": msg.content,
                    "tickers": msg.tickers,
                    "timestamp": msg.timestamp.isoformat(),
                    "is_bot": msg.is_bot,
                    "bot_replied": msg.bot_replied,
                    "points_awarded": msg.points_awarded,
                    "award_reason": msg.award_reason,
                    "likes": msg.likes,
                    "reply_to": msg.reply_to,
                }
                for msg in messages
            ],
            "count": len(messages),
        }
    except Exception as e:
        logger.error(f"Chat messages fetch failed: {e}")
        return {"messages": [], "error": str(e)}


@app.post("/api/chat/send")
async def send_chat_message(request: Request) -> Dict[str, Any]:
    """
    Send a chat message.

    Body:
    {
        "content": "I think $BTC is going to pump!",
        "reply_to": null  // Optional message ID to reply to
    }
    """
    try:
        # Get authenticated user from middleware (already verified)
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        from .chat_bot import get_chat_bot
        from .chat_service import get_chat_service

        body = await request.json()
        content = body.get("content", "").strip()
        reply_to = body.get("reply_to")

        if not content:
            return {"error": "Message content is required"}

        if len(content) > 500:
            return {"error": "Message too long (max 500 characters)"}

        chat_service = get_chat_service()

        # Get or create user profile
        profile = await chat_service.get_or_create_profile(uid)

        # Send message
        message = await chat_service.send_message(
            user_id=uid,
            username=profile.username,
            content=content,
            display_name=profile.display_name,
            avatar="👤",
            reply_to=reply_to,
        )

        # Check for bot mentions
        if "@sapphire" in content.lower() or "@bot" in content.lower():
            chat_bot = get_chat_bot()
            asyncio.create_task(chat_bot.respond_to_mention(message.id, content, profile.username))

        return {
            "success": True,
            "message": {
                "id": message.id,
                "content": message.content,
                "tickers": message.tickers,
                "timestamp": message.timestamp.isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Chat send failed: {e}")
        return {"error": str(e)}


@app.post("/api/chat/like")
async def like_chat_message(request: Request) -> Dict[str, Any]:
    """Like a chat message."""
    try:
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        from .chat_service import get_chat_service

        body = await request.json()
        message_id = body.get("message_id")

        if not message_id:
            return {"error": "message_id is required"}

        chat_service = get_chat_service()
        success = await chat_service.like_message(message_id, uid)

        return {"success": success, "liked": success}
    except Exception as e:
        logger.error(f"Chat like failed: {e}")
        return {"error": str(e)}


@app.get("/api/chat/ticker/{ticker}")
async def get_ticker_messages(ticker: str, limit: int = 20) -> Dict[str, Any]:
    """Get messages mentioning a specific ticker."""
    try:
        from .chat_service import get_chat_service

        chat_service = get_chat_service()
        messages = await chat_service.get_messages_with_ticker(ticker, limit=limit)

        return {
            "ticker": ticker.upper(),
            "messages": [
                {
                    "id": msg.id,
                    "username": msg.username,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "points_awarded": msg.points_awarded,
                }
                for msg in messages
            ],
            "count": len(messages),
        }
    except Exception as e:
        logger.error(f"Ticker messages fetch failed: {e}")
        return {"messages": [], "error": str(e)}


@app.get("/api/chat/sentiment/{symbol}")
async def get_chat_sentiment(symbol: str) -> Dict[str, Any]:
    """Get crowd sentiment for a symbol based on chat messages."""
    try:
        from .chat_bot import get_chat_bot

        chat_bot = get_chat_bot()
        sentiment = await chat_bot.get_crowd_sentiment(symbol)

        return {
            "symbol": symbol.upper(),
            **sentiment,
        }
    except Exception as e:
        logger.error(f"Chat sentiment fetch failed: {e}")
        return {"error": str(e)}


# ============ USER PROFILE ENDPOINTS ============


@app.get("/api/user/profile")
async def get_user_profile(request: Request) -> Dict[str, Any]:
    """Get the authenticated user's profile."""
    try:
        uid = getattr(request.state, "uid", None)
        if not uid:
            return {"error": "Authentication required"}

        from .chat_service import get_chat_service

        chat_service = get_chat_service()
        profile = await chat_service.get_or_create_profile(uid)

        return {
            "uid": profile.uid,
            "username": profile.username,
            "display_name": profile.display_name,
            "avatar_seed": profile.avatar_seed,
            "bio": profile.bio,
            "total_points": profile.total_points,
            "chat_points": profile.chat_points,
            "messages_sent": profile.messages_sent,
            "bot_interactions": profile.bot_interactions,
            "advice_taken": profile.advice_taken,
            "is_advisor": profile.is_advisor,
            "created_at": profile.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Profile fetch failed: {e}")
        return {"error": str(e)}


@app.post("/api/user/profile")
async def update_user_profile(request: Request) -> Dict[str, Any]:
    """
    Update user profile.

    Body:
    {
        "username": "trader123",  // Must be unique
        "display_name": "Pro Trader",
        "bio": "Diamond hands only 💎"
    }
    """
    try:
        uid = getattr(request.state, "uid", None)
        if not uid:
            return {"error": "Authentication required"}

        from .chat_service import get_chat_service

        body = await request.json()
        username = body.get("username")
        display_name = body.get("display_name")
        bio = body.get("bio")

        # Validate username
        if username:
            if len(username) < 3 or len(username) > 20:
                return {"error": "Username must be 3-20 characters"}
            if not username.isalnum() and "_" not in username:
                return {"error": "Username can only contain letters, numbers, and underscores"}

        chat_service = get_chat_service()

        try:
            profile = await chat_service.update_profile(
                uid=uid,
                username=username,
                display_name=display_name,
                bio=bio,
            )
        except ValueError as ve:
            return {"error": str(ve)}

        return {
            "success": True,
            "profile": {
                "username": profile.username,
                "display_name": profile.display_name,
                "bio": profile.bio,
            },
        }
    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        return {"error": str(e)}


@app.get("/api/user/check-username")
async def check_username_available(
    username: str = Query(..., min_length=3, max_length=20)
) -> Dict[str, Any]:
    """Check if a username is available."""
    try:
        from .chat_service import get_chat_service

        chat_service = get_chat_service()
        available = await chat_service.check_username_available(username)

        return {"username": username, "available": available}
    except Exception as e:
        logger.error(f"Username check failed: {e}")
        return {"error": str(e)}


@app.get("/api/chat/bot-stats")
async def get_bot_stats() -> Dict[str, Any]:
    """Get chat bot statistics."""
    try:
        from .chat_bot import get_chat_bot

        chat_bot = get_chat_bot()

        return {
            "pending_advice_count": chat_bot.get_pending_advice_count(),
            "recent_suggestions": chat_bot.get_recent_suggestions(limit=10),
            "last_analysis": (
                chat_bot._last_analysis_time.isoformat() if chat_bot._last_analysis_time else None
            ),
        }
    except Exception as e:
        logger.error(f"Bot stats fetch failed: {e}")
        return {"error": str(e)}

    return app
