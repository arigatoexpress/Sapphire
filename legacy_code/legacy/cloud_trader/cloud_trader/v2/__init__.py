"""
Sapphire V2 Enhancement Modules
================================
Multi-platform trading with Lighter and Aster.

Platforms:
- Lighter: ACTIVE ✅ (Reinstated DeFi Perps)
- Aster: ACTIVE ✅ (Solana Perps)
- Aster: ACTIVE ✅ (CEX)
- Aster: ACTIVE ✅ (Monad Treasury)

Version: 2.2.0
"""

from .lighter_client import (
    LighterClient,
    LighterOrder,
    LighterPosition,
)

from .dual_platform_router import (
    DualPlatformRouter,
    RoutingConfig,
    RoutingStrategy,
    RoutingDecision,
    ExecutionResult,
    create_dual_router,
)

from .aster_agent_manager import (
    AsterAgentManager,
    AsterAgent,
    AgentType,
    AgentStatus,
    create_aster_manager,
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

from .aster_mit_tracker import (
    AsterMITTracker,
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
    # Lighter Client
    "LighterClient",
    "LighterOrder",
    "LighterPosition",
    
    # Dual Platform Router
    "DualPlatformRouter",
    "RoutingConfig",
    "RoutingStrategy",
    "RoutingDecision",
    "ExecutionResult",
    "create_dual_router",
    
    # Aster Agent Manager
    "AsterAgentManager",
    "AsterAgent",
    "AgentType",
    "AgentStatus",
    "create_aster_manager",
    
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
    "AsterMITTracker",
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
