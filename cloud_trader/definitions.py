"""Shared definitions to avoid circular imports."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class HealthStatus:
    running: bool
    paper_trading: bool
    last_error: Optional[str]


AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "trend-momentum-agent",
        "name": "Trend Momentum (Gemini)",
        "model": "gemini-2.0-flash-exp",
        "system": "aster",
        "emoji": "📈",
        "symbols": [],
        "description": "High-speed momentum analysis using Gemini 2.0 Flash (Next-Gen) for Aster ecosystem.",
        "personality": "Aggressive momentum trader.",
        "baseline_win_rate": 0.65,
        "risk_multiplier": 1.4,
        "profit_target": 0.008,
        "margin_allocation": 500.0,
        "specialization": "momentum_trading",
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 50.0,
        "min_position_size_pct": 0.08,
        "max_position_size_pct": 0.25,
        "risk_tolerance": "high",
        "time_horizon": "very_short",
        "market_regime_preference": "trending",
    },
    {
        "id": "financial-sentiment-agent",
        "name": "Sentiment (Gemini)",
        "model": "gemini-2.0-flash-exp",
        "system": "aster",
        "emoji": "💭",
        "symbols": [],
        "description": "Real-time sentiment analysis using Gemini 2.0 Flash (Next-Gen).",
        "personality": "News-driven sentiment trader.",
        "baseline_win_rate": 0.58,
        "risk_multiplier": 1.8,
        "profit_target": 0.012,
        "margin_allocation": 500.0,
        "specialization": "sentiment_analysis",
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 50.0,
        "min_position_size_pct": 0.08,
        "max_position_size_pct": 0.28,
        "risk_tolerance": "high",
        "time_horizon": "short_medium",
        "market_regime_preference": "news_driven",
    },
    {
        "id": "market-maker-agent",
        "name": "Market Maker (Gemini)",
        "model": "gemini-2.0-flash-exp",
        "system": "aster",
        "emoji": "⚡",
        "symbols": [],
        "description": "High-frequency market making with tight spreads on Aster DEX.",
        "personality": "Precision market maker seeking bid-ask profit.",
        "baseline_win_rate": 0.62,
        "risk_multiplier": 2.0,
        "profit_target": 0.003,
        "margin_allocation": 800.0,
        "specialization": "market_making",
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 50.0,
        "min_position_size_pct": 0.05,
        "max_position_size_pct": 0.15,
        "risk_tolerance": "high",
        "time_horizon": "very_short",
        "market_regime_preference": "ranging",
    },
    {
        "id": "swing-trader-agent",
        "name": "Swing Trader (Gemini)",
        "model": "gemini-2.0-flash-exp",
        "system": "aster",
        "emoji": "🧠",
        "symbols": [],
        "description": "Strategic swing trader for multi-day positions on Aster DEX.",
        "personality": "Patient swing trader capturing larger moves.",
        "baseline_win_rate": 0.68,
        "risk_multiplier": 1.3,
        "profit_target": 0.03,
        "margin_allocation": 1500.0,
        "specialization": "swing_trading",
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 50.0,
        "min_position_size_pct": 0.1,
        "max_position_size_pct": 0.3,
        "risk_tolerance": "low",
        "time_horizon": "medium",
        "market_regime_preference": "trending",
    },
]

# Agents trade all available symbols dynamically
# SYMBOL_CONFIG only used as fallback for quantity/precision if exchange info unavailable
SYMBOL_CONFIG = {
    # Dynamic agents will use exchange info for precision
}


@dataclass
class MinimalAgentState:
    """State tracking for a minimal trading agent."""

    id: str
    name: str
    model: str
    emoji: str
    symbols: Optional[List[str]] = None  # Optional - agents can trade any symbols
    description: str = ""
    personality: str = ""
    baseline_win_rate: float = 0.0
    margin_allocation: float = 1000.0
    specialization: str = ""
    active: bool = True
    performance_score: float = 0.0
    last_active: Optional[float] = None
    total_trades: int = 0
    wins: int = 0  # Track actual winning trades
    losses: int = 0  # Track actual losing trades
    win_rate: float = 0.0
    dynamic_position_sizing: bool = True
    adaptive_leverage: bool = True
    intelligence_tp_sl: bool = True
    max_leverage_limit: float = 10.0
    min_position_size_pct: float = 0.08
    max_position_size_pct: float = 0.25
    risk_tolerance: str = "moderate"
    time_horizon: str = "short"
    market_regime_preference: str = "all_regimes"
    daily_pnl: float = 0.0
    last_intervention: Optional[Dict[str, Any]] = None
    intervention_history: List[Dict[str, Any]] = None
    # Additional fields used in minimal_trading_service.py
    system: str = "aster"  # "aster" or "hyperliquid"
    max_daily_loss_pct: float = 0.05  # 5% daily loss limit
    daily_loss_breached: bool = False
    daily_volume: float = 0.0
    max_position_size_today: float = 0.0
    whale_trade_executed: bool = False
    avalon_spot_volume: float = 0.0

    def __post_init__(self):
        if self.intervention_history is None:
            self.intervention_history = []
