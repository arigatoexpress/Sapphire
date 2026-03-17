"""
Adaptive strategy routing based on market regime detection.
Dynamically selects the optimal trading strategy for current market conditions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import pandas as pd

from .logger import get_logger
from .strategies import (
    ArbitrageStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    StrategySignal,
    TradingStrategy,
)
from .strategy import MarketSnapshot

logger = get_logger(__name__)


class MarketRegimeType(Enum):
    """Market regime classifications."""

    BULL_TRENDING = "BULL_TRENDING"
    BEAR_TRENDING = "BEAR_TRENDING"
    CRAB_RANGING = "CRAB_RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


@dataclass
class RegimeDetectionResult:
    """Result from market regime detection."""

    regime: MarketRegimeType
    confidence: float  # 0.0 to 1.0
    volatility: float
    trend_strength: float
    reasoning: str


class StrategyRouter:
    """
    Intelligently routes to the best strategy based on market conditions.

    This is the solution to the "single-strategy anti-pattern" identified in the
    performance analysis. Instead of only running Mean Reversion, we now:
    1. Detect market regime (trending vs ranging vs volatile)
    2. Select the strategy optimized for that regime
    3. Execute with regime-appropriate parameters

    Target: +40-60% alpha capture by matching strategy to market conditions.
    """

    def __init__(self):
        # Initialize all available strategies
        self.strategies: Dict[str, TradingStrategy] = {
            "momentum": MomentumStrategy(threshold=0.15),  # Lower threshold for more sensitivity
            "mean_reversion": MeanReversionStrategy(bb_period=20, bb_std=2.0),
            "arbitrage": ArbitrageStrategy(min_spread=0.002),
        }

        # Performance tracking per strategy per regime
        self.strategy_performance: Dict[tuple, Dict[str, float]] = {}

        logger.info("✅ StrategyRouter initialized with %d strategies", len(self.strategies))

    async def route_and_evaluate(
        self,
        symbol: str,
        market_data: MarketSnapshot,
        historical_data: Optional[pd.DataFrame] = None,
        current_regime: Optional[str] = None,  # Can be passed from overarching regime detector
    ) -> StrategySignal:
        """
        Main entry point: detect regime and select optimal strategy.

        Args:
            symbol: Trading pair symbol
            market_data: Current market snapshot
            historical_data: Historical candle data
            current_regime: Optional pre-detected regime (from TradingService)

        Returns:
            StrategySignal from the best-suited strategy
        """
        # Step 1: Detect market regime
        regime_result = await self._detect_regime(market_data, historical_data, current_regime)

        logger.info(
            f"📊 Regime for {symbol}: {regime_result.regime.value} "
            f"(confidence: {regime_result.confidence:.2f}, volatility: {regime_result.volatility:.2f})"
        )

        # Step 2: Select strategy based on regime
        strategy = self._select_strategy_for_regime(regime_result)

        # Step 3: Evaluate using selected strategy
        signal = await strategy.evaluate(symbol, market_data, historical_data)

        # Enhance signal with regime context
        signal.metadata["selected_strategy"] = strategy.name
        signal.metadata["market_regime"] = regime_result.regime.value
        signal.metadata["regime_confidence"] = regime_result.confidence
        signal.metadata["routing_reasoning"] = regime_result.reasoning

        # Adjust confidence based on regime alignment
        # If we're very confident about the regime, boost signal confidence
        if regime_result.confidence > 0.75:
            signal.confidence *= 1.15  # 15% boost for high regime confidence
            signal.metadata["confidence_boosted"] = True

        logger.info(
            f"✅ {symbol}: Selected '{strategy.name}' → {signal.direction} "
            f"(confidence: {signal.confidence:.2f})"
        )

        return signal

    async def _detect_regime(
        self,
        market_data: MarketSnapshot,
        historical_data: Optional[pd.DataFrame],
        current_regime: Optional[str] = None,
    ) -> RegimeDetectionResult:
        """
        Detect market regime using multi-factor analysis.

        Factors:
        1. Trend strength (20-period SMA vs 50-period SMA crossover)
        2. Volatility (ATR, standard deviation)
        3. Price momentum (24h change, recent returns)
        4. Volume profile
        """
        # If regime is passed in from global detector, use it
        if current_regime:
            return self._map_global_regime_to_local(current_regime, market_data)

        # Otherwise, perform local detection
        if historical_data is None or len(historical_data) < 50:
            # Not enough data for regime detection - default to ranging
            return RegimeDetectionResult(
                regime=MarketRegimeType.CRAB_RANGING,
                confidence=0.5,
                volatility=1.0,
                trend_strength=0.0,
                reasoning="Insufficient historical data - defaulting to ranging regime",
            )

        # Calculate indicators
        closes = historical_data["close"]
        sma_20 = closes.rolling(20).mean()
        sma_50 = closes.rolling(50).mean()

        # Volatility (ATR normalized by price)
        high_low = historical_data["high"] - historical_data["low"]
        volatility = (high_low.rolling(14).mean() / closes).iloc[-1]

        # Trend strength (SMA gradient)
        recent_sma_20 = sma_20.tail(10)
        sma_gradient = (recent_sma_20.iloc[-1] - recent_sma_20.iloc[0]) / recent_sma_20.iloc[0]

        # Price position relative to SMAs
        current_price = market_data.price
        latest_sma_20 = sma_20.iloc[-1]
        latest_sma_50 = sma_50.iloc[-1]

        price_above_20 = current_price > latest_sma_20
        price_above_50 = current_price > latest_sma_50
        sma_20_above_50 = latest_sma_20 > latest_sma_50

        # Recent momentum
        recent_returns = closes.pct_change().tail(20)
        momentum = recent_returns.mean()

        # Decision logic
        # High volatility detection (first priority)
        if volatility > 0.03:  # 3% daily ATR
            return RegimeDetectionResult(
                regime=MarketRegimeType.HIGH_VOLATILITY,
                confidence=min(volatility / 0.03, 1.0),
                volatility=volatility,
                trend_strength=abs(sma_gradient),
                reasoning=f"High volatility detected (ATR: {volatility*100:.2f}%)",
            )

        # Low volatility detection
        if volatility < 0.01:  # 1% daily ATR
            return RegimeDetectionResult(
                regime=MarketRegimeType.LOW_VOLATILITY,
                confidence=1.0 - (volatility / 0.01),
                volatility=volatility,
                trend_strength=abs(sma_gradient),
                reasoning=f"Low volatility detected (ATR: {volatility*100:.2f}%)",
            )

        # Trend detection
        if price_above_20 and price_above_50 and sma_20_above_50 and sma_gradient > 0.005:
            # Strong uptrend
            conf = min(abs(sma_gradient) / 0.01 + 0.5, 1.0)
            return RegimeDetectionResult(
                regime=MarketRegimeType.BULL_TRENDING,
                confidence=conf,
                volatility=volatility,
                trend_strength=abs(sma_gradient),
                reasoning=f"Uptrend: Price > SMA20 > SMA50, momentum: {momentum*100:.2f}%",
            )

        if (
            not price_above_20
            and not price_above_50
            and not sma_20_above_50
            and sma_gradient < -0.005
        ):
            # Strong downtrend
            conf = min(abs(sma_gradient) / 0.01 + 0.5, 1.0)
            return RegimeDetectionResult(
                regime=MarketRegimeType.BEAR_TRENDING,
                confidence=conf,
                volatility=volatility,
                trend_strength=abs(sma_gradient),
                reasoning=f"Downtrend: Price < SMA20 < SMA50, momentum: {momentum*100:.2f}%",
            )

        # Default to ranging (crab market)
        return RegimeDetectionResult(
            regime=MarketRegimeType.CRAB_RANGING,
            confidence=0.7,
            volatility=volatility,
            trend_strength=abs(sma_gradient),
            reasoning=f"Ranging market: Mixed SMA signals, low trend strength",
        )

    def _map_global_regime_to_local(
        self, global_regime: str, market_data: MarketSnapshot
    ) -> RegimeDetectionResult:
        """Map global regime string to our RegimeDetectionResult."""
        regime_map = {
            "BULL": MarketRegimeType.BULL_TRENDING,
            "BEAR": MarketRegimeType.BEAR_TRENDING,
            "CRAB": MarketRegimeType.CRAB_RANGING,
            "NEUTRAL": MarketRegimeType.CRAB_RANGING,
        }

        regime_type = regime_map.get(global_regime.upper(), MarketRegimeType.CRAB_RANGING)

        # Estimate volatility from 24h change
        volatility = abs(market_data.change_24h) / 100

        return RegimeDetectionResult(
            regime=regime_type,
            confidence=0.8,  # Moderate confidence when using global regime
            volatility=volatility,
            trend_strength=abs(market_data.change_24h) / 10,
            reasoning=f"Using global regime: {global_regime}",
        )

    def _select_strategy_for_regime(self, regime_result: RegimeDetectionResult) -> TradingStrategy:
        """
        Select the optimal strategy for the detected regime.

        Strategy mapping:
        - BULL_TRENDING → Momentum (ride the trend)
        - BEAR_TRENDING → Momentum (short the trend)
        - CRAB_RANGING → Mean Reversion (buy low, sell high)
        - HIGH_VOLATILITY → Arbitrage (exploit volatility)
        - LOW_VOLATILITY → Mean Reversion (predictable reversions)
        """
        regime = regime_result.regime

        if regime == MarketRegimeType.BULL_TRENDING:
            return self.strategies["momentum"]

        elif regime == MarketRegimeType.BEAR_TRENDING:
            return self.strategies["momentum"]

        elif regime == MarketRegimeType.CRAB_RANGING:
            return self.strategies["mean_reversion"]

        elif regime == MarketRegimeType.HIGH_VOLATILITY:
            # In high volatility, arbitrage or wait
            return self.strategies["arbitrage"]

        elif regime == MarketRegimeType.LOW_VOLATILITY:
            # Low volatility = predictable mean reversion
            return self.strategies["mean_reversion"]

        # Fallback to mean reversion (current default)
        return self.strategies["mean_reversion"]

    def update_strategy_performance(
        self, strategy_name: str, regime: MarketRegimeType, profit: float, success: bool
    ) -> None:
        """
        Track strategy performance per regime for adaptive learning.

        This allows us to dynamically adjust which strategy we prefer
        for each regime based on actual live performance.
        """
        key = (strategy_name, regime.value)

        if key not in self.strategy_performance:
            self.strategy_performance[key] = {
                "trades": 0,
                "wins": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
            }

        perf = self.strategy_performance[key]
        perf["trades"] += 1
        perf["total_pnl"] += profit

        if success:
            perf["wins"] += 1

        perf["win_rate"] = perf["wins"] / perf["trades"]
        perf["avg_pnl"] = perf["total_pnl"] / perf["trades"]

        logger.info(
            f"📈 Performance Update: {strategy_name} in {regime.value} - "
            f"Win Rate: {perf['win_rate']:.1%}, Avg PnL: ${perf['avg_pnl']:.2f}"
        )

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report across all strategies and regimes."""
        report = {
            "total_strategies": len(self.strategies),
            "tracked_combinations": len(self.strategy_performance),
            "performance_by_strategy": {},
            "performance_by_regime": {},
        }

        for (strategy, regime), perf in self.strategy_performance.items():
            # By strategy
            if strategy not in report["performance_by_strategy"]:
                report["performance_by_strategy"][strategy] = {
                    "total_trades": 0,
                    "total_wins": 0,
                    "total_pnl": 0.0,
                }

            report["performance_by_strategy"][strategy]["total_trades"] += perf["trades"]
            report["performance_by_strategy"][strategy]["total_wins"] += perf["wins"]
            report["performance_by_strategy"][strategy]["total_pnl"] += perf["total_pnl"]

            # By regime
            if regime not in report["performance_by_regime"]:
                report["performance_by_regime"][regime] = {
                    "total_trades": 0,
                    "total_wins": 0,
                    "total_pnl": 0.0,
                }

            report["performance_by_regime"][regime]["total_trades"] += perf["trades"]
            report["performance_by_regime"][regime]["total_wins"] += perf["wins"]
            report["performance_by_regime"][regime]["total_pnl"] += perf["total_pnl"]

        return report


# Global singleton
_strategy_router: Optional[StrategyRouter] = None


def get_strategy_router() -> StrategyRouter:
    """Get or create the global strategy router instance."""
    global _strategy_router
    if _strategy_router is None:
        _strategy_router = StrategyRouter()
    return _strategy_router
