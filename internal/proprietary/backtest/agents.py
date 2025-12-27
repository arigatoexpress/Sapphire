"""Backtest-compatible agent logic for historical simulation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..strategies import StrategySelector, StrategySignal
from ..strategy import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class BacktestAgentDecision:
    """Agent decision for backtesting."""

    timestamp: datetime
    symbol: str
    agent_id: str
    agent_type: str
    signal: StrategySignal
    confidence: float
    position_size_pct: float
    take_profit_pct: float
    stop_loss_pct: float


class BacktestAgent:
    """Backtest-compatible agent that mimics live agent behavior."""

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        config: Dict[str, Any],
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.config = config
        self.strategy_selector = StrategySelector(enable_rl=False)
        self._decisions: List[BacktestAgentDecision] = []

    async def evaluate(
        self,
        symbol: str,
        timestamp: datetime,
        market_snapshot: MarketSnapshot,
        historical_data: pd.DataFrame,
    ) -> Optional[BacktestAgentDecision]:
        """Evaluate market conditions and generate trading decision."""
        try:
            # Get strategy signal (similar to live agent)
            signal = await self.strategy_selector.select_best_strategy(
                symbol=symbol,
                snapshot=market_snapshot,
                historical_data=historical_data,
            )

            if signal.direction == "HOLD" or signal.confidence < 0.6:
                return None

            # Calculate position sizing based on agent config
            position_size_pct = self._calculate_position_size(
                signal.confidence,
                market_snapshot.change_24h,
            )

            # Calculate TP/SL based on agent config
            take_profit_pct = self.config.get("profit_target", 0.01)
            stop_loss_pct = self.config.get("stop_loss", 0.005)

            decision = BacktestAgentDecision(
                timestamp=timestamp,
                symbol=symbol,
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                signal=signal,
                confidence=signal.confidence,
                position_size_pct=position_size_pct,
                take_profit_pct=take_profit_pct,
                stop_loss_pct=stop_loss_pct,
            )

            self._decisions.append(decision)
            return decision

        except Exception as e:
            logger.error(f"Agent {self.agent_id} evaluation error: {e}")
            return None

    def _calculate_position_size(
        self,
        confidence: float,
        volatility: float,
    ) -> float:
        """Calculate position size as percentage of capital."""
        # Base size from config
        base_size = self.config.get("max_position_size_pct", 0.08)
        min_size = self.config.get("min_position_size_pct", 0.005)

        # Adjust based on confidence
        confidence_multiplier = min(confidence / 0.7, 1.5)  # Cap at 1.5x

        # Adjust based on volatility (inverse relationship)
        volatility_multiplier = max(0.5, 1.0 - abs(volatility) / 0.1)  # Reduce size in high vol

        size = base_size * confidence_multiplier * volatility_multiplier

        # Clamp to min/max
        size = max(min_size, min(size, base_size))

        return size

    def get_decisions(self) -> List[BacktestAgentDecision]:
        """Get all decisions made by this agent during backtest."""
        return self._decisions.copy()

    def reset(self) -> None:
        """Reset agent state for new backtest run."""
        self._decisions.clear()


def create_backtest_agent(
    agent_id: str,
    agent_type: str,
    agent_config: Dict[str, Any],
) -> BacktestAgent:
    """Factory function to create backtest-compatible agent."""
    return BacktestAgent(
        agent_id=agent_id,
        agent_type=agent_type,
        config=agent_config,
    )
