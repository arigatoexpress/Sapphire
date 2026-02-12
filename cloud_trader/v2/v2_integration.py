"""
Sapphire V2 Integration Module - Multi-Platform Edition
========================================================
Integrates all V2 components including reinstated Lighter.

Platforms:
- Lighter: ACTIVE ✅ (DeFi Perps)
- Aster: ACTIVE ✅ (Solana Perps)  
- Aster: ACTIVE ✅ (CEX)
- Aster: ACTIVE ✅ (Monad Treasury)

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
from .aster_agent_manager import (
    AgentType,
    AsterAgentManager,
    create_aster_manager,
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
from .lighter_client import (
    LighterClient,
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
    platform: Optional[str] = None  # lighter, aster, or auto
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
    lighter_client: Optional[LighterClient] = None
    aster_client: Optional[Any] = None
    aster_client: Optional[Any] = None
    aster_client: Optional[Any] = None
    
    # Core managers
    dual_router: Optional[DualPlatformRouter] = None
    aster_manager: Optional[AsterAgentManager] = None
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
    lighter_private_key: Optional[str] = None,
    lighter_wallet: Optional[str] = None,
    aster_private_key: Optional[str] = None,
    # Existing clients (optional)
    aster_client: Optional[Any] = None,
    aster_client: Optional[Any] = None,
    aster_client: Optional[Any] = None,
    firestore_client: Optional[Any] = None,
    # Configuration
    lighter_testnet: bool = False,
) -> SapphireV2State:
    """
    Initialize all V2 components including Lighter.
    
    Args:
        lighter_private_key: Lighter wallet private key
        lighter_wallet: Lighter wallet address
        aster_private_key: Aster/Solana private key
        aster_client: Existing Aster client
        aster_client: Existing Aster client
        aster_client: Existing Aster client
        firestore_client: Firestore client for persistence
        lighter_testnet: Use Lighter testnet
        
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
    
    # 2. Initialize Lighter Client
    if lighter_private_key and lighter_wallet:
        logger.info("  🔷 Initializing Lighter Client...")
        try:
            state.lighter_client = LighterClient(
                private_key=lighter_private_key,
                wallet_address=lighter_wallet,
                testnet=lighter_testnet,
            )
            await state.lighter_client.initialize()
            logger.info("  ✅ Lighter Client ready")
        except Exception as e:
            logger.error(f"  ❌ Lighter Client failed: {e}")
    else:
        logger.warning("  ⚠️ Lighter credentials not provided - client disabled")
    
    # 3. Store existing clients
    state.aster_client = aster_client
    state.aster_client = aster_client
    state.aster_client = aster_client
    
    # 4. Initialize Dual Platform Router
    if state.lighter_client or state.aster_client:
        logger.info("  🔀 Initializing Dual Platform Router...")
        try:
            state.dual_router = await create_dual_router(
                lighter_client=state.lighter_client,
                aster_client=state.aster_client,
            )
            logger.info("  ✅ Dual Router ready")
        except Exception as e:
            logger.error(f"  ❌ Dual Router failed: {e}")
    
    # 5. Initialize Aster Agent Manager
    logger.info("  🎭 Initializing Aster Agent Manager...")
    try:
        state.aster_manager = await create_aster_manager(
            firestore_client=firestore_client,
            aster_client=aster_client,
        )
        logger.info("  ✅ Aster Manager ready ($MILF, $AGDG active, $MIT pending)")
    except Exception as e:
        logger.error(f"  ❌ Aster Manager failed: {e}")
    
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
        f"  Lighter: {'✅ ACTIVE' if state.lighter_client else '❌ Disabled'}\n"
        f"  Aster: {'✅ ACTIVE' if state.aster_client else '❌ Disabled'}\n"
        f"  Dual Router: {'✅ Ready' if state.dual_router else '❌ Disabled'}\n"
        f"  Aster: {'✅ Ready' if state.aster_manager else '❌ Disabled'}\n"
        f"  Memory: {'✅ Ready' if state.memory_manager else '❌ Disabled'}\n"
        f"{'='*60}\n"
    )
    
    # Log MIT status
    if state.aster_manager:
        mit = state.aster_manager.get_mit_agent()
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
    
    if state.lighter_client:
        await state.lighter_client.close()
    
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
    - lighter: Force Lighter
    - aster: Force Aster
    """
    state = get_app_state()
    
    if not state.dual_router:
        raise HTTPException(status_code=503, detail="Dual router not initialized")
    
    # Force platform if specified
    if request.platform and request.platform.lower() in ("lighter", "aster"):
        # Direct execution
        if request.platform.lower() == "lighter" and state.lighter_client:
            result = await state.lighter_client.place_order(
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                order_type=request.order_type,
                price=request.price,
                reduce_only=request.reduce_only,
            )
            return {"success": True, "platform": "lighter", "order": result.to_dict()}
        elif request.platform.lower() == "aster" and state.aster_client:
            result = await state.aster_client.place_order(
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
            )
            return {"success": True, "platform": "aster", "order": result}
    
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
        "lighter": {
            "enabled": state.lighter_client is not None,
            "status": state.lighter_client.get_status() if state.lighter_client else None,
        },
        "aster": {
            "enabled": state.aster_client is not None,
        },
        "aster": {
            "enabled": state.aster_client is not None,
        },
        "aster": {
            "enabled": state.aster_client is not None,
        },
    }
    
    if state.circuit_manager:
        status["circuits"] = state.circuit_manager.get_all_status()
    
    return {"success": True, "platforms": status}


@router.get("/platforms/lighter/positions")
async def get_lighter_positions():
    """Get Lighter positions."""
    state = get_app_state()
    
    if not state.lighter_client:
        raise HTTPException(status_code=503, detail="Lighter not configured")
    
    positions = await state.lighter_client.get_positions()
    return {
        "success": True,
        "platform": "lighter",
        "positions": [p.to_dict() for p in positions],
    }


@router.get("/platforms/aster/positions")
async def get_aster_positions():
    """Get Aster positions."""
    state = get_app_state()
    
    if not state.aster_client:
        raise HTTPException(status_code=503, detail="Aster not configured")
    
    if hasattr(state.aster_client, 'get_positions'):
        positions = await state.aster_client.get_positions()
        return {"success": True, "platform": "aster", "positions": positions}
    
    return {"success": True, "platform": "aster", "positions": []}


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


# --- Aster Endpoints ---

@router.get("/aster/status")
async def get_aster_status():
    """Get Aster agent status."""
    state = get_app_state()
    
    if not state.aster_manager:
        raise HTTPException(status_code=503, detail="Aster manager not initialized")
    
    return {"success": True, "data": state.aster_manager.get_all_status()}


@router.get("/aster/mit/status")
async def get_mit_status():
    """Get MIT activation status."""
    state = get_app_state()
    
    if not state.aster_manager:
        raise HTTPException(status_code=503, detail="Aster manager not initialized")
    
    mit = state.aster_manager.get_mit_agent()
    
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


@router.post("/aster/mit/activate")
async def execute_mit_activation(request: MITActivationRequest):
    """Execute MIT activation trade."""
    state = get_app_state()
    
    if not state.aster_manager:
        raise HTTPException(status_code=503, detail="Aster manager not initialized")
    
    result = await state.aster_manager.execute_mit_activation_trade(
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
            "lighter": state.lighter_client is not None,
            "aster": state.aster_client is not None,
            "dual_router": state.dual_router is not None,
            "aster": state.aster_manager is not None,
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
    
    if not state.aster_manager:
        return {"error": "Not initialized", "is_active": False}
    
    mit = state.aster_manager.get_mit_agent()
    return {
        "is_active": mit.is_active,
        "progress": mit.activation_progress,
        "remaining": mit.trades_until_activation,
    }


if __name__ == "__main__":
    print("Sapphire V2 Integration Module")
    print("Lighter: REINSTATED ✅")
    print("Aster: ACTIVE ✅")
