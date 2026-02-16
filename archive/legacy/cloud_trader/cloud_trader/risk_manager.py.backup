"""
Risk Manager Module
Implements stop-loss, position sizing, and hedging for Sapphire V2.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Position:
    symbol: str
    side: str  # LONG or SHORT
    size: float
    entry_price: float
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop_pct: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        if self.current_price == 0:
            return 0.0
        diff = self.current_price - self.entry_price
        return diff * self.size if self.side == "LONG" else -diff * self.size

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price


class RiskManager:
    """
    Manages trading risk through position sizing, stop-losses, and hedging.
    """

    def __init__(
        self,
        max_position_pct: float = 0.1,  # Max 10% of portfolio per trade
        max_drawdown_pct: float = 0.15,  # Max 15% drawdown before halt
        default_stop_loss_pct: float = 0.02,  # 2% stop loss
        default_take_profit_pct: float = 0.04,  # 4% take profit (2:1 R/R)
        max_correlation: float = 0.7,  # Max correlation for hedging
    ):
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.default_stop_loss_pct = default_stop_loss_pct
        self.default_take_profit_pct = default_take_profit_pct
        self.max_correlation = max_correlation

        self.positions: Dict[str, Position] = {}
        self.portfolio_value = 0.0
        self.peak_value = 0.0
        self.current_drawdown = 0.0
        self.is_halted = False

    def calculate_position_size(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        volatility: float,
        confidence: float = 0.5,
    ) -> float:
        """
        Calculate dynamic position size using Kelly Criterion + volatility adjustment.
        
        Args:
            symbol: Trading pair
            side: LONG or SHORT
            entry_price: Entry price
            volatility: Recent volatility (ATR %)
            confidence: Signal confidence (0-1)
            
        Returns:
            Position size as fraction of portfolio
        """
        if self.is_halted:
            logger.warning("Risk manager halted, returning 0 size")
            return 0.0

        # Base size from max position
        base_size = self.max_position_pct

        # Kelly Criterion adjustment
        # f* = (bp - q) / b where b=R/R ratio, p=win prob, q=1-p
        win_prob = 0.5 + confidence * 0.2  # Map confidence to win prob
        rr_ratio = self.default_take_profit_pct / self.default_stop_loss_pct
        kelly = (rr_ratio * win_prob - (1 - win_prob)) / rr_ratio
        kelly = max(0, min(kelly, 0.25))  # Cap at 25%

        # Volatility scaling (reduce size in high volatility)
        vol_scalar = 1.0 / (1.0 + volatility * 10)
        vol_scalar = max(0.25, min(vol_scalar, 1.0))

        # Drawdown scaling (reduce size when in drawdown)
        dd_scalar = 1.0 - (self.current_drawdown / self.max_drawdown_pct)
        dd_scalar = max(0.1, min(dd_scalar, 1.0))

        final_size = base_size * kelly * vol_scalar * dd_scalar
        final_size = max(0.01, min(final_size, self.max_position_pct))

        logger.info(
            f"Position size for {symbol}: {final_size:.2%} "
            f"(kelly={kelly:.2f}, vol_scalar={vol_scalar:.2f}, dd_scalar={dd_scalar:.2f})"
        )

        return final_size

    def calculate_stop_loss(
        self, entry_price: float, side: str, volatility: float
    ) -> float:
        """Calculate dynamic stop-loss based on volatility."""
        # ATR-based stop loss (1.5x ATR from entry)
        atr_stop = volatility * 1.5

        # Use larger of default stop or ATR-based
        stop_pct = max(self.default_stop_loss_pct, atr_stop)
        stop_pct = min(stop_pct, 0.05)  # Cap at 5%

        if side == "LONG":
            return entry_price * (1 - stop_pct)
        else:
            return entry_price * (1 + stop_pct)

    def calculate_take_profit(
        self, entry_price: float, side: str, stop_loss: float
    ) -> float:
        """Calculate take-profit for 2:1 risk/reward."""
        risk = abs(entry_price - stop_loss)

        if side == "LONG":
            return entry_price + risk * 2
        else:
            return entry_price - risk * 2

    def add_position(self, position: Position):
        """Add position to tracking."""
        self.positions[position.symbol] = position
        logger.info(f"Added position: {position.symbol} {position.side} {position.size}")

    def update_position(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Update position and check for stop/take-profit triggers.
        
        Returns:
            'STOP_LOSS', 'TAKE_PROFIT', 'TRAILING_STOP', or None
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        pos.current_price = current_price

        # Check stop loss
        if pos.side == "LONG" and current_price <= pos.stop_loss:
            return "STOP_LOSS"
        if pos.side == "SHORT" and current_price >= pos.stop_loss:
            return "STOP_LOSS"

        # Check take profit
        if pos.side == "LONG" and current_price >= pos.take_profit:
            return "TAKE_PROFIT"
        if pos.side == "SHORT" and current_price <= pos.take_profit:
            return "TAKE_PROFIT"

        # Trailing stop update
        if pos.trailing_stop_pct > 0:
            if pos.side == "LONG":
                new_stop = current_price * (1 - pos.trailing_stop_pct)
                if new_stop > pos.stop_loss:
                    pos.stop_loss = new_stop
            else:
                new_stop = current_price * (1 + pos.trailing_stop_pct)
                if new_stop < pos.stop_loss:
                    pos.stop_loss = new_stop

        return None

    def remove_position(self, symbol: str):
        """Remove closed position."""
        self.positions.pop(symbol, None)

    def update_portfolio(self, value: float):
        """Update portfolio value and check drawdown."""
        self.portfolio_value = value

        if value > self.peak_value:
            self.peak_value = value

        if self.peak_value > 0:
            self.current_drawdown = (self.peak_value - value) / self.peak_value

        if self.current_drawdown >= self.max_drawdown_pct:
            logger.warning(f"🚨 Max drawdown reached: {self.current_drawdown:.2%}")
            self.is_halted = True

    def get_risk_level(self) -> RiskLevel:
        """Get current risk level."""
        if self.is_halted:
            return RiskLevel.CRITICAL
        if self.current_drawdown > self.max_drawdown_pct * 0.8:
            return RiskLevel.HIGH
        if self.current_drawdown > self.max_drawdown_pct * 0.5:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def should_hedge(self, symbol: str) -> Optional[str]:
        """
        Determine if hedging is needed.
        
        Returns:
            Hedge symbol or None
        """
        # Simple hedging logic: if too concentrated, suggest inverse
        total_exposure = sum(p.size for p in self.positions.values())

        if total_exposure > self.max_position_pct * 3:
            logger.info("Portfolio over-exposed, hedging recommended")
            # Return a hedge suggestion (e.g., opposite ETF or short)
            return f"{symbol}_HEDGE"

        return None

    def get_status(self) -> Dict:
        """Get risk manager status."""
        return {
            "is_halted": self.is_halted,
            "current_drawdown": self.current_drawdown,
            "risk_level": self.get_risk_level().value,
            "positions": len(self.positions),
            "portfolio_value": self.portfolio_value,
        }
