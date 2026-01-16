"""
Sapphire V2 Integration Module - Multi-Platform Edition
========================================================
Integrates all V2 components including reinstated Hyperliquid.

Platforms:
- Hyperliquid: ACTIVE ✅ (DeFi Perps)
- Drift: ACTIVE ✅ (Solana Perps)  
- Aster: ACTIVE ✅ (CEX)
- Symphony: ACTIVE ✅ (Monad Treasury)

Author: Sapphire V2 Architecture Team
Version: 2.2.0
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import V2 modules
from .symphony_agent_manager import (
    AgentType,
    SymphonyAgentManager,
    create_symphony_manager,
)
from .hardened_memory_manager import (
    HardenedMemoryManager,
    MemoryType,
    create_memory_manager,
)
from .enhanced_circuit_breaker import (
    Platform,
    PlatformCircuitManager,
    configure_circuit_manager,
)
from .dual_platform_router import (
    DualPlatformRouter,
    RoutingConfig,
    RoutingStrategy,
    create_dual_router,
)
from .hyperliquid_client import (
    HyperliquidClient,
    HyperliquidConfig,
    create_hyperliquid_client,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class TradeRequest(BaseModel):
    """Trade execution request."""
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    order_type: str = "MARKET"
    price: Optional[float] = None
    platform: Optional[str] = None  # hyperliquid, drift, or auto
    reduce_only: bool = False


class MITActivationRequest(BaseModel):
    """MIT activation trade request."""
    symbol: str = "BTC-USDC"
    side: str = "BUY"
    quantity: float = 0.001


class MemoryStoreRequest(BaseModel):
    """Memory storage request."""
    content: str
    memory_type: str = "market_pattern"
    metadata: Optional[dict] = None


class MemoryRecallRequest(BaseModel):
    """Memory recall request."""
    query: str
    top_k: int = 5


# ============================================================================
# Application State
# ============================================================================

@dataclass
class SapphireV2State:
    """Centralized application state."""
    # Platform clients
    hyperliquid_client: Optional[HyperliquidClient] = None
    drift_client: Optional[Any] = None
    aster_client: Optional[Any] = None
    symphony_client: Optional[Any] = None
    
    # Core managers
    dual_router: Optional[DualPlatformRouter] = None
    symphony_manager: Optional[SymphonyAgentManager] = None
    memory_manager: Optional[HardenedMemoryManager] = None
    circuit_manager: Optional[PlatformCircuitManager] = None
    
    # State
    initialized: bool = False
    startup_time: Optional[datetime] = None
    
    def __post_init__(self):
        self._background_tasks = []


_app_state: Optional[SapphireV2State] = None


def get_app_state() -> SapphireV2State:
    global _app_state
    if _app_state is None:
        _app_state = SapphireV2State()
    return _app_state


# ============================================================================
# Initialization
# ============================================================================

async def initialize_v2_components(
    # Credentials from Secret Manager
    hyperliquid_private_key: Optional[str] = None,
    hyperliquid_wallet: Optional[str] = None,
    drift_private_key: Optional[str] = None,
    # Existing clients (optional)
    drift_client: Optional[Any] = None,
    aster_client: Optional[Any] = None,
    symphony_client: Optional[Any] = None,
    firestore_client: Optional[Any] = None,
    # Configuration
    hyperliquid_testnet: bool = False,
) -> SapphireV2State:
    """
    Initialize all V2 components including Hyperliquid.
    
    Args:
        hyperliquid_private_key: Hyperliquid wallet private key
        hyperliquid_wallet: Hyperliquid wallet address
        drift_private_key: Drift/Solana private key
        drift_client: Existing Drift client
        aster_client: Existing Aster client
        symphony_client: Existing Symphony client
        firestore_client: Firestore client for persistence
        hyperliquid_testnet: Use Hyperliquid testnet
        
    Returns:
        Initialized application state
    """
    state = get_app_state()
    
    if state.initialized:
        logger.warning("⚠️ V2 components already initialized")
        return state
    
    logger.info("🚀 [V2] Initializing Sapphire V2 (Multi-Platform Edition)...")
    state.startup_time = datetime.utcnow()
    
    # 1. Initialize Circuit Manager
    logger.info("  🔧 Initializing Circuit Manager...")
    state.circuit_manager = configure_circuit_manager()
    logger.info("  ✅ Circuit Manager ready (4 platforms)")
    
    # 2. Initialize Hyperliquid Client
    if hyperliquid_private_key and hyperliquid_wallet:
        logger.info("  🔷 Initializing Hyperliquid Client...")
        try:
            state.hyperliquid_client = await create_hyperliquid_client(
                private_key=hyperliquid_private_key,
                wallet_address=hyperliquid_wallet,
                testnet=hyperliquid_testnet,
            )
            logger.info("  ✅ Hyperliquid Client ready")
        except Exception as e:
            logger.error(f"  ❌ Hyperliquid Client failed: {e}")
    else:
        logger.warning("  ⚠️ Hyperliquid credentials not provided - client disabled")
    
    # 3. Store existing clients
    state.drift_client = drift_client
    state.aster_client = aster_client
    state.symphony_client = symphony_client
    
    # 4. Initialize Dual Platform Router
    if state.hyperliquid_client or state.drift_client:
        logger.info("  🔀 Initializing Dual Platform Router...")
        try:
            state.dual_router = await create_dual_router(
                hyperliquid_client=state.hyperliquid_client,
                drift_client=state.drift_client,
            )
            logger.info("  ✅ Dual Router ready")
        except Exception as e:
            logger.error(f"  ❌ Dual Router failed: {e}")
    
    # 5. Initialize Symphony Agent Manager
    logger.info("  🎭 Initializing Symphony Agent Manager...")
    try:
        state.symphony_manager = await create_symphony_manager(
            firestore_client=firestore_client,
            symphony_client=symphony_client,
        )
        logger.info("  ✅ Symphony Manager ready ($MILF, $AGDG active, $MIT pending)")
    except Exception as e:
        logger.error(f"  ❌ Symphony Manager failed: {e}")
    
    # 6. Initialize Memory Manager
    logger.info("  🧠 Initializing Memory Manager...")
    try:
        state.memory_manager = await create_memory_manager(
            firestore_client=firestore_client,
        )
        logger.info("  ✅ Memory Manager ready")
    except Exception as e:
        logger.error(f"  ❌ Memory Manager failed: {e}")
    
    state.initialized = True
    
    # Summary
    logger.info(
        f"\n{'='*60}\n"
        f"🎉 SAPPHIRE V2 INITIALIZATION COMPLETE\n"
        f"{'='*60}\n"
        f"  Hyperliquid: {'✅ ACTIVE' if state.hyperliquid_client else '❌ Disabled'}\n"
        f"  Drift: {'✅ ACTIVE' if state.drift_client else '❌ Disabled'}\n"
        f"  Dual Router: {'✅ Ready' if state.dual_router else '❌ Disabled'}\n"
        f"  Symphony: {'✅ Ready' if state.symphony_manager else '❌ Disabled'}\n"
        f"  Memory: {'✅ Ready' if state.memory_manager else '❌ Disabled'}\n"
        f"{'='*60}\n"
    )
    
    # Log MIT status
    if state.symphony_manager:
        mit = state.symphony_manager.get_mit_agent()
        logger.info(
            f"🎯 MIT STATUS: {mit.status.value} | "
            f"Progress: {mit.activation_progress}/5 | "
            f"Remaining: {mit.trades_until_activation} trades"
        )
    
    return state


async def shutdown_v2_components() -> None:
    """Gracefully shutdown V2 components."""
    state = get_app_state()
    
    logger.info("🛑 [V2] Shutting down...")
    
    if state.hyperliquid_client:
        await state.hyperliquid_client.close()
    
    if state.memory_manager:
        await state.memory_manager.shutdown()
    
    logger.info("✅ [V2] Shutdown complete")


@asynccontextmanager
async def v2_lifespan(app):
    """FastAPI lifespan context manager."""
    await initialize_v2_components()
    yield
    await shutdown_v2_components()


# ============================================================================
# API Router
# ============================================================================

router = APIRouter(prefix="/api/v2", tags=["Sapphire V2"])


# --- Trading Endpoints ---

@router.post("/trade")
async def execute_trade(request: TradeRequest):
    """
    Execute trade through dual-platform router.
    
    Platform routing:
    - auto: Router decides based on symbol
    - hyperliquid: Force Hyperliquid
    - drift: Force Drift
    """
    state = get_app_state()
    
    if not state.dual_router:
        raise HTTPException(status_code=503, detail="Dual router not initialized")
    
    # Force platform if specified
    if request.platform and request.platform.lower() in ("hyperliquid", "drift"):
        # Direct execution
        if request.platform.lower() == "hyperliquid" and state.hyperliquid_client:
            result = await state.hyperliquid_client.place_order(
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                order_type=request.order_type,
                price=request.price,
                reduce_only=request.reduce_only,
            )
            return {"success": True, "platform": "hyperliquid", "order": result.to_dict()}
        elif request.platform.lower() == "drift" and state.drift_client:
            result = await state.drift_client.place_order(
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
            )
            return {"success": True, "platform": "drift", "order": result}
    
    # Auto routing
    result = await state.dual_router.execute(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        order_type=request.order_type,
        price=request.price,
        reduce_only=request.reduce_only,
    )
    
    return result.to_dict()


@router.get("/trade/routing")
async def get_routing_info():
    """Get symbol to platform routing map."""
    state = get_app_state()
    
    if not state.dual_router:
        raise HTTPException(status_code=503, detail="Dual router not initialized")
    
    return {
        "success": True,
        "routing": state.dual_router.get_symbol_routing(),
        "stats": state.dual_router.get_routing_stats(),
    }


# --- Platform Endpoints ---

@router.get("/platforms/status")
async def get_platforms_status():
    """Get status of all trading platforms."""
    state = get_app_state()
    
    status = {
        "hyperliquid": {
            "enabled": state.hyperliquid_client is not None,
            "status": state.hyperliquid_client.get_status() if state.hyperliquid_client else None,
        },
        "drift": {
            "enabled": state.drift_client is not None,
        },
        "aster": {
            "enabled": state.aster_client is not None,
        },
        "symphony": {
            "enabled": state.symphony_client is not None,
        },
    }
    
    if state.circuit_manager:
        status["circuits"] = state.circuit_manager.get_all_status()
    
    return {"success": True, "platforms": status}


@router.get("/platforms/hyperliquid/positions")
async def get_hyperliquid_positions():
    """Get Hyperliquid positions."""
    state = get_app_state()
    
    if not state.hyperliquid_client:
        raise HTTPException(status_code=503, detail="Hyperliquid not configured")
    
    positions = await state.hyperliquid_client.get_positions()
    return {
        "success": True,
        "platform": "hyperliquid",
        "positions": [p.to_dict() for p in positions],
    }


@router.get("/platforms/drift/positions")
async def get_drift_positions():
    """Get Drift positions."""
    state = get_app_state()
    
    if not state.drift_client:
        raise HTTPException(status_code=503, detail="Drift not configured")
    
    if hasattr(state.drift_client, 'get_positions'):
        positions = await state.drift_client.get_positions()
        return {"success": True, "platform": "drift", "positions": positions}
    
    return {"success": True, "platform": "drift", "positions": []}


@router.get("/platforms/all/positions")
async def get_all_positions():
    """Get positions from all platforms."""
    state = get_app_state()
    
    if state.dual_router:
        return {
            "success": True,
            "positions": await state.dual_router.get_positions(),
        }
    
    return {"success": True, "positions": {}}


# --- Symphony Endpoints ---

@router.get("/symphony/status")
async def get_symphony_status():
    """Get Symphony agent status."""
    state = get_app_state()
    
    if not state.symphony_manager:
        raise HTTPException(status_code=503, detail="Symphony manager not initialized")
    
    return {"success": True, "data": state.symphony_manager.get_all_status()}


@router.get("/symphony/mit/status")
async def get_mit_status():
    """Get MIT activation status."""
    state = get_app_state()
    
    if not state.symphony_manager:
        raise HTTPException(status_code=503, detail="Symphony manager not initialized")
    
    mit = state.symphony_manager.get_mit_agent()
    
    return {
        "success": True,
        "ticker": mit.ticker,
        "status": mit.status.value,
        "is_activated": mit.is_active,
        "progress": mit.activation_progress,
        "threshold": mit.config.activation_threshold,
        "remaining": mit.trades_until_activation,
        "percent": round(mit.activation_percent, 1),
    }


@router.post("/symphony/mit/activate")
async def execute_mit_activation(request: MITActivationRequest):
    """Execute MIT activation trade."""
    state = get_app_state()
    
    if not state.symphony_manager:
        raise HTTPException(status_code=503, detail="Symphony manager not initialized")
    
    result = await state.symphony_manager.execute_mit_activation_trade(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
    )
    
    return result


# --- Memory Endpoints ---

@router.get("/memory/health")
async def get_memory_health():
    """Get memory system health."""
    state = get_app_state()
    
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="Memory manager not initialized")
    
    return {"success": True, "health": state.memory_manager.get_health().to_dict()}


@router.post("/memory/store")
async def store_memory(request: MemoryStoreRequest):
    """Store a new memory."""
    state = get_app_state()
    
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="Memory manager not initialized")
    
    try:
        memory_type = MemoryType(request.memory_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid memory type")
    
    memory = await state.memory_manager.remember(
        content=request.content,
        memory_type=memory_type,
        metadata=request.metadata,
        force_persist=True,
    )
    
    return {"success": True, "memory_id": memory.memory_id}


@router.post("/memory/recall")
async def recall_memories(request: MemoryRecallRequest):
    """Recall relevant memories."""
    state = get_app_state()
    
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="Memory manager not initialized")
    
    results = await state.memory_manager.recall(
        query=request.query,
        top_k=request.top_k,
    )
    
    return {
        "success": True,
        "results": [
            {"content": m.content, "type": m.memory_type.value, "relevance": round(r, 3)}
            for m, r in results
        ],
    }


# --- Health Endpoints ---

@router.get("/health")
async def v2_health():
    """V2 health check."""
    state = get_app_state()
    
    return {
        "status": "healthy" if state.initialized else "degraded",
        "v2_version": "2.2.0",
        "initialized": state.initialized,
        "startup_time": state.startup_time.isoformat() if state.startup_time else None,
        "components": {
            "hyperliquid": state.hyperliquid_client is not None,
            "drift": state.drift_client is not None,
            "dual_router": state.dual_router is not None,
            "symphony": state.symphony_manager is not None,
            "memory": state.memory_manager is not None,
        },
    }


# ============================================================================
# Helper Functions
# ============================================================================

def include_v2_router(app) -> None:
    """Include V2 router in FastAPI app."""
    app.include_router(router)
    logger.info("✅ [V2] Router included at /api/v2")


async def get_mit_activation_status() -> dict:
    """Quick helper to get MIT status."""
    state = get_app_state()
    
    if not state.symphony_manager:
        return {"error": "Not initialized", "is_active": False}
    
    mit = state.symphony_manager.get_mit_agent()
    return {
        "is_active": mit.is_active,
        "progress": mit.activation_progress,
        "remaining": mit.trades_until_activation,
    }


if __name__ == "__main__":
    print("Sapphire V2 Integration Module")
    print("Hyperliquid: REINSTATED ✅")
    print("Drift: ACTIVE ✅")
