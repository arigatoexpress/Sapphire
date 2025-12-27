"""Autonomous Agent - Self-Configuring Trading Intelligence

Agents that formulate their own strategies by:
1. Querying DataStore for any indicators they want
2. Formulating trading thesis based on data
3. Learning from trade outcomes
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Thesis:
    """Agent's trading thesis."""

    symbol: str
    signal: str  # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    data_used: List[str] = field(default_factory=list)
    expected_profit: Optional[float] = None


class AutonomousAgent:
    """
    Self-configuring trading agent.

    Agent decides:
    - Which indicators to query
    - How to combine them into a thesis
    - Updates preferences based on outcomes
    """

    def __init__(self, agent_id: str, name: str, data_store, specialization: Optional[str] = None):
        self.id = agent_id
        self.name = name
        self.data_store = data_store
        self.specialization = specialization  # "technical", "sentiment", "hybrid"

        # Strategy configuration (evolves over time)
        self.strategy_config = {
            "preferred_indicators": self._get_default_indicators(),
            "indicator_scores": {},  # Which indicators have worked best
            "confidence_threshold": 0.6,
            "exploration_rate": 0.1,  # % of time to try new indicators
        }

        # Performance tracking
        self.performance_history = []
        self.total_trades = 0
        self.winning_trades = 0

    def _get_default_indicators(self) -> List[str]:
        """Get default indicators based on specialization."""
        if self.specialization == "technical":
            return ["rsi", "macd", "bollinger_bands", "adx"]
        elif self.specialization == "sentiment":
            return ["social_sentiment", "news_sentiment", "rsi", "volatility_state"]
        elif self.specialization == "orderflow":
            return ["bid_pressure", "spread", "volume", "obv", "cci"]
        else:  # hybrid
            return ["rsi", "bid_pressure", "volume", "stochastic"]

    async def analyze(self, symbol: str) -> Thesis:
        """
        Analyze symbol and formulate trading thesis.

        Agent autonomously decides what data to request.
        """
        logger.info(f"{self.name} analyzing {symbol}")

        # 1. Gather data
        indicators = await self._gather_data(symbol)

        # 2. Formulate thesis
        thesis = self._formulate_thesis(symbol, indicators)

        # 3. Track what data was used
        thesis.data_used = list(indicators.keys())

        logger.info(
            f"{self.name} thesis for {symbol}: {thesis.signal} "
            f"(confidence={thesis.confidence:.2f}, reason={thesis.reasoning})"
        )

        return thesis

    async def _gather_data(self, symbol: str) -> Dict[str, Any]:
        """
        Agent decides what data to fetch.

        This is where autonomous behavior happens:
        - Prefers indicators that have worked in the past
        - Occasionally explores new indicators
        """
        data = {}

        # Always fetch core indicators
        core_indicators = ["price", "volume"]
        for indicator in core_indicators:
            try:
                value = await self.data_store.get(indicator, symbol)
                if value is not None:
                    data[indicator] = value
            except Exception as e:
                logger.debug(f"Failed to fetch {indicator}: {e}")

        # Fetch preferred indicators
        for indicator in self.strategy_config["preferred_indicators"]:
            try:
                value = await self.data_store.get(indicator, symbol)
                if value is not None:
                    data[indicator] = value
            except Exception as e:
                logger.debug(f"Failed to fetch {indicator}: {e}")

        # Exploration: try new indicators occasionally
        if random.random() < self.strategy_config["exploration_rate"]:
            available = self.data_store.get_available_indicators()
            unused = [i for i in available if i not in data]
            if unused:
                new_indicator = random.choice(unused)
                try:
                    value = await self.data_store.get(new_indicator, symbol)
                    if value is not None:
                        data[new_indicator] = value
                        logger.info(f"{self.name} exploring new indicator: {new_indicator}")
                except Exception as e:
                    logger.debug(f"Failed to explore {new_indicator}: {e}")

        return data

    def _formulate_thesis(self, symbol: str, indicators: Dict[str, Any]) -> Thesis:
        """
        Formulate trading thesis based on available data.

        Agent combines indicators using its own logic.
        """
        bullish_signals = 0
        bearish_signals = 0
        reasons = []

        # Analyze RSI
        if "rsi" in indicators:
            rsi = indicators["rsi"]
            if rsi < 30:
                bullish_signals += 2  # Strong signal
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi < 40:
                bullish_signals += 1  # Moderate signal
                reasons.append(f"RSI low ({rsi:.1f})")
            elif rsi > 70:
                bearish_signals += 2
                reasons.append(f"RSI overbought ({rsi:.1f})")
            elif rsi > 60:
                bearish_signals += 1
                reasons.append(f"RSI high ({rsi:.1f})")

        # Analyze MACD (if available)
        if "macd" in indicators:
            macd = indicators["macd"]
            if isinstance(macd, dict):
                trend = macd.get("trend", "NEUTRAL")
                if trend == "BULLISH":
                    bullish_signals += 1
                    reasons.append("MACD bullish")
                elif trend == "BEARISH":
                    bearish_signals += 1
                    reasons.append("MACD bearish")

        # Analyze Order Flow
        if "bid_pressure" in indicators:
            bid_pressure = indicators["bid_pressure"]
            if bid_pressure > 0.6:
                bullish_signals += 1
                reasons.append(f"Strong bid pressure ({bid_pressure:.2f})")
            elif bid_pressure < 0.4:
                bearish_signals += 1
                reasons.append(f"Weak bid pressure ({bid_pressure:.2f})")

        # Analyze Sentiment (if available)
        if "social_sentiment" in indicators:
            sentiment = indicators["social_sentiment"]
            if sentiment > 0.7:
                bullish_signals += 1
                reasons.append("Positive sentiment")
            elif sentiment < 0.3:
                bearish_signals += 1
                reasons.append("Negative sentiment")

        # Make decision
        total_signals = bullish_signals + bearish_signals

        if total_signals == 0:
            # No clear signals
            return Thesis(
                symbol=symbol, signal="HOLD", confidence=0.0, reasoning="Insufficient data"
            )

        if bullish_signals > bearish_signals:
            confidence = bullish_signals / total_signals
            return Thesis(
                symbol=symbol, signal="BUY", confidence=confidence, reasoning=" + ".join(reasons)
            )

        elif bearish_signals > bullish_signals:
            confidence = bearish_signals / total_signals
            return Thesis(
                symbol=symbol, signal="SELL", confidence=confidence, reasoning=" + ".join(reasons)
            )

        else:
            # Tied signals
            return Thesis(
                symbol=symbol,
                signal="HOLD",
                confidence=0.5,
                reasoning="Mixed signals: " + " vs ".join(reasons),
            )

    def learn_from_trade(self, thesis: Thesis, pnl_pct: float):
        """
        Update strategy based on trade outcome.

        Args:
            thesis: The thesis that led to the trade
            pnl_pct: PnL as percentage (e.g., 0.05 = 5% profit)
        """
        self.total_trades += 1
        if pnl_pct > 0:
            self.winning_trades += 1

        # Record outcome
        self.performance_history.append(
            {"thesis": thesis, "pnl_pct": pnl_pct, "timestamp": time.time()}
        )

        # Limit history size
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

        # Update indicator scores
        for indicator in thesis.data_used:
            current_score = self.strategy_config.get("indicator_scores", {}).get(indicator, 0.5)

            if pnl_pct > 0:
                # Winning trade: boost indicator score
                new_score = min(1.0, current_score + 0.1)
            else:
                # Losing trade: decrease indicator score
                new_score = max(0.0, current_score - 0.05)

            self.strategy_config.setdefault("indicator_scores", {})[indicator] = new_score

        # Update preferred indicators (top 5 by score)
        scores = self.strategy_config.get("indicator_scores", {})
        if scores:
            top_indicators = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
            self.strategy_config["preferred_indicators"] = [ind for ind, _ in top_indicators]

            logger.info(
                f"{self.name} updated preferences: "
                f"{self.strategy_config['preferred_indicators']}"
            )

    def get_win_rate(self) -> float:
        """Get current win rate."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    def get_strategy_summary(self) -> Dict[str, Any]:
        """Get summary of agent's current strategy."""
        return {
            "id": self.id,
            "name": self.name,
            "specialization": self.specialization,
            "preferred_indicators": self.strategy_config["preferred_indicators"],
            "indicator_scores": self.strategy_config.get("indicator_scores", {}),
            "total_trades": self.total_trades,
            "win_rate": self.get_win_rate(),
            "confidence_threshold": self.strategy_config["confidence_threshold"],
        }
