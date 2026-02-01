"""
V2.3 Autonomous Agent Definitions - Self-Learning Platform Traders

Philosophy:
- NO hardcoded strategies (no VPIN, Momentum, Market Making, etc.)
- Each platform trader discovers its own optimal methodology
- Agents learn from experience and adapt continuously
- Platform-specific expertise develops organically
- Frequent trading with self-evolved strategies

One autonomous agent per platform, each mastering its exchange.
"""

from typing import Any, Dict, List

# V2.3 AUTONOMOUS AGENTS - One per platform
AUTONOMOUS_AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "drift-learner",
        "name": "Drift Autonomous Trader",
        "platform": "drift",
        "model": "gemini-3.0-flash-001",
        "system": "drift",
        "emoji": "🌀",
        "description": "Self-learning trader mastering Drift Protocol (Solana Perps) through experience.",
        "personality": "Adaptive, data-driven trader that discovers optimal patterns for Solana perpetuals.",

        # Learning Configuration
        "type": "autonomous_learning",
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
        "exploration_rate": 0.25,  # 25% explore, 75% exploit

        # Starting Parameters (will adapt)
        "baseline_win_rate": 0.50,
        "margin_allocation": 500.0,
        "self_tuning_enabled": True,

        "adaptive_params": {
            "confidence_threshold": 0.40,  # Will adapt
            "leverage": 10.0,  # Discovers optimal leverage
            "position_size_pct": 0.15,  # Learns position sizing
        },
        "max_leverage_limit": 20.0,

        # Flexible parameters (agent determines)
        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",  # Learns best holding periods
        "symbols": [],  # Learns which symbols trade best

        # NO fixed strategies
        "specialization": "autonomous_learning",
        "preferred_regimes": [],  # Discovers when to trade
    },
    {
        "id": "hyperliquid-learner",
        "name": "Hyperliquid Autonomous Trader",
        "platform": "hyperliquid",
        "model": "gemini-3.0-flash-001",
        "system": "hyperliquid",
        "emoji": "🔷",
        "description": "Self-learning trader mastering Hyperliquid L1 through pattern discovery.",
        "personality": "Intelligent L1 trader evolving strategies based on what works.",

        "type": "autonomous_learning",
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
        "exploration_rate": 0.25,

        "baseline_win_rate": 0.50,
        "margin_allocation": 800.0,
        "self_tuning_enabled": True,

        "adaptive_params": {
            "confidence_threshold": 0.40,
            "leverage": 15.0,
            "position_size_pct": 0.15,
        },
        "max_leverage_limit": 50.0,

        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",
        "symbols": [],
        "specialization": "autonomous_learning",
        "preferred_regimes": [],
    },
    {
        "id": "aster-learner",
        "name": "Aster Autonomous Trader",
        "platform": "aster",
        "model": "gemini-3.0-flash-001",
        "system": "aster",
        "emoji": "⚡",
        "description": "Self-learning HFT trader mastering Aster CEX through continuous adaptation.",
        "personality": "Fast-learning HFT specialist discovering optimal execution strategies.",

        "type": "autonomous_learning",
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
        "exploration_rate": 0.30,  # More exploration for HFT

        "baseline_win_rate": 0.50,
        "margin_allocation": 1200.0,
        "self_tuning_enabled": True,

        "adaptive_params": {
            "confidence_threshold": 0.45,  # Higher initial bar for quality
            "leverage": 20.0,
            "position_size_pct": 0.12,
        },
        "max_leverage_limit": 125.0,  # Can learn high-leverage strategies

        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",
        "symbols": [],
        "specialization": "autonomous_learning",
        "preferred_regimes": [],
    },
    {
        "id": "symphony-learner",
        "name": "Symphony Autonomous Trader",
        "platform": "symphony",
        "model": "gemini-3.0-flash-001",
        "system": "symphony",
        "emoji": "🎵",
        "description": "Self-learning treasury agent mastering Monad/Base ecosystem.",
        "personality": "Strategic learner discovering profitable patterns in Monad ecosystem.",

        "type": "autonomous_learning",
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
        "exploration_rate": 0.20,  # Less exploration, more consistent

        "baseline_win_rate": 0.50,
        "margin_allocation": 600.0,
        "self_tuning_enabled": True,

        "adaptive_params": {
            "confidence_threshold": 0.40,
            "leverage": 15.0,
            "position_size_pct": 0.15,
        },
        "max_leverage_limit": 25.0,

        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",
        "symbols": [],  # Learns which Monad tokens work best
        "specialization": "autonomous_learning",
        "preferred_regimes": [],
    },
    {
        "id": "lighter-learner",
        "name": "Lighter Autonomous Trader",
        "platform": "lighter",
        "model": "gemini-3.0-flash-001",
        "system": "lighter",
        "emoji": "💡",
        "description": "Self-learning trader mastering Lighter L2 orderbook dynamics.",
        "personality": "Methodical learner discovering L2 arbitrage and market-making opportunities.",

        "type": "autonomous_learning",
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
        "exploration_rate": 0.25,

        "baseline_win_rate": 0.50,
        "margin_allocation": 400.0,
        "self_tuning_enabled": True,

        "adaptive_params": {
            "confidence_threshold": 0.40,
            "leverage": 8.0,
            "position_size_pct": 0.12,
        },
        "max_leverage_limit": 10.0,

        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",
        "symbols": [],  # Learns which L2 pairs trade best
        "specialization": "autonomous_learning",
        "preferred_regimes": [],
    },
]
