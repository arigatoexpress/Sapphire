"""Advanced partial exit strategies for profit maximization and risk management."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from .market_regime import MarketRegime, RegimeMetrics
from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


@dataclass
class ExitLevel:
    """Represents a profit target exit level."""

    percentage: float  # % of position to exit (0-1)
    profit_target: float  # Profit target in points/bps
    trailing_stop: Optional[float] = None  # Trailing stop distance
    time_limit: Optional[int] = None  # Time limit in microseconds
    executed: bool = False
    execution_price: Optional[float] = None
    execution_time: Optional[int] = None


@dataclass
class PositionExitPlan:
    """Complete exit strategy for a position."""

    symbol: str
    entry_price: float
    current_price: float
    position_size: float
    side: str  # 'long' or 'short'

    exit_levels: List[ExitLevel]
    trailing_stop: Optional[float] = None
    emergency_stop: Optional[float] = None

    total_exited: float = 0.0
    total_pnl: float = 0.0
    active: bool = True

    created_time: int = 0
    last_update: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "position_size": self.position_size,
            "side": self.side,
            "exit_levels": [
                {
                    "percentage": level.percentage,
                    "profit_target": level.profit_target,
                    "trailing_stop": level.trailing_stop,
                    "time_limit": level.time_limit,
                    "executed": level.executed,
                    "execution_price": level.execution_price,
                    "execution_time": level.execution_time,
                }
                for level in self.exit_levels
            ],
            "trailing_stop": self.trailing_stop,
            "emergency_stop": self.emergency_stop,
            "total_exited": self.total_exited,
            "total_pnl": self.total_pnl,
            "active": self.active,
            "created_time": self.created_time,
            "last_update": self.last_update,
        }


@dataclass
class ExitSignal:
    """Signal to execute a partial exit."""

    symbol: str
    exit_size: float  # Size to exit
    exit_price: Optional[float] = None  # Target exit price
    reason: str = "profit_target"  # Reason for exit
    confidence: float = 1.0
    timestamp_us: Optional[int] = None

    def __post_init__(self):
        if self.timestamp_us is None:
            self.timestamp_us = get_timestamp_us()


class PartialExitStrategy:
    """
    Advanced partial exit strategy manager.
    Implements multiple profit targets, trailing stops, and adaptive exits.
    """

    def __init__(self):
        # Active position exit plans
        self.active_plans: Dict[str, PositionExitPlan] = {}

        # Historical exit performance
        self.exit_history: Deque[Dict] = Deque(maxlen=5000)

        # Strategy performance tracking
        self.performance_stats: Dict[str, Dict] = {}

        # Default exit configurations
        self.default_exit_levels = [
            ExitLevel(percentage=0.25, profit_target=0.005, trailing_stop=0.002),  # 0.5% target
            ExitLevel(percentage=0.25, profit_target=0.010, trailing_stop=0.005),  # 1.0% target
            ExitLevel(percentage=0.25, profit_target=0.020, trailing_stop=0.010),  # 2.0% target
            ExitLevel(percentage=0.25, profit_target=0.050, trailing_stop=0.025),  # 5.0% target
        ]

        # Risk management parameters
        self.max_holding_time_us = 300_000_000  # 5 minutes default
        self.trailing_stop_activation = 0.01  # Activate trailing stop at 1% profit
        self.emergency_stop_loss = 0.05  # 5% emergency stop loss

        # Adaptive parameters based on market regime
        self.regime_adjustments = {
            MarketRegime.TRENDING_UP: {
                "extend_targets": 1.2,  # Extend profit targets in uptrends
                "reduce_stops": 0.8,  # Tighter stops in uptrends
            },
            MarketRegime.TRENDING_DOWN: {
                "extend_targets": 1.2,  # Extend profit targets in downtrends
                "reduce_stops": 0.8,  # Tighter stops in downtrends
            },
            MarketRegime.VOLATILE: {
                "extend_targets": 0.8,  # Reduce targets in volatility
                "reduce_stops": 1.5,  # Wider stops in volatility
                "faster_exits": True,  # Exit faster in volatile conditions
            },
            MarketRegime.RANGING: {
                "extend_targets": 0.9,  # Slightly reduce targets in ranging
                "reduce_stops": 1.2,  # Slightly wider stops
            },
            MarketRegime.CALM: {
                "extend_targets": 1.1,  # Extend targets in calm markets
                "reduce_stops": 0.9,  # Tighter stops in calm conditions
            },
        }

    def create_exit_plan(
        self,
        symbol: str,
        entry_price: float,
        position_size: float,
        side: str,
        regime: Optional[RegimeMetrics] = None,
        custom_levels: Optional[List[ExitLevel]] = None,
    ) -> PositionExitPlan:
        """
        Create a comprehensive exit plan for a position.
        Adapts strategy based on market regime and position characteristics.
        """

        # Use custom levels or adapt defaults based on regime
        exit_levels = custom_levels or self._adapt_exit_levels_for_regime(
            self.default_exit_levels.copy(), regime
        )

        # Adjust for position size (larger positions may need different scaling)
        exit_levels = self._scale_exit_levels_for_position_size(exit_levels, position_size)

        # Create the exit plan
        plan = PositionExitPlan(
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,  # Will be updated
            position_size=position_size,
            side=side,
            exit_levels=exit_levels,
            trailing_stop=self._calculate_initial_trailing_stop(entry_price, regime),
            emergency_stop=self._calculate_emergency_stop(entry_price, side, regime),
            created_time=get_timestamp_us(),
            last_update=get_timestamp_us(),
        )

        self.active_plans[symbol] = plan
        logger.info(
            f"Created exit plan for {symbol}: {len(exit_levels)} levels, trailing_stop={plan.trailing_stop}"
        )

        return plan

    def update_position_price(self, symbol: str, current_price: float) -> List[ExitSignal]:
        """
        Update position price and check for exit signals.
        Returns list of exit signals to execute.
        """

        if symbol not in self.active_plans:
            return []

        plan = self.active_plans[symbol]
        plan.current_price = current_price
        plan.last_update = get_timestamp_us()

        exit_signals = []

        # Check profit target exits
        target_exits = self._check_profit_targets(plan)
        exit_signals.extend(target_exits)

        # Check trailing stop
        trailing_exit = self._check_trailing_stop(plan)
        if trailing_exit:
            exit_signals.append(trailing_exit)

        # Check emergency stop
        emergency_exit = self._check_emergency_stop(plan)
        if emergency_exit:
            exit_signals.append(emergency_exit)
            # Emergency exit - close entire remaining position
            plan.active = False

        # Check time-based exits
        time_exit = self._check_time_limits(plan)
        if time_exit:
            exit_signals.append(time_exit)

        # Update trailing stop levels
        self._update_trailing_stops(plan)

        return exit_signals

    def execute_exit(self, symbol: str, exit_signal: ExitSignal) -> bool:
        """
        Execute a partial exit and update the position plan.
        Returns True if exit was executed successfully.
        """

        if symbol not in self.active_plans:
            return False

        plan = self.active_plans[symbol]

        # Validate exit signal
        if exit_signal.exit_size > (plan.position_size - plan.total_exited):
            logger.warning(
                f"Exit size {exit_signal.exit_size} exceeds remaining position {plan.position_size - plan.total_exited}"
            )
            return False

        # Calculate P&L for this exit
        exit_pnl = self._calculate_exit_pnl(
            plan, exit_signal.exit_price or plan.current_price, exit_signal.exit_size
        )

        # Update plan
        plan.total_exited += exit_signal.exit_size
        plan.total_pnl += exit_pnl

        # Mark corresponding exit level as executed if applicable
        self._mark_exit_level_executed(plan, exit_signal)

        # Check if position is fully closed
        if plan.total_exited >= plan.position_size * 0.99:  # 99% threshold for rounding
            plan.active = False
            self._finalize_position_exit(plan)

        # Record exit in history
        exit_record = {
            "symbol": symbol,
            "exit_size": exit_signal.exit_size,
            "exit_price": exit_signal.exit_price or plan.current_price,
            "reason": exit_signal.reason,
            "pnl": exit_pnl,
            "remaining_size": plan.position_size - plan.total_exited,
            "timestamp_us": exit_signal.timestamp_us,
        }
        self.exit_history.append(exit_record)

        logger.info(
            f"Executed {exit_signal.reason} exit for {symbol}: size={exit_signal.exit_size:.4f}, pnl={exit_pnl:.2f}"
        )

        return True

    def get_position_status(self, symbol: str) -> Optional[Dict]:
        """Get current status of a position's exit plan."""

        if symbol not in self.active_plans:
            return None

        plan = self.active_plans[symbol]

        # Calculate unrealized P&L
        remaining_size = plan.position_size - plan.total_exited
        if remaining_size > 0:
            current_pnl = self._calculate_exit_pnl(plan, plan.current_price, remaining_size)
        else:
            current_pnl = 0

        return {
            "symbol": symbol,
            "active": plan.active,
            "remaining_size": remaining_size,
            "total_exited": plan.total_exited,
            "realized_pnl": plan.total_pnl,
            "unrealized_pnl": current_pnl,
            "total_pnl": plan.total_pnl + current_pnl,
            "entry_price": plan.entry_price,
            "current_price": plan.current_price,
            "trailing_stop": plan.trailing_stop,
            "emergency_stop": plan.emergency_stop,
            "next_targets": self._get_next_exit_targets(plan),
            "holding_time_us": get_timestamp_us() - plan.created_time,
        }

    def close_position(self, symbol: str, close_price: Optional[float] = None) -> bool:
        """Force close entire remaining position."""

        if symbol not in self.active_plans:
            return False

        plan = self.active_plans[symbol]
        close_price = close_price or plan.current_price

        remaining_size = plan.position_size - plan.total_exited
        if remaining_size <= 0:
            return True

        # Calculate final P&L
        final_pnl = self._calculate_exit_pnl(plan, close_price, remaining_size)
        plan.total_exited = plan.position_size
        plan.total_pnl += final_pnl
        plan.active = False

        # Record final exit
        exit_record = {
            "symbol": symbol,
            "exit_size": remaining_size,
            "exit_price": close_price,
            "reason": "forced_close",
            "pnl": final_pnl,
            "remaining_size": 0,
            "timestamp_us": get_timestamp_us(),
        }
        self.exit_history.append(exit_record)

        self._finalize_position_exit(plan)

        logger.info(f"Force closed position {symbol}: pnl={final_pnl:.2f}")

        return True

    def _adapt_exit_levels_for_regime(
        self, levels: List[ExitLevel], regime: Optional[RegimeMetrics]
    ) -> List[ExitLevel]:
        """Adapt exit levels based on market regime."""

        if not regime:
            return levels

        adjustments = self.regime_adjustments.get(regime.regime, {})

        adapted_levels = []
        for level in levels:
            adapted_level = ExitLevel(
                percentage=level.percentage,
                profit_target=level.profit_target * adjustments.get("extend_targets", 1.0),
                trailing_stop=level.trailing_stop,
                time_limit=level.time_limit,
            )

            # Adjust trailing stops
            if adapted_level.trailing_stop:
                adapted_level.trailing_stop *= adjustments.get("reduce_stops", 1.0)

            # Faster exits in volatile conditions
            if adjustments.get("faster_exits", False) and adapted_level.time_limit:
                adapted_level.time_limit = int(adapted_level.time_limit * 0.7)

            adapted_levels.append(adapted_level)

        return adapted_levels

    def _scale_exit_levels_for_position_size(
        self, levels: List[ExitLevel], position_size: float
    ) -> List[ExitLevel]:
        """Scale exit levels based on position size."""

        # Larger positions might use different scaling
        if position_size > 1000:  # Large position
            # Slightly reduce profit targets for large positions (harder to exit)
            scale_factor = 0.9
        elif position_size < 100:  # Small position
            # Slightly increase profit targets for small positions (easier to exit)
            scale_factor = 1.1
        else:
            scale_factor = 1.0

        scaled_levels = []
        for level in levels:
            scaled_level = ExitLevel(
                percentage=level.percentage,
                profit_target=level.profit_target * scale_factor,
                trailing_stop=level.trailing_stop,
                time_limit=level.time_limit,
            )
            scaled_levels.append(scaled_level)

        return scaled_levels

    def _calculate_initial_trailing_stop(
        self, entry_price: float, regime: Optional[RegimeMetrics]
    ) -> Optional[float]:
        """Calculate initial trailing stop distance."""

        base_stop = abs(entry_price * self.trailing_stop_activation)

        if regime:
            adjustments = self.regime_adjustments.get(regime.regime, {})
            stop_multiplier = adjustments.get("reduce_stops", 1.0)
            base_stop *= stop_multiplier

        return base_stop

    def _calculate_emergency_stop(
        self, entry_price: float, side: str, regime: Optional[RegimeMetrics]
    ) -> Optional[float]:
        """Calculate emergency stop loss level."""

        base_stop = abs(entry_price * self.emergency_stop_loss)

        if regime and regime.regime == MarketRegime.VOLATILE:
            # Wider stops in volatile markets
            base_stop *= 1.5

        # Return stop price (not distance)
        if side == "long":
            return entry_price - base_stop
        else:
            return entry_price + base_stop

    def _check_profit_targets(self, plan: PositionExitPlan) -> List[ExitSignal]:
        """Check if any profit targets have been hit."""

        exit_signals = []
        current_profit = self._calculate_profit_pct(plan)

        for i, level in enumerate(plan.exit_levels):
            if level.executed:
                continue

            if current_profit >= level.profit_target:
                # Calculate exit size
                remaining_size = plan.position_size - plan.total_exited
                exit_size = min(level.percentage * plan.position_size, remaining_size)

                if exit_size > 0:
                    signal = ExitSignal(
                        symbol=plan.symbol,
                        exit_size=exit_size,
                        reason=f"profit_target_{i+1}",
                        confidence=0.9,
                    )
                    exit_signals.append(signal)

        return exit_signals

    def _check_trailing_stop(self, plan: PositionExitPlan) -> Optional[ExitSignal]:
        """Check if trailing stop has been hit."""

        if not plan.trailing_stop:
            return None

        # Calculate current trailing stop price
        if plan.side == "long":
            stop_price = plan.current_price - plan.trailing_stop
            if plan.current_price <= stop_price:
                remaining_size = plan.position_size - plan.total_exited
                return ExitSignal(
                    symbol=plan.symbol,
                    exit_size=remaining_size,
                    exit_price=stop_price,
                    reason="trailing_stop",
                    confidence=0.95,
                )
        else:  # short
            stop_price = plan.current_price + plan.trailing_stop
            if plan.current_price >= stop_price:
                remaining_size = plan.position_size - plan.total_exited
                return ExitSignal(
                    symbol=plan.symbol,
                    exit_size=remaining_size,
                    exit_price=stop_price,
                    reason="trailing_stop",
                    confidence=0.95,
                )

        return None

    def _check_emergency_stop(self, plan: PositionExitPlan) -> Optional[ExitSignal]:
        """Check if emergency stop loss has been hit."""

        if not plan.emergency_stop:
            return None

        if plan.side == "long" and plan.current_price <= plan.emergency_stop:
            remaining_size = plan.position_size - plan.total_exited
            return ExitSignal(
                symbol=plan.symbol,
                exit_size=remaining_size,
                exit_price=plan.emergency_stop,
                reason="emergency_stop",
                confidence=1.0,
            )
        elif plan.side == "short" and plan.current_price >= plan.emergency_stop:
            remaining_size = plan.position_size - plan.total_exited
            return ExitSignal(
                symbol=plan.symbol,
                exit_size=remaining_size,
                exit_price=plan.emergency_stop,
                reason="emergency_stop",
                confidence=1.0,
            )

        return None

    def _check_time_limits(self, plan: PositionExitPlan) -> Optional[ExitSignal]:
        """Check if position has exceeded time limits."""

        holding_time = get_timestamp_us() - plan.created_time

        # Check individual level time limits
        for level in plan.exit_levels:
            if not level.executed and level.time_limit and holding_time >= level.time_limit:
                remaining_size = plan.position_size - plan.total_exited
                exit_size = min(level.percentage * plan.position_size, remaining_size)

                if exit_size > 0:
                    return ExitSignal(
                        symbol=plan.symbol, exit_size=exit_size, reason="time_limit", confidence=0.7
                    )

        # Check overall position time limit
        if holding_time >= self.max_holding_time_us:
            remaining_size = plan.position_size - plan.total_exited
            return ExitSignal(
                symbol=plan.symbol,
                exit_size=remaining_size,
                reason="max_holding_time",
                confidence=0.8,
            )

        return None

    def _update_trailing_stops(self, plan: PositionExitPlan):
        """Update trailing stop levels based on current profit."""

        current_profit = self._calculate_profit_pct(plan)

        # Activate trailing stop if profit threshold reached
        if current_profit >= self.trailing_stop_activation and plan.trailing_stop is None:

            # Set initial trailing stop
            profit_distance = abs(plan.current_price - plan.entry_price)
            plan.trailing_stop = profit_distance * 0.5  # 50% of profit as stop distance

        # Update trailing stop if price moves favorably
        elif plan.trailing_stop is not None:
            if plan.side == "long":
                # For longs, trail below the highest price reached
                new_stop = plan.current_price - plan.trailing_stop
                # Only tighten the stop, don't loosen it
                if plan.emergency_stop and new_stop > plan.emergency_stop:
                    plan.emergency_stop = new_stop
            else:  # short
                new_stop = plan.current_price + plan.trailing_stop
                if plan.emergency_stop and new_stop < plan.emergency_stop:
                    plan.emergency_stop = new_stop

    def _calculate_profit_pct(self, plan: PositionExitPlan) -> float:
        """Calculate current profit as percentage."""
        if plan.side == "long":
            profit = plan.current_price - plan.entry_price
        else:
            profit = plan.entry_price - plan.current_price

        return profit / plan.entry_price

    def _calculate_exit_pnl(
        self, plan: PositionExitPlan, exit_price: float, exit_size: float
    ) -> float:
        """Calculate P&L for an exit."""
        if plan.side == "long":
            pnl_per_unit = exit_price - plan.entry_price
        else:
            pnl_per_unit = plan.entry_price - exit_price

        return pnl_per_unit * exit_size

    def _mark_exit_level_executed(self, plan: PositionExitPlan, exit_signal: ExitSignal):
        """Mark the appropriate exit level as executed."""

        # Find the exit level that corresponds to this signal
        for level in plan.exit_levels:
            if not level.executed:
                # This is a simple approximation - in practice, you'd need more sophisticated matching
                level.executed = True
                level.execution_price = exit_signal.exit_price
                level.execution_time = exit_signal.timestamp_us
                break

    def _get_next_exit_targets(self, plan: PositionExitPlan) -> List[Dict]:
        """Get the next profit targets for the position."""

        targets = []
        current_profit = self._calculate_profit_pct(plan)

        for i, level in enumerate(plan.exit_levels):
            if not level.executed:
                targets.append(
                    {
                        "level": i + 1,
                        "profit_target": level.profit_target,
                        "current_profit": current_profit,
                        "distance_to_target": level.profit_target - current_profit,
                        "exit_percentage": level.percentage,
                    }
                )

        return targets

    def _finalize_position_exit(self, plan: PositionExitPlan):
        """Finalize a completed position exit."""

        # Calculate final statistics
        total_holding_time = plan.last_update - plan.created_time
        final_pnl_pct = plan.total_pnl / (plan.entry_price * plan.position_size)

        # Update performance stats
        symbol_stats = self.performance_stats.setdefault(
            plan.symbol,
            {
                "total_positions": 0,
                "winning_positions": 0,
                "total_pnl": 0.0,
                "avg_holding_time": 0,
                "best_trade": float("-inf"),
                "worst_trade": float("inf"),
            },
        )

        symbol_stats["total_positions"] += 1
        symbol_stats["total_pnl"] += plan.total_pnl

        if plan.total_pnl > 0:
            symbol_stats["winning_positions"] += 1

        symbol_stats["best_trade"] = max(symbol_stats["best_trade"], final_pnl_pct)
        symbol_stats["worst_trade"] = min(symbol_stats["worst_trade"], final_pnl_pct)

        # Update average holding time (exponential moving average)
        alpha = 0.1
        symbol_stats["avg_holding_time"] = (
            alpha * total_holding_time + (1 - alpha) * symbol_stats["avg_holding_time"]
        )

        # Clean up
        if plan.symbol in self.active_plans:
            del self.active_plans[plan.symbol]

    def get_performance_stats(self) -> Dict:
        """Get comprehensive performance statistics."""

        total_positions = sum(stats["total_positions"] for stats in self.performance_stats.values())
        winning_positions = sum(
            stats["winning_positions"] for stats in self.performance_stats.values()
        )
        total_pnl = sum(stats["total_pnl"] for stats in self.performance_stats.values())

        win_rate = winning_positions / total_positions if total_positions > 0 else 0

        return {
            "total_positions": total_positions,
            "winning_positions": winning_positions,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "active_positions": len(self.active_plans),
            "symbol_performance": self.performance_stats,
            "recent_exits": list(self.exit_history)[-10:] if self.exit_history else [],
        }


# Global partial exit strategy instance
_partial_exit_strategy: Optional[PartialExitStrategy] = None


async def get_partial_exit_strategy() -> PartialExitStrategy:
    """Get global partial exit strategy instance."""
    global _partial_exit_strategy
    if _partial_exit_strategy is None:
        _partial_exit_strategy = PartialExitStrategy()
    return _partial_exit_strategy
