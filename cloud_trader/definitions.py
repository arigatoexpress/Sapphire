"""Shared definitions to avoid circular imports.

VERSION: 2.0.1 - 2025-12-19 - String Formatting Precision Fix
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class HealthStatus:
    running: bool = True
    paper_trading: bool = True
    api_connected: bool = True
    last_error: Optional[str] = None


AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    # V2.3: AUTONOMOUS LEARNING AGENTS
    # Agents discover their own strategies through experience
    # NO hardcoded methods (no VPIN, Momentum, etc.)
    # Each platform trader learns what works best on its exchange
    {
        "id": "aster-autonomous-trader",
        "name": "Aster Autonomous Trader",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "⚡",
        "type": "adaptive_learning",  # Self-improving agent
        "symbols": [],  # Trades all available symbols
        "description": "Autonomous learning agent that discovers optimal trading strategies for Aster CEX through experience.",
        "personality": "Curious, adaptive trader that learns from every trade and evolves strategies organically.",
        "baseline_win_rate": 0.50,  # Starts neutral, improves through learning
        "risk_multiplier": 1.5,
        "profit_target": 0.025,  # Initial target, will adapt
        "stop_loss": 0.012,  # Initial stop, will adapt
        "margin_allocation": 1000.0,
        "specialization": "autonomous_learning",  # No fixed strategy
        # Self-tuning: agent modifies ALL parameters based on what works
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.40,  # Will adapt based on success
            "leverage": 20.0,  # Will discover optimal leverage
            "position_size_pct": 0.15,
        },
        "max_leverage_limit": 125.0,  # Shield strategy can use high leverage when learned
        "risk_tolerance": "adaptive",  # Learns optimal risk level
        "time_horizon": "adaptive",  # Discovers best holding periods
        # NO preferred regimes - agent learns when to trade
        "preferred_regimes": [],
        # Learning enabled
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
    },
    {
        "id": "market-maker-agent",
        "name": "Market Maker",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "⚡",
        "type": "market_maker",
        "symbols": [],
        "description": "High-frequency market making capturing bid-ask spreads.",
        "personality": "Precision market maker seeking consistent small profits.",
        "baseline_win_rate": 0.62,
        "risk_multiplier": 2.0,
        "profit_target": 0.008,  # 0.8% TP
        "stop_loss": 0.004,  # 0.4% SL
        "margin_allocation": 1200.0,
        "specialization": "market_making",
        # Self-tuning: agent can modify these based on performance
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.35,
            "leverage": 25.0,
            "position_size_pct": 0.10,
        },
        "max_leverage_limit": 50.0,
        "risk_tolerance": "medium",
        "time_horizon": "very_short",
        # ATR-based dynamic TP/SL (multipliers of ATR)
        "atr_tp_multiplier": 2.0,
        "atr_sl_multiplier": 1.0,
        # Regime preferences (boost/reduce activity)
        "preferred_regimes": ["ranging"],
    },
    {
        "id": "swing-trader-agent",
        "name": "Swing Trader",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "🧠",
        "type": "swing",
        "symbols": [],
        "description": "Strategic swing trader for multi-day trending positions.",
        "personality": "Patient swing trader capturing larger trend moves.",
        "baseline_win_rate": 0.68,
        "risk_multiplier": 1.3,
        "profit_target": 0.05,  # 5% TP
        "stop_loss": 0.02,  # 2% SL
        "margin_allocation": 1800.0,
        "specialization": "swing_trading",
        # Self-tuning: agent can modify these based on performance
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.35,
            "leverage": 10.0,
            "position_size_pct": 0.20,
        },
        "max_leverage_limit": 50.0,
        "risk_tolerance": "low",
        "time_horizon": "medium",
        # ATR-based dynamic TP/SL (multipliers of ATR)
        "atr_tp_multiplier": 4.0,
        "atr_sl_multiplier": 1.5,
        # Regime preferences (boost/reduce activity)
        "preferred_regimes": ["trending_up", "trending_down"],
    },
    # ============ ASTER AGENTS ============
    # These agents route to Aster for Monad/Base chain execution
    {
        "id": "monad-treasury-agent",  # Formerly MILF
        "name": "Monad Implementation Treasury Agent",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "🏛️",
        "type": "swap",
        "symbols": [],  # Empty = trade all ASTER_SYMBOLS dynamically
        "description": "Monad Treasury Agent focusing on top-market cap projects and whale tracking.",
        "personality": "Strategic Monad whale follower and smart money tracker.",
        "baseline_win_rate": 0.60,
        "risk_multiplier": 1.0,
        "profit_target": 0.03,
        "stop_loss": 0.015,
        "margin_allocation": 333.0,
        "specialization": "SWAP",
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.35,
            "leverage": 20.0,
            "position_size_pct": 0.15,
        },
        "max_leverage_limit": 50.0,
        "risk_tolerance": "medium",
        "time_horizon": "short",
        "preferred_regimes": ["trending_up", "trending_down"],
    },
    {
        "id": "ari-gold-fund",  # Formerly AGDG
        "name": "The Ari Gold Fund",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "🚁",
        "type": "perps",
        "symbols": ["ETH-USDC", "BTC-USDC", "DEGEN-USDC", "BRETT-USDC", "VIRTUAL-USDC"],
        "description": "The Ari Gold Fund: The Risk-On Choice. Asymmetric bets on Base Perps, AI, Privacy, and Virtuals.",
        "personality": "Aggressive, risk-on asymmetric bettor investing in AI/Privacy/Virtuals.",
        "baseline_win_rate": 0.60,
        "risk_multiplier": 1.5,
        "profit_target": 0.05,
        "stop_loss": 0.02,
        "margin_allocation": 1000.0,  # Increased allocation for the fund
        "specialization": "PERPS",
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.35,
            "leverage": 25.0,
            "position_size_pct": 0.20,
        },
        "max_leverage_limit": 50.0,
        "risk_tolerance": "high",
        "time_horizon": "short",
        "preferred_regimes": ["trending_up", "volatile"],
    },
    # Degen agent removed - consolidated into "The Ari Gold Fund"
    {
        "id": "aster-autonomous-trader",
        "name": "Aster Autonomous Trader",
        "model": "gemini-3-flash-preview",
        "system": "aster",
        "emoji": "🌀",
        "type": "adaptive_learning",
        "symbols": [],  # Learns which Solana tokens trade best
        "description": "Autonomous learning agent mastering Aster Protocol through experience and pattern discovery.",
        "personality": "Intelligent Solana trader that evolves strategies based on platform-specific insights.",
        "baseline_win_rate": 0.50,  # Improves through learning
        "risk_multiplier": 1.2,
        "profit_target": 0.03,  # Will adapt
        "stop_loss": 0.015,  # Will adapt
        "margin_allocation": 500.0,
        "specialization": "autonomous_learning",
        "self_tuning_enabled": True,
        "adaptive_params": {
            "confidence_threshold": 0.40,
            "leverage": 10.0,  # Will discover optimal leverage for Aster
            "position_size_pct": 0.15,
        },
        "max_leverage_limit": 20.0,
        "risk_tolerance": "adaptive",
        "time_horizon": "adaptive",
        "preferred_regimes": [],  # Learns when to trade
        "enable_episodic_memory": True,
        "enable_pattern_discovery": True,
    },
    # Lighter Agent Removed (Deprecated) - Coverage moved to Aster/Aster
]

# Agents trade all available symbols dynamically
# SYMBOL_CONFIG only used as fallback for quantity/precision if exchange info unavailable
# ⚠️ ASTER VERIFIED: Only symbols confirmed on fapi.asterdex.com/fapi/v1/exchangeInfo
SYMBOL_CONFIG = {
    # Liquid / Major (Aster Verified)
    "BTCUSDC": {"qty": 0.001, "precision": 3},
    "ETHUSDC": {"qty": 0.01, "precision": 2},
    "SOLUSDC": {"qty": 0.1, "precision": 2},
    # Monad Ecosystem (Aster Verified)
    "MONUSDC": {"qty": 1.0, "precision": 1},
    # Base Ecosystem (Aster Verified)
    "ASTERUSDC": {"qty": 10.0, "precision": 1},
    "TOSHIUSDC": {"qty": 1000.0, "precision": 0},
    # Lighter Cross-Listed (Aster Verified)
    "HYPEUSDC": {"qty": 1.0, "precision": 1},
    # Additional Aster-Verified Pairs
    "ZECUSDC": {"qty": 0.1, "precision": 2},
    "TRUMPUSDC": {"qty": 1.0, "precision": 1},
}

# Assets supported by Aster Agents (Monad chain priority)
# Assets supported by Aster Agents (Monad chain priority)
ASTER_SYMBOLS = [
    # Monad Ecosystem - Priority for chain launch incentives
    "ETH-USDC",  # Native ETH on Monad
    "MON-USDC",  # Monad native token
    # Base/Cross-chain
    "DAC-USDC",
    "ASTER-USDC",
    "BRETT-USDC",
    "DEGEN-USDC",
    "EMO-USDC",
    "CHOG-USDC",
    "VIRTUAL-USDC",
]

# Assets supported by Lighter (US-compatible exchange)
# Expanded to cover major trading pairs - bypasses Aster's US region block
LIGHTER_SYMBOLS = [
    # Major pairs (highest liquidity)
    "BTC-USDC", "BTCUSDT", "BTCUSD",
    "ETH-USDC", "ETHUSDT", "ETHUSD",
    "SOL-USDC", "SOLUSDT", "SOLUSD",
    # Altcoins available on Lighter
    "HYPE-USDC", "PURR-USDC",
    "BNB-USDC", "BNBUSDT",
    "AVAX-USDC", "AVAXUSDT",
    "MATIC-USDC", "MATICUSDT",
    "XRP-USDC", "XRPUSDT",
    "DOGE-USDC", "DOGEUSDT",
]

# Assets supported by Aster (Solana perps - US-compatible)
ASTER_SYMBOLS = [
    "JUP-USDC", "JUPUSDT",
    "PYTH-USDC", "PYTHUSDT",
    "BONK-USDC", "BONKUSDT",
    "SOL-USDC", "SOLUSDT",  # Also on Aster
]


# Assets supported by Lighter (L2 Order Book)
LIGHTER_SYMBOLS = [
    "WBTC-USDC",
    "WETH-USDC",
]

# Assets supported by Jupiter (Solana DEX Aggregator - SPOT ONLY)
# Jupiter aggregates best prices across all Solana DEXs for spot swaps
JUPITER_SPOT_SYMBOLS = [
    # Major Solana pairs
    "SOL-USDC", "SOLUSDT", "SOLUSD",
    # Solana ecosystem tokens
    "JUP-USDC", "JUPUSDT",  # Jupiter's own token
    "PYTH-USDC", "PYTHUSDT",
    "BONK-USDC", "BONKUSDT",
    "RAY-USDC",  # Raydium
    "ORCA-USDC",  # Orca
    "MNGO-USDC",  # Mango Markets
    # Wrapped major assets on Solana
    "ETH-USDC", "WETH-USDC",
    "BTC-USDC", "WBTC-USDC",
    "USDT-USDC",
]

# Legacy alias for backward compatibility
JUPITER_SYMBOLS = JUPITER_SPOT_SYMBOLS

# Assets supported by Aster (Solana Perpetuals - PERPS ONLY)
# Aster Protocol for leveraged perpetual futures trading
ASTER_PERP_SYMBOLS = [
    "SOL-PERP",
    "BTC-PERP",
    "ETH-PERP",
    "APT-PERP",
    "ARB-PERP",
    "AVAX-PERP",
    "BNB-PERP",
    "DOGE-PERP",
    "JTO-PERP",
    "MATIC-PERP",
    "OP-PERP",
    "PYTH-PERP",
    "SUI-PERP",
    "WIF-PERP",
    "JUP-PERP",
]


@dataclass
class MinimalAgentState:
    """State tracking for a trading agent with self-tuning capabilities."""

    # Core identity
    id: str
    name: str
    type: str  # Agent type for consensus engine (momentum, market_maker, swing, etc.)
    model: str
    emoji: str
    symbols: Optional[List[str]] = None  # None = trade all symbols
    description: str = ""
    personality: str = ""
    specialization: str = ""
    system: str = "aster"

    # Performance tracking
    active: bool = True
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    baseline_win_rate: float = 0.6
    margin_allocation: float = 1000.0
    daily_pnl: float = 0.0
    performance_score: float = 0.0
    last_active: Optional[float] = None

    # Self-tuning parameters (agent can modify these)
    self_tuning_enabled: bool = True
    dynamic_position_sizing: bool = True  # Whether to use dynamic position sizing
    adaptive_leverage: bool = True  # Whether to adjust leverage dynamically
    intelligence_tp_sl: bool = True  # Use intelligent TP/SL levels
    adaptive_params: Optional[Dict[str, Any]] = None

    # Position sizing limits
    min_position_size_pct: float = 0.08
    max_position_size_pct: float = 0.25

    # Risk limits
    max_leverage_limit: float = 50.0
    profit_target: float = 0.025  # 2.5% default
    stop_loss: float = 0.012  # 1.2% default
    risk_tolerance: str = "medium"
    time_horizon: str = "short"
    market_regime_preference: str = "neutral"  # Agent's preferred market conditions
    max_daily_loss_pct: float = 0.05
    daily_loss_breached: bool = False

    def __post_init__(self):
        if self.adaptive_params is None:
            self.adaptive_params = {
                "confidence_threshold": 0.35,
                "leverage": 20.0,
                "position_size_pct": 0.15,
            }

    def adjust_params(self, pnl: float):
        """Self-improvement: adjust params based on trade outcome."""
        if not self.self_tuning_enabled:
            return

        # Simple adaptive logic: tighten threshold on losses, loosen on wins
        if pnl > 0:
            # Winning trade: slightly lower threshold to take more trades
            self.adaptive_params["confidence_threshold"] = max(
                0.60, self.adaptive_params["confidence_threshold"] - 0.01
            )
        else:
            # Losing trade: raise threshold to be more selective
            self.adaptive_params["confidence_threshold"] = min(
                0.90, self.adaptive_params["confidence_threshold"] + 0.02
            )
