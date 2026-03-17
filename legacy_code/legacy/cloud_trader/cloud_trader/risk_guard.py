"""
Risk Guard - Global Risk Protection Module

Centralized risk management that enforces hard limits across ALL trades.
No position-specific exceptions - these rules apply universally.

Key Features:
- $50 max loss per trade (hard cap)
- Volatility-scaled position sizing
- Leverage capped at 10x
- Daily loss limit protection
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL RISK LIMITS - NEVER EXCEEDED
# ═══════════════════════════════════════════════════════════════════════════

MAX_LOSS_PER_TRADE_USD = 50.0  # Hard cap: never lose more than $50 per trade
MAX_LEVERAGE = 10.0  # Hard cap: never exceed 10x leverage
MAX_POSITION_PCT = 0.15  # Max 15% of portfolio per position
MAX_DAILY_LOSS_PCT = 0.05  # Stop trading after 5% daily loss
MIN_POSITION_SIZE_USD = 10.0  # Minimum viable trade size


@dataclass
class RiskCheckResult:
    """Result of a risk check."""

    approved: bool
    adjusted_size: float  # Position size after adjustments
    adjusted_leverage: float  # Leverage after adjustments
    max_loss_usd: float  # Maximum possible loss
    reason: str  # Explanation


class RiskGuard:
    """
    Global risk protection enforcer.

    All trades MUST pass through this guard. No exceptions.
    """

    def __init__(
        self,
        max_loss_per_trade: float = MAX_LOSS_PER_TRADE_USD,
        max_leverage: float = MAX_LEVERAGE,
        max_position_pct: float = MAX_POSITION_PCT,
        max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT,
    ):
        self.max_loss_per_trade = max_loss_per_trade
        self.max_leverage = max_leverage
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct

        # Track daily losses
        self._daily_pnl: float = 0.0
        self._daily_reset_timestamp: int = 0

        # Trading halt state
        self._trading_halted: bool = False
        self._halt_reason: Optional[str] = None

    def check_trade(
        self,
        portfolio_balance: float,
        proposed_notional: float,
        proposed_leverage: float,
        stop_loss_pct: float,
        entry_price: float,
        symbol: str,
        atr_pct: float = 0.02,  # ATR as % of price (volatility)
    ) -> RiskCheckResult:
        """
        Check if a trade passes all risk limits. Adjust if needed.

        Args:
            portfolio_balance: Current portfolio value
            proposed_notional: Proposed trade size in USD
            proposed_leverage: Proposed leverage
            stop_loss_pct: Stop loss distance as percentage (e.g., 0.02 = 2%)
            entry_price: Entry price of the trade
            symbol: Trading pair
            atr_pct: ATR as percentage of price (for volatility scaling)

        Returns:
            RiskCheckResult with approval and any adjustments
        """
        reasons = []

        # ═══════════════════════════════════════════════════════════════
        # HARD LIMIT 1: Leverage Cap
        # ═══════════════════════════════════════════════════════════════
        adjusted_leverage = min(proposed_leverage, self.max_leverage)
        if adjusted_leverage < proposed_leverage:
            reasons.append(f"Leverage capped: {proposed_leverage:.1f}x → {adjusted_leverage:.1f}x")

        # ═══════════════════════════════════════════════════════════════
        # HARD LIMIT 2: Max Position Size (% of portfolio)
        # ═══════════════════════════════════════════════════════════════
        max_notional_pct = portfolio_balance * self.max_position_pct
        adjusted_notional = min(proposed_notional, max_notional_pct)
        if adjusted_notional < proposed_notional:
            reasons.append(
                f"Position capped: ${proposed_notional:.0f} → ${adjusted_notional:.0f} (15% limit)"
            )

        # ═══════════════════════════════════════════════════════════════
        # HARD LIMIT 3: Max Loss Per Trade ($50 cap)
        # ═══════════════════════════════════════════════════════════════
        # Calculate max loss at stop-loss with leverage
        potential_loss = adjusted_notional * stop_loss_pct * adjusted_leverage

        if potential_loss > self.max_loss_per_trade:
            # Reduce position size to cap loss at $50
            # loss = notional * sl_pct * leverage
            # notional = loss / (sl_pct * leverage)
            safe_notional = self.max_loss_per_trade / (stop_loss_pct * adjusted_leverage)
            safe_notional = max(MIN_POSITION_SIZE_USD, safe_notional)  # Ensure minimum

            if safe_notional < adjusted_notional:
                adjusted_notional = safe_notional
                potential_loss = adjusted_notional * stop_loss_pct * adjusted_leverage
                reasons.append(f"Size reduced for $50 loss cap: ${adjusted_notional:.0f}")

        # ═══════════════════════════════════════════════════════════════
        # VOLATILITY ADJUSTMENT: Reduce size in high-vol markets
        # ═══════════════════════════════════════════════════════════════
        volatility_multiplier = 1.0
        if atr_pct > 0.04:  # Very high volatility (>4%)
            volatility_multiplier = 0.5
            reasons.append(f"High volatility ({atr_pct:.1%}): Size halved")
        elif atr_pct > 0.025:  # High volatility (>2.5%)
            volatility_multiplier = 0.7
            reasons.append(f"Elevated volatility ({atr_pct:.1%}): Size reduced 30%")

        adjusted_notional *= volatility_multiplier

        # ═══════════════════════════════════════════════════════════════
        # DAILY LOSS CHECK
        # ═══════════════════════════════════════════════════════════════
        daily_loss_limit = portfolio_balance * self.max_daily_loss_pct
        if self._daily_pnl < -daily_loss_limit:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0,
                adjusted_leverage=0,
                max_loss_usd=0,
                reason=f"❌ Daily loss limit reached: ${abs(self._daily_pnl):.2f}",
            )

        # ═══════════════════════════════════════════════════════════════
        # MINIMUM SIZE CHECK
        # ═══════════════════════════════════════════════════════════════
        if adjusted_notional < MIN_POSITION_SIZE_USD:
            return RiskCheckResult(
                approved=False,
                adjusted_size=0,
                adjusted_leverage=0,
                max_loss_usd=0,
                reason=f"❌ Position too small: ${adjusted_notional:.2f} < ${MIN_POSITION_SIZE_USD}",
            )

        # Recalculate final max loss
        final_max_loss = adjusted_notional * stop_loss_pct * adjusted_leverage

        # Build approval reason
        if reasons:
            reason = "✅ Approved with adjustments: " + " | ".join(reasons)
        else:
            reason = "✅ Approved: All risk checks passed"

        logger.info(
            f"🛡️ RiskGuard {symbol}: Notional=${adjusted_notional:.0f}, "
            f"Lev={adjusted_leverage:.1f}x, MaxLoss=${final_max_loss:.2f}"
        )

        return RiskCheckResult(
            approved=True,
            adjusted_size=adjusted_notional,
            adjusted_leverage=adjusted_leverage,
            max_loss_usd=final_max_loss,
            reason=reason,
        )

    def record_trade_result(self, pnl: float) -> bool:
        """
        Record a trade result for daily loss tracking.

        Returns:
            True if trading is still allowed, False if daily limit hit.
        """
        self._daily_pnl += pnl

        if pnl < 0:
            logger.warning(f"📉 Trade loss: ${pnl:.2f} | Daily PnL: ${self._daily_pnl:.2f}")

        # Check if we've hit daily limit
        if self._trading_halted:
            return False

        # Check limit (need portfolio balance for percentage calc)
        # For now, use absolute value check; in production, pass portfolio balance
        if self._daily_pnl < -250:  # Absolute fallback: -$250 daily max
            self._trading_halted = True
            self._halt_reason = f"Daily loss limit reached: ${abs(self._daily_pnl):.2f}"
            logger.critical(f"🛑 TRADING HALTED: {self._halt_reason}")
            return False

        return True

    def check_daily_limit(self, portfolio_balance: float) -> bool:
        """
        Check if daily loss limit has been reached.

        Returns:
            True if trading is allowed, False if halted.
        """
        if self._trading_halted:
            return False

        daily_loss_limit = portfolio_balance * self.max_daily_loss_pct
        if self._daily_pnl < -daily_loss_limit:
            self._trading_halted = True
            self._halt_reason = f"Daily loss limit ({self.max_daily_loss_pct:.0%}) reached: ${abs(self._daily_pnl):.2f}"
            logger.critical(f"🛑 TRADING HALTED: {self._halt_reason}")
            return False

        return True

    @property
    def is_trading_halted(self) -> bool:
        """Check if trading is currently halted."""
        return self._trading_halted

    @property
    def halt_reason(self) -> Optional[str]:
        """Get the reason trading was halted."""
        return self._halt_reason if self._trading_halted else None

    def reset_daily_pnl(self):
        """Reset daily PnL and clear halt status (call at start of each trading day)."""
        self._daily_pnl = 0.0
        self._trading_halted = False
        self._halt_reason = None
        logger.info("🔄 Daily PnL reset - Trading resumed")

    def get_max_position_for_symbol(
        self,
        portfolio_balance: float,
        stop_loss_pct: float,
        leverage: float,
    ) -> float:
        """
        Calculate the maximum position size allowed for given parameters.

        Ensures max loss never exceeds $50.
        """
        # Cap leverage
        safe_leverage = min(leverage, self.max_leverage)

        # Calculate max notional that keeps loss under $50
        # loss = notional * sl_pct * leverage
        # notional = loss / (sl_pct * leverage)
        max_notional = self.max_loss_per_trade / (stop_loss_pct * safe_leverage)

        # Also cap at portfolio percentage
        max_by_portfolio = portfolio_balance * self.max_position_pct

        return min(max_notional, max_by_portfolio)


# Global instance
_risk_guard: Optional[RiskGuard] = None


def get_risk_guard() -> RiskGuard:
    """Get or create the global RiskGuard instance."""
    global _risk_guard
    if _risk_guard is None:
        _risk_guard = RiskGuard()
        logger.info("🛡️ RiskGuard initialized: Max loss $50, Max leverage 10x")
    return _risk_guard
