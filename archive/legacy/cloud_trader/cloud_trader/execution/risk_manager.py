"""
Sapphire V2 Risk Manager
Professional-grade portfolio risk management.

Features:
- Position sizing (Kelly Criterion, Fixed %, Volatility-adjusted)
- Dynamic stop-loss and take-profit
- Portfolio-level risk limits
- Drawdown protection
- Correlation-aware allocation
"""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SizingMethod(Enum):
    """Position sizing methods."""

    FIXED_AMOUNT = "fixed_amount"  # Fixed USD per trade
    FIXED_PERCENT = "fixed_percent"  # Fixed % of portfolio
    KELLY = "kelly"  # Kelly Criterion
    VOLATILITY = "volatility"  # Volatility-adjusted
    RISK_PARITY = "risk_parity"  # Risk parity allocation


@dataclass
class RiskLimits:
    """Portfolio risk limits."""

    max_position_pct: float = 0.20  # Max 20% in single position
    max_total_exposure_pct: float = 0.80  # Max 80% portfolio exposed
    max_daily_loss_pct: float = 0.05  # Max 5% daily drawdown
    max_drawdown_pct: float = 0.15  # Max 15% total drawdown
    max_correlation: float = 0.70  # Max correlation between positions
    max_positions: int = 10  # Max concurrent positions


@dataclass
class PositionSize:
    """Calculated position size with reasoning."""

    symbol: str
    recommended_size_usd: float
    recommended_quantity: float
    sizing_method: SizingMethod
    confidence: float
    stop_loss_pct: float
    take_profit_pct: float
    risk_reward_ratio: float
    reasoning: str


@dataclass
class RiskAssessment:
    """Portfolio risk assessment."""

    total_exposure_pct: float
    largest_position_pct: float
    current_drawdown_pct: float
    daily_pnl_pct: float
    var_95_pct: float  # Value at Risk
    correlation_risk: str  # low, moderate, high
    risk_score: float  # 0-100
    warnings: List[str]
    can_trade: bool


class RiskManager:
    """
    Professional portfolio risk management.
    """

    def __init__(self, portfolio_value: float = 10000.0):
        self.portfolio_value = portfolio_value
        self.limits = RiskLimits()

        # Track daily performance
        self._day_start_value = portfolio_value
        self._peak_value = portfolio_value

        # Historical data for calculations
        self._returns_history: List[float] = []
        self._volatility_cache: Dict[str, float] = {}

        logger.info(f"📊 RiskManager initialized with ${portfolio_value:,.2f} portfolio")

    def calculate_position_size(
        self,
        symbol: str,
        side: str,
        current_price: float,
        confidence: float,
        win_rate: float = 0.55,
        avg_win: float = 0.03,
        avg_loss: float = 0.02,
        method: SizingMethod = SizingMethod.VOLATILITY,
    ) -> PositionSize:
        """
        Calculate optimal position size.
        """
        if method == SizingMethod.FIXED_AMOUNT:
            size_usd = 100.0  # Fixed $100 per trade

        elif method == SizingMethod.FIXED_PERCENT:
            size_usd = self.portfolio_value * 0.02  # 2% per trade

        elif method == SizingMethod.KELLY:
            # Kelly Criterion: f* = (p*b - q) / b
            # p = win rate, q = loss rate, b = win/loss ratio
            if avg_loss > 0:
                b = avg_win / avg_loss
                kelly_fraction = (win_rate * b - (1 - win_rate)) / b
                kelly_fraction = max(0, min(0.25, kelly_fraction))  # Cap at 25%
                size_usd = self.portfolio_value * kelly_fraction
            else:
                size_usd = self.portfolio_value * 0.02

        elif method == SizingMethod.VOLATILITY:
            # Volatility-adjusted: smaller positions for volatile assets
            volatility = self._volatility_cache.get(symbol, 0.05)  # Default 5%
            target_risk = 0.01  # Target 1% portfolio risk per trade
            size_usd = (self.portfolio_value * target_risk) / max(volatility, 0.01)
            size_usd = min(size_usd, self.portfolio_value * 0.10)  # Cap at 10%

        else:  # RISK_PARITY
            size_usd = self.portfolio_value * 0.05  # 5% per position

        # Adjust for confidence
        size_usd *= confidence

        # Apply limits
        max_size = self.portfolio_value * self.limits.max_position_pct
        size_usd = min(size_usd, max_size)

        # Calculate quantity
        quantity = size_usd / current_price if current_price > 0 else 0

        # Calculate stop-loss and take-profit
        volatility = self._volatility_cache.get(symbol, 0.05)
        stop_loss_pct = max(0.02, volatility * 1.5)  # 1.5x volatility
        take_profit_pct = stop_loss_pct * 2  # 2:1 reward/risk default

        risk_reward = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0

        logger.info(
            f"📏 Position size for {symbol}: ${size_usd:.2f} "
            f"({method.value}, conf: {confidence:.2f})"
        )

        return PositionSize(
            symbol=symbol,
            recommended_size_usd=size_usd,
            recommended_quantity=quantity,
            sizing_method=method,
            confidence=confidence,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            risk_reward_ratio=risk_reward,
            reasoning=f"{method.value}: ${size_usd:.2f} at {confidence:.0%} confidence",
        )

    def assess_portfolio_risk(
        self, positions: Dict[str, Dict], current_value: float
    ) -> RiskAssessment:
        """
        Assess current portfolio risk.
        """
        warnings = []

        # Calculate exposures
        total_exposure = sum(
            p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0))
            for p in positions.values()
        )
        total_exposure_pct = total_exposure / current_value if current_value > 0 else 0

        # Largest position
        position_sizes = [
            p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0))
            for p in positions.values()
        ]
        largest_position_pct = (
            max(position_sizes) / current_value if position_sizes and current_value > 0 else 0
        )

        # Drawdown
        current_drawdown = (
            (self._peak_value - current_value) / self._peak_value if self._peak_value > 0 else 0
        )
        if current_value > self._peak_value:
            self._peak_value = current_value

        # Daily P&L
        daily_pnl_pct = (
            (current_value - self._day_start_value) / self._day_start_value
            if self._day_start_value > 0
            else 0
        )

        # VaR (simplified - historical simulation)
        var_95 = self._calculate_var(positions)

        # Correlation risk (simplified)
        correlation_risk = "low"
        if len(positions) > 3:
            correlation_risk = "moderate"
        if len(positions) > 6:
            correlation_risk = "high"

        # Check limits
        can_trade = True

        if total_exposure_pct > self.limits.max_total_exposure_pct:
            warnings.append(
                f"Exposure {total_exposure_pct:.1%} exceeds limit {self.limits.max_total_exposure_pct:.0%}"
            )
            can_trade = False

        if largest_position_pct > self.limits.max_position_pct:
            warnings.append(f"Largest position {largest_position_pct:.1%} exceeds limit")

        if current_drawdown > self.limits.max_drawdown_pct:
            warnings.append(f"Drawdown {current_drawdown:.1%} exceeds maximum")
            can_trade = False

        if daily_pnl_pct < -self.limits.max_daily_loss_pct:
            warnings.append(f"Daily loss {daily_pnl_pct:.1%} exceeds limit")
            can_trade = False

        if len(positions) >= self.limits.max_positions:
            warnings.append(f"At maximum positions ({self.limits.max_positions})")
            can_trade = False

        # Calculate risk score (0-100, higher = riskier)
        risk_score = (
            (total_exposure_pct / self.limits.max_total_exposure_pct) * 30
            + (current_drawdown / self.limits.max_drawdown_pct) * 30
            + (largest_position_pct / self.limits.max_position_pct) * 20
            + (len(positions) / self.limits.max_positions) * 20
        )
        risk_score = min(100, risk_score * 100)

        return RiskAssessment(
            total_exposure_pct=total_exposure_pct,
            largest_position_pct=largest_position_pct,
            current_drawdown_pct=current_drawdown,
            daily_pnl_pct=daily_pnl_pct,
            var_95_pct=var_95,
            correlation_risk=correlation_risk,
            risk_score=risk_score,
            warnings=warnings,
            can_trade=can_trade,
        )

    def calculate_dynamic_stops(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: str,
        unrealized_pnl_pct: float,
    ) -> Dict[str, float]:
        """
        Calculate dynamic stop-loss and take-profit levels.
        Uses trailing stops and profit protection.
        """
        volatility = self._volatility_cache.get(symbol, 0.05)

        # Base stop at 1.5x volatility
        base_stop_pct = volatility * 1.5

        # Trailing stop logic
        if unrealized_pnl_pct > 0.05:  # In profit > 5%
            # Tighten stop to lock in gains
            stop_distance = max(0.02, base_stop_pct * 0.5)
        elif unrealized_pnl_pct > 0.02:  # In profit > 2%
            stop_distance = base_stop_pct * 0.75
        else:
            stop_distance = base_stop_pct

        # Calculate actual price levels
        if side == "BUY":
            stop_loss = current_price * (1 - stop_distance)
            take_profit = entry_price * (1 + base_stop_pct * 2)  # 2:1 R/R
        else:
            stop_loss = current_price * (1 + stop_distance)
            take_profit = entry_price * (1 - base_stop_pct * 2)

        # Breakeven stop if in decent profit
        if unrealized_pnl_pct > 0.03:
            if side == "BUY":
                stop_loss = max(stop_loss, entry_price * 1.005)  # 0.5% above entry
            else:
                stop_loss = min(stop_loss, entry_price * 0.995)

        return {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_distance_pct": stop_distance,
            "is_trailing": unrealized_pnl_pct > 0.02,
        }

    def _calculate_var(self, positions: Dict) -> float:
        """Calculate Value at Risk (95% confidence)."""
        if not self._returns_history or len(self._returns_history) < 20:
            return 0.05  # Default 5% VaR

        # Sort returns and find 5th percentile
        sorted_returns = sorted(self._returns_history)
        var_index = int(len(sorted_returns) * 0.05)
        return abs(sorted_returns[var_index])

    def update_portfolio_value(self, new_value: float):
        """Update portfolio value and track returns."""
        if self.portfolio_value > 0:
            daily_return = (new_value - self.portfolio_value) / self.portfolio_value
            self._returns_history.append(daily_return)
            if len(self._returns_history) > 252:  # Keep 1 year
                self._returns_history.pop(0)

        self.portfolio_value = new_value
        if new_value > self._peak_value:
            self._peak_value = new_value

    def update_volatility(self, symbol: str, volatility: float):
        """Update volatility estimate for a symbol."""
        self._volatility_cache[symbol] = volatility

    def reset_daily_tracking(self):
        """Reset daily tracking (call at start of each day)."""
        self._day_start_value = self.portfolio_value

    def get_stats(self) -> Dict[str, Any]:
        """Get risk manager statistics."""
        return {
            "portfolio_value": self.portfolio_value,
            "peak_value": self._peak_value,
            "current_drawdown_pct": (
                (self._peak_value - self.portfolio_value) / self._peak_value
                if self._peak_value > 0
                else 0
            ),
            "limits": {
                "max_position_pct": self.limits.max_position_pct,
                "max_exposure_pct": self.limits.max_total_exposure_pct,
                "max_daily_loss_pct": self.limits.max_daily_loss_pct,
                "max_drawdown_pct": self.limits.max_drawdown_pct,
            },
            "volatility_estimates": len(self._volatility_cache),
            "returns_history_days": len(self._returns_history),
        }
