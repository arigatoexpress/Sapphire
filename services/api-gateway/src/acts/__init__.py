"""
ACTS - Autonomous Cognitive Trading Swarm

This package contains all components for the cognitive trading swarm:
- cognitive_mesh: Inter-agent communication fabric
- cognitive_agent: Scout, Sniper, Oracle agents with Gemini
- enhanced_episodic_memory: Learning from past episodes
- dual_speed_cognition: System 1 (Flash) + System 2 (Pro) thinking
- executor_agent: Platform-specific trade execution
- acts_orchestrator: Main coordinator
"""

from .cognitive_agent import CognitiveAgent, MarketContext, OracleAgent, ScoutAgent, SniperAgent
from .cognitive_mesh import (
    AgentRole,
    CognitiveMesh,
    CognitiveMessage,
    ConsensusState,
    MessageType,
    get_cognitive_mesh,
    init_cognitive_mesh,
)
from .dual_speed_cognition import (
    CognitionRequest,
    CognitionSpeed,
    DualSpeedCognition,
    get_dual_cognition,
)
from .enhanced_episodic_memory import (
    EnhancedEpisode,
    EnhancedMemoryBank,
    MarketRegime,
    MarketSnapshot,
    MultiFacetedLesson,
    auto_detect_regime,
    get_enhanced_memory,
)

__all__ = [
    # Mesh
    "CognitiveMesh",
    "CognitiveMessage",
    "ConsensusState",
    "MessageType",
    "AgentRole",
    "get_cognitive_mesh",
    "init_cognitive_mesh",
    # Memory
    "EnhancedMemoryBank",
    "EnhancedEpisode",
    "MarketSnapshot",
    "MarketRegime",
    "MultiFacetedLesson",
    "auto_detect_regime",
    "get_enhanced_memory",
    # Agents
    "CognitiveAgent",
    "ScoutAgent",
    "SniperAgent",
    "OracleAgent",
    "MarketContext",
    # Cognition
    "DualSpeedCognition",
    "CognitionSpeed",
    "CognitionRequest",
    "get_dual_cognition",
]
