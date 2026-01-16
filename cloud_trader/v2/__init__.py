"""
Sapphire V2 Enhancement Modules
================================
Multi-platform trading with Hyperliquid and Drift.

Platforms:
- Hyperliquid: ACTIVE ✅ (Reinstated DeFi Perps)
- Drift: ACTIVE ✅ (Solana Perps)
- Aster: ACTIVE ✅ (CEX)
- Symphony: ACTIVE ✅ (Monad Treasury)

Version: 2.2.0
"""

from .hyperliquid_client import (
    HyperliquidClient,
    HyperliquidConfig,
    HyperliquidOrder,
    HyperliquidPosition,
    create_hyperliquid_client,
)

from .dual_platform_router import (
    DualPlatformRouter,
    RoutingConfig,
    RoutingStrategy,
    RoutingDecision,
    ExecutionResult,
    create_dual_router,
)

from .symphony_agent_manager import (
    SymphonyAgentManager,
    SymphonyAgent,
    AgentType,
    AgentStatus,
    create_symphony_manager,
)

from .hardened_memory_manager import (
    HardenedMemoryManager,
    Memory,
    MemoryType,
    MemoryHealth,
    create_memory_manager,
)

from .enhanced_circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitConfig,
    CircuitOpenError,
    Platform,
    PlatformCircuitManager,
    get_circuit_manager,
    configure_circuit_manager,
    circuit_protected,
)

from .symphony_mit_tracker import (
    SymphonyMITTracker,
    MITActivationState,
    MITActivationProgress,
    create_mit_tracker,
)

from .v2_integration import (
    SapphireV2State,
    initialize_v2_components,
    shutdown_v2_components,
    get_app_state,
    get_mit_activation_status,
    include_v2_router,
    v2_lifespan,
    router as v2_router,
)

__all__ = [
    # Hyperliquid Client
    "HyperliquidClient",
    "HyperliquidConfig",
    "HyperliquidOrder",
    "HyperliquidPosition",
    "create_hyperliquid_client",
    
    # Dual Platform Router
    "DualPlatformRouter",
    "RoutingConfig",
    "RoutingStrategy",
    "RoutingDecision",
    "ExecutionResult",
    "create_dual_router",
    
    # Symphony Agent Manager
    "SymphonyAgentManager",
    "SymphonyAgent",
    "AgentType",
    "AgentStatus",
    "create_symphony_manager",
    
    # Memory Manager
    "HardenedMemoryManager",
    "Memory",
    "MemoryType",
    "MemoryHealth",
    "create_memory_manager",
    
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitConfig",
    "CircuitOpenError",
    "Platform",
    "PlatformCircuitManager",
    "get_circuit_manager",
    "configure_circuit_manager",
    "circuit_protected",
    
    # MIT Tracker
    "SymphonyMITTracker",
    "MITActivationState",
    "MITActivationProgress",
    "create_mit_tracker",
    
    # V2 Integration
    "SapphireV2State",
    "initialize_v2_components",
    "shutdown_v2_components",
    "get_app_state",
    "get_mit_activation_status",
    "include_v2_router",
    "v2_lifespan",
    "v2_router",
]

__version__ = "2.2.0"
