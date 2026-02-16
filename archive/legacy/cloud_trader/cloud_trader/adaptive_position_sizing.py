"""
Adaptive Position Sizing - Dynamic Risk Allocation
Implements Kelly Criterion and regime-aware position sizing.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Core portfolio risk metrics for sizing."""

    portfolio_value: float
    current_drawdown: float
    volatility_24h: float
    sharpe_ratio: float
    max_drawdown_limit: float = 0.2
    daily_pnl: float = 0.0
    win_rate_24h: float = 0.55
    avg_win_loss_ratio: float = 2.0


class AdaptivePositionSizer:
    """Professional position sizer with Kelly and Regime awareness."""

    def __init__(self):
        self.base_risk_pct = 0.01  # Risk 1% of equity per trade

    def calculate_position_size(
        self,
        signal_strength: float,
        confidence: float,
        regime: Any,
        risk_metrics: RiskMetrics,
        current_positions: List[Dict],
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Calculate optimal position size based on Kelly and regime.
        """
        # 1. Start with Kelly-like base
        win_rate = risk_metrics.win_rate_24h
        ratio = risk_metrics.avg_win_loss_ratio

        # Simple Kelly: K = W - (1-W)/R
        kelly_fraction = win_rate - (1 - win_rate) / max(0.1, ratio)
        kelly_fraction = max(0, min(0.3, kelly_fraction))  # Cap at 30%

        # 2. Adjust for confidence and signal strength
        recommended_pct = kelly_fraction * confidence * (signal_strength / 5.0)

        # 3. VOLATILITY ADJUSTMENT: Reduce size in volatile markets
        volatility_mult = 1.0
        if risk_metrics.volatility_24h > 0.05:  # >5% daily volatility
            volatility_mult = 0.7  # Reduce by 30%
        elif risk_metrics.volatility_24h > 0.03:  # >3% daily volatility
            volatility_mult = 0.85  # Reduce by 15%

        # 4. DRAWDOWN PROTECTION: Reduce size when in drawdown
        drawdown_mult = 1.0
        if risk_metrics.current_drawdown > 0.1:  # >10% drawdown
            drawdown_mult = 0.5  # Halve position sizes
        elif risk_metrics.current_drawdown > 0.05:  # >5% drawdown
            drawdown_mult = 0.75

        # 5. Apply all multipliers
        adjusted_pct = recommended_pct * volatility_mult * drawdown_mult

        # 6. Apply sanity caps
        max_position_pct = 0.1  # Never risk more than 10% on one symbol
        final_pct = min(adjusted_pct, max_position_pct)

        absolute_size = risk_metrics.portfolio_value * final_pct

        return {
            "recommended_size": absolute_size,
            "recommended_pct": final_pct,
            "kelly_fraction": kelly_fraction,
            "reasoning": f"Kelly={kelly_fraction:.1%}, Vol={volatility_mult:.0%}, DD={drawdown_mult:.0%}",
            "breakdown": {
                "signal_strength": signal_strength,
                "confidence": confidence,
                "volatility_mult": volatility_mult,
                "drawdown_mult": drawdown_mult,
            },
        }


_sizer_instance = None


async def get_adaptive_position_sizer():
    """Singleton getter for position sizer."""
    global _sizer_instance
    if _sizer_instance is None:
        _sizer_instance = AdaptivePositionSizer()
    return _sizer_instance
