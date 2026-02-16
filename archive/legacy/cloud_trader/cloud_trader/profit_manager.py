"""
Active Profit Management System
Implements trailing stops, partial profit-taking, and breakeven protection.

This solves the "profit erosion" problem identified in the performance analysis,
where winning positions often reverse and hit stop-loss (30-50% profit loss).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProfitTarget:
    """Represents a profit-taking level."""

    profit_percent: float  # e.g., 0.05 for 5%
    size_to_close: float  # e.g., 0.5 for 50% of position
    triggered: bool = False


@dataclass
class PositionState:
    """Tracks position state for profit management."""

    symbol: str
    entry_price: float
    current_price: float
    size: float
    side: str  # "LONG" or "SHORT"
    unrealized_pnl: float
    unrealized_pnl_percent: float
    highest_pnl_percent: float = 0.0
    trailing_stop_activated: bool = False
    trailing_stop_price: Optional[float] = None
    breakeven_moved: bool = False
    profit_targets: list[ProfitTarget] = None

    def __post_init__(self):
        if self.profit_targets is None:
            # Default profit targets: 25% at 5%, 25% at 10%, 50% at 15%
            self.profit_targets = [
                ProfitTarget(profit_percent=0.05, size_to_close=0.25),  # Take 25% at 5% profit
                ProfitTarget(profit_percent=0.10, size_to_close=0.25),  # Take 25% at 10% profit
                ProfitTarget(profit_percent=0.15, size_to_close=0.50),  # Take 50% at 15% profit
            ]


class ActiveProfitManager:
    """
    Manages open positions to maximize profit retention.

    Features:
    1. Trailing stops - Lock in profits as position moves in our favor
    2. Partial profit-taking - Take profits at key levels
    3. Breakeven protection - Move stop to breakeven after initial profit
    4. Anti-stubborn entry - Tracks recent losses to prevent revenge trading

    Target: +20-30% profit retention vs no active management
    """

    def __init__(self):
        self.position_states: Dict[str, PositionState] = {}
        self.recent_losses: list[dict] = []  # Track recent losses to prevent stubborn re-entry
        self.max_recent_losses = 3  # Max losses before cooling off
        self.cooldown_period = 300  # 5 minutes cooldown after max losses
        self.last_loss_time: Optional[datetime] = None

        logger.info("✅ ActiveProfitManager initialized")

    def update_position_state(
        self, symbol: str, entry_price: float, current_price: float, size: float, side: str
    ) -> PositionState:
        """Update or create position state."""
        # Calculate PnL
        if side == "LONG":
            unrealized_pnl = (current_price - entry_price) * size
            unrealized_pnl_percent = (current_price - entry_price) / entry_price
        else:  # SHORT
            unrealized_pnl = (entry_price - current_price) * size
            unrealized_pnl_percent = (entry_price - current_price) / entry_price

        # Create or update state
        if symbol not in self.position_states:
            state = PositionState(
                symbol=symbol,
                entry_price=entry_price,
                current_price=current_price,
                size=size,
                side=side,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl_percent,
                highest_pnl_percent=unrealized_pnl_percent,
            )
            self.position_states[symbol] = state
        else:
            state = self.position_states[symbol]
            state.current_price = current_price
            state.size = size
            state.unrealized_pnl = unrealized_pnl
            state.unrealized_pnl_percent = unrealized_pnl_percent

            # Track highest PnL for trailing stop
            if unrealized_pnl_percent > state.highest_pnl_percent:
                state.highest_pnl_percent = unrealized_pnl_percent

        return state

    def check_profit_targets(self, state: PositionState) -> Optional[dict]:
        """
        Check if any profit targets should be triggered.

        Returns:
            dict with action details if a target is hit, None otherwise
        """
        for target in state.profit_targets:
            if target.triggered:
                continue

            if state.unrealized_pnl_percent >= target.profit_percent:
                target.triggered = True

                close_size = state.size * target.size_to_close

                logger.info(
                    f"🎯 Profit Target Hit: {state.symbol} @ {target.profit_percent*100:.1f}% profit, "
                    f"closing {target.size_to_close*100:.0f}% of position"
                )

                return {
                    "action": "partial_close",
                    "symbol": state.symbol,
                    "size": close_size,
                    "reason": f"Profit target {target.profit_percent*100:.1f}% reached",
                    "pnl_percent": state.unrealized_pnl_percent,
                }

        return None

    def check_trailing_stop(self, state: PositionState) -> Optional[dict]:
        """
        Check if trailing stop should be activated or triggered.

        Trailing stop logic:
        1. Activate after 3% profit
        2. Trail 2% below highest point reached
        3. Close entire position if triggered

        Returns:
            dict with action details if stop is hit, None otherwise
        """
        # Activate trailing stop after 3% profit
        if not state.trailing_stop_activated and state.unrealized_pnl_percent > 0.03:
            state.trailing_stop_activated = True
            logger.info(f"🔒 Trailing stop activated for {state.symbol} @ 3% profit")

        # Update trailing stop price
        if state.trailing_stop_activated:
            trail_percent = 0.02  # Trail 2% behind

            if state.side == "LONG":
                # For longs, trail 2% below highest price
                highest_price = state.entry_price * (1 + state.highest_pnl_percent)
                new_stop = highest_price * (1 - trail_percent)

                if state.trailing_stop_price is None or new_stop > state.trailing_stop_price:
                    state.trailing_stop_price = new_stop
                    logger.debug(f"Updated trailing stop for {state.symbol}: ${new_stop:.2f}")

                # Check if current price hit trailing stop
                if state.current_price <= state.trailing_stop_price:
                    logger.info(
                        f"🛑 Trailing Stop Hit: {state.symbol} @ ${state.current_price:.2f} "
                        f"(stop: ${state.trailing_stop_price:.2f})"
                    )
                    return {
                        "action": "close_all",
                        "symbol": state.symbol,
                        "reason": f"Trailing stop hit (locked in {state.unrealized_pnl_percent*100:.1f}% profit)",
                        "pnl_percent": state.unrealized_pnl_percent,
                    }

            else:  # SHORT
                # For shorts, trail 2% above lowest price
                lowest_price = state.entry_price * (1 - state.highest_pnl_percent)
                new_stop = lowest_price * (1 + trail_percent)

                if state.trailing_stop_price is None or new_stop < state.trailing_stop_price:
                    state.trailing_stop_price = new_stop

                # Check if current price hit trailing stop
                if state.current_price >= state.trailing_stop_price:
                    return {
                        "action": "close_all",
                        "symbol": state.symbol,
                        "reason": f"Trailing stop hit (locked in {state.unrealized_pnl_percent*100:.1f}% profit)",
                        "pnl_percent": state.unrealized_pnl_percent,
                    }

        return None

    def check_breakeven_move(self, state: PositionState) -> Optional[dict]:
        """
        Move stop to breakeven after 5% profit.

        This protects capital and ensures we don't turn winners into losers.
        """
        if state.breakeven_moved:
            return None

        # Move to breakeven after 5% profit
        if state.unrealized_pnl_percent > 0.05:
            state.breakeven_moved = True

            logger.info(
                f"🔐 Breakeven Protection: {state.symbol} stop moved to entry ${state.entry_price:.2f} "
                f"after {state.unrealized_pnl_percent*100:.1f}% profit"
            )

            return {
                "action": "update_stop",
                "symbol": state.symbol,
                "new_stop": state.entry_price,
                "reason": "Breakeven protection after 5% profit",
            }

        return None

    def should_allow_new_entry(self, symbol: str) -> tuple[bool, str]:
        """
        Check if new entry should be allowed (anti-stubborn entry logic).

        Prevents:
        - Revenge trading after consecutive losses
        - Over-trading the same symbol

        Returns:
            (allowed: bool, reason: str)
        """
        # Check recent losses for this symbol
        symbol_losses = [l for l in self.recent_losses if l["symbol"] == symbol]

        if len(symbol_losses) >= self.max_recent_losses:
            # Check if still in cooldown
            if self.last_loss_time:
                time_since_loss = (datetime.now(timezone.utc) - self.last_loss_time).total_seconds()

                if time_since_loss < self.cooldown_period:
                    remaining = self.cooldown_period - time_since_loss
                    return (
                        False,
                        f"Cooldown active: {len(symbol_losses)} recent losses on {symbol}, "
                        f"wait {remaining:.0f}s before re-entry",
                    )

        return (True, "Entry allowed")

    def record_loss(self, symbol: str, pnl_percent: float) -> None:
        """Record a losing trade to track stubborn entry prevention."""
        loss_record = {
            "symbol": symbol,
            "pnl_percent": pnl_percent,
            "timestamp": datetime.now(timezone.utc),
        }

        self.recent_losses.append(loss_record)
        self.last_loss_time = datetime.now(timezone.utc)

        # Keep only last 10 losses
        if len(self.recent_losses) > 10:
            self.recent_losses = self.recent_losses[-10:]

        logger.warning(
            f"📉 Loss recorded: {symbol} {pnl_percent*100:.2f}% "
            f"({len([l for l in self.recent_losses if l['symbol'] == symbol])} recent losses)"
        )

    def clear_position_state(self, symbol: str) -> None:
        """Clear position state after closing."""
        if symbol in self.position_states:
            del self.position_states[symbol]
            logger.debug(f"Cleared position state for {symbol}")

    async def monitor_position(
        self, symbol: str, entry_price: float, current_price: float, size: float, side: str
    ) -> list[dict]:
        """
        Monitor a single position and return list of actions to take.

        Returns:
            List of action dicts, e.g.:
            [
                {"action": "partial_close", "size": 0.5, "reason": "5% profit target"},
                {"action": "update_stop", "new_stop": 100.0, "reason": "breakeven"}
            ]
        """
        actions = []

        # Update state
        state = self.update_position_state(symbol, entry_price, current_price, size, side)

        # Check profit targets (highest priority)
        profit_action = self.check_profit_targets(state)
        if profit_action:
            actions.append(profit_action)

        # Check trailing stop
        trailing_action = self.check_trailing_stop(state)
        if trailing_action:
            actions.append(trailing_action)

        # Check breakeven move
        breakeven_action = self.check_breakeven_move(state)
        if breakeven_action:
            actions.append(breakeven_action)

        return actions

    def get_statistics(self) -> dict:
        """Get profit management statistics."""
        return {
            "active_positions": len(self.position_states),
            "trailing_stops_active": sum(
                1 for s in self.position_states.values() if s.trailing_stop_activated
            ),
            "breakeven_protected": sum(
                1 for s in self.position_states.values() if s.breakeven_moved
            ),
            "recent_losses": len(self.recent_losses),
            "cooldown_active": (
                len(self.recent_losses) >= self.max_recent_losses
                and self.last_loss_time
                and (datetime.now(timezone.utc) - self.last_loss_time).total_seconds()
                < self.cooldown_period
            ),
        }


# Global singleton
_profit_manager: Optional[ActiveProfitManager] = None


def get_profit_manager() -> ActiveProfitManager:
    """Get or create the global profit manager instance."""
    global _profit_manager
    if _profit_manager is None:
        _profit_manager = ActiveProfitManager()
    return _profit_manager
