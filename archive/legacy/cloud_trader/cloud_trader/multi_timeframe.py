"""Multi-timeframe analysis system for enhanced trading signals."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .cache import BaseCache, get_cache
from .market_regime import MarketRegime, RegimeMetrics
from .time_sync import get_precision_clock, get_timestamp_us

logger = logging.getLogger(__name__)


class Timeframe(Enum):
    """Available timeframes for analysis."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"


class AnalysisType(Enum):
    """Types of multi-timeframe analysis."""

    TREND_ALIGNMENT = "trend_alignment"
    MOMENTUM_DIVERGENCE = "momentum_divergence"
    VOLUME_CONFIRMATION = "volume_confirmation"
    SUPPORT_RESISTANCE = "support_resistance"
    PATTERN_RECOGNITION = "pattern_recognition"
    VOLATILITY_REGIME = "volatility_regime"


@dataclass
class TimeframeData:
    """OHLCV data for a specific timeframe."""

    timeframe: Timeframe
    symbol: str
    timestamp_us: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    vpin: Optional[float] = None
    quote_imbalance: Optional[float] = None
    indicators: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timeframe": self.timeframe.value,
            "symbol": self.symbol,
            "timestamp_us": self.timestamp_us,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "vpin": self.vpin,
            "quote_imbalance": self.quote_imbalance,
            "indicators": self.indicators,
        }


@dataclass
class MultiTimeframeSignal:
    """Signal generated from multi-timeframe analysis."""

    symbol: str
    primary_timeframe: Timeframe
    signal_type: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0-1
    analysis_type: AnalysisType
    timeframe_contributions: Dict[Timeframe, Dict[str, Any]]
    overall_score: float
    timestamp_us: int
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "primary_timeframe": self.primary_timeframe.value,
            "signal_type": self.signal_type,
            "confidence": self.confidence,
            "analysis_type": self.analysis_type.value,
            "timeframe_contributions": {
                tf.value: contrib for tf, contrib in self.timeframe_contributions.items()
            },
            "overall_score": self.overall_score,
            "timestamp_us": self.timestamp_us,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }


class MultiTimeframeAnalyzer:
    """
    Advanced multi-timeframe analysis system.

    Analyzes market data across multiple timeframes to generate more robust signals
    by considering alignment, divergence, and confirmation patterns.
    """

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history

        # Data storage: symbol -> timeframe -> deque of TimeframeData
        self.market_data: Dict[str, Dict[Timeframe, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=max_history))
        )

        # Analysis weights for different timeframes
        self.timeframe_weights = {
            Timeframe.ONE_MINUTE: 0.1,
            Timeframe.FIVE_MINUTES: 0.15,
            Timeframe.FIFTEEN_MINUTES: 0.2,
            Timeframe.THIRTY_MINUTES: 0.15,
            Timeframe.ONE_HOUR: 0.25,
            Timeframe.FOUR_HOURS: 0.1,
            Timeframe.ONE_DAY: 0.04,
            Timeframe.ONE_WEEK: 0.01,
        }

        # Cache for performance
        self._cache: Optional[BaseCache] = None
        self._cache_ready = False

        # Analysis functions
        self.analysis_functions: Dict[AnalysisType, Callable] = {
            AnalysisType.TREND_ALIGNMENT: self._analyze_trend_alignment,
            AnalysisType.MOMENTUM_DIVERGENCE: self._analyze_momentum_divergence,
            AnalysisType.VOLUME_CONFIRMATION: self._analyze_volume_confirmation,
            AnalysisType.SUPPORT_RESISTANCE: self._analyze_support_resistance,
            AnalysisType.PATTERN_RECOGNITION: self._analyze_pattern_recognition,
            AnalysisType.VOLATILITY_REGIME: self._analyze_volatility_regime,
        }

    async def initialize(self) -> None:
        """Initialize the analyzer."""
        try:
            self._cache = await get_cache()
            self._cache_ready = self._cache.is_connected()
            if self._cache_ready:
                logger.info("Multi-timeframe analyzer cache initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize analyzer cache: {e}")

    def add_market_data(self, data: TimeframeData) -> None:
        """Add market data for a specific timeframe."""
        symbol_data = self.market_data[data.symbol]
        symbol_data[data.timeframe].append(data)

        # Cache if available
        if self._cache_ready:
            cache_key = f"mtf_data:{data.symbol}:{data.timeframe.value}:{data.timestamp_us}"
            try:
                asyncio.create_task(self._cache.set(cache_key, data.to_dict(), ttl=3600))  # 1 hour
            except Exception as e:
                logger.debug(f"Failed to cache market data: {e}")

    async def analyze_symbol(
        self,
        symbol: str,
        primary_timeframe: Timeframe = Timeframe.ONE_HOUR,
        analysis_types: Optional[List[AnalysisType]] = None,
    ) -> List[MultiTimeframeSignal]:
        """
        Perform multi-timeframe analysis for a symbol.

        Returns a list of signals from different analysis types.
        """
        if analysis_types is None:
            analysis_types = list(AnalysisType)

        signals = []

        for analysis_type in analysis_types:
            try:
                if analysis_type in self.analysis_functions:
                    signal = await self.analysis_functions[analysis_type](symbol, primary_timeframe)
                    if signal:
                        signals.append(signal)
            except Exception as e:
                logger.warning(f"Error in {analysis_type.value} analysis for {symbol}: {e}")

        return signals

    async def _analyze_trend_alignment(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze trend alignment across timeframes."""
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        # Get trend direction for each timeframe
        timeframe_trends = {}
        contributions = {}

        for timeframe in Timeframe:
            data_queue = symbol_data.get(timeframe)
            if not data_queue or len(data_queue) < 5:
                continue

            # Calculate simple trend (slope of closing prices)
            recent_data = list(data_queue)[-10:]  # Last 10 candles
            if len(recent_data) >= 5:
                closes = [d.close_price for d in recent_data]
                trend_slope = self._calculate_trend_slope(closes)

                # Classify trend
                if trend_slope > 0.001:
                    trend_direction = "UP"
                elif trend_slope < -0.001:
                    trend_direction = "DOWN"
                else:
                    trend_direction = "SIDEWAYS"

                timeframe_trends[timeframe] = trend_direction
                contributions[timeframe] = {
                    "trend_slope": trend_slope,
                    "direction": trend_direction,
                    "weight": self.timeframe_weights[timeframe],
                    "data_points": len(recent_data),
                }

        if not timeframe_trends:
            return None

        # Calculate alignment score
        primary_trend = timeframe_trends.get(primary_timeframe, "SIDEWAYS")
        alignment_score = 0
        total_weight = 0

        for timeframe, trend_data in contributions.items():
            weight = trend_data["weight"]
            total_weight += weight

            if trend_data["direction"] == primary_trend:
                alignment_score += weight
            elif primary_trend != "SIDEWAYS" and trend_data["direction"] == "SIDEWAYS":
                alignment_score += weight * 0.5  # Partial credit for neutral

        if total_weight == 0:
            return None

        alignment_score /= total_weight

        # Generate signal
        confidence = min(alignment_score * 0.9, 0.95)  # Cap at 95%

        if primary_trend == "UP" and alignment_score > 0.6:
            signal_type = "BUY"
            reasoning = f"Strong upward trend alignment ({alignment_score:.2f}) across {len(contributions)} timeframes"
        elif primary_trend == "DOWN" and alignment_score > 0.6:
            signal_type = "SELL"
            reasoning = f"Strong downward trend alignment ({alignment_score:.2f}) across {len(contributions)} timeframes"
        else:
            signal_type = "HOLD"
            reasoning = f"Weak or conflicting trend alignment ({alignment_score:.2f})"
            confidence *= 0.5

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.TREND_ALIGNMENT,
            timeframe_contributions=contributions,
            overall_score=alignment_score,
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    async def _analyze_momentum_divergence(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze momentum divergence across timeframes."""
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        # Calculate RSI for different timeframes
        timeframe_momentum = {}
        contributions = {}

        for timeframe in Timeframe:
            data_queue = symbol_data.get(timeframe)
            if not data_queue or len(data_queue) < 14:  # Need at least 14 periods for RSI
                continue

            recent_data = list(data_queue)[-20:]  # Last 20 candles
            rsi_values = self._calculate_rsi([d.close_price for d in recent_data])

            if rsi_values:
                current_rsi = rsi_values[-1]
                prev_rsi = rsi_values[-2] if len(rsi_values) > 1 else current_rsi

                # Classify momentum
                if current_rsi > 70:
                    momentum = "OVERBOUGHT"
                elif current_rsi < 30:
                    momentum = "OVERSOLD"
                elif current_rsi > prev_rsi:
                    momentum = "INCREASING"
                elif current_rsi < prev_rsi:
                    momentum = "DECREASING"
                else:
                    momentum = "NEUTRAL"

                timeframe_momentum[timeframe] = {
                    "rsi": current_rsi,
                    "momentum": momentum,
                    "change": current_rsi - prev_rsi,
                }

                contributions[timeframe] = {
                    "rsi": current_rsi,
                    "momentum": momentum,
                    "rsi_change": current_rsi - prev_rsi,
                    "weight": self.timeframe_weights[timeframe],
                }

        if len(timeframe_momentum) < 2:
            return None

        # Look for divergences
        primary_momentum = timeframe_momentum.get(primary_timeframe)
        if not primary_momentum:
            return None

        divergence_score = 0
        total_weight = 0

        for timeframe, momentum_data in timeframe_momentum.items():
            if timeframe == primary_timeframe:
                continue

            weight = self.timeframe_weights[timeframe]
            total_weight += weight

            # Check for bullish divergence (price down, momentum up)
            if (
                primary_momentum["rsi"] < 50
                and momentum_data["rsi"] > primary_momentum["rsi"]
                and momentum_data["change"] > 0
            ):
                divergence_score += weight * 0.8  # Bullish divergence

            # Check for bearish divergence (price up, momentum down)
            elif (
                primary_momentum["rsi"] > 50
                and momentum_data["rsi"] < primary_momentum["rsi"]
                and momentum_data["change"] < 0
            ):
                divergence_score -= weight * 0.8  # Bearish divergence

        if total_weight == 0:
            return None

        divergence_score /= total_weight

        # Generate signal
        confidence = min(abs(divergence_score) * 0.8, 0.9)

        if divergence_score > 0.3:
            signal_type = "BUY"
            reasoning = f"Bullish momentum divergence detected ({divergence_score:.2f})"
        elif divergence_score < -0.3:
            signal_type = "SELL"
            reasoning = f"Bearish momentum divergence detected ({divergence_score:.2f})"
        else:
            return None  # No significant divergence

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.MOMENTUM_DIVERGENCE,
            timeframe_contributions=contributions,
            overall_score=divergence_score,
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    async def _analyze_volume_confirmation(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze volume confirmation across timeframes."""
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        # Analyze volume trends
        timeframe_volume = {}
        contributions = {}

        for timeframe in Timeframe:
            data_queue = symbol_data.get(timeframe)
            if not data_queue or len(data_queue) < 10:
                continue

            recent_data = list(data_queue)[-15:]  # Last 15 candles
            volumes = [d.volume for d in recent_data]
            closes = [d.close_price for d in recent_data]

            # Calculate volume trend and price-volume relationship
            volume_trend = self._calculate_trend_slope(volumes)
            price_trend = self._calculate_trend_slope(closes)

            # Volume confirmation (price and volume moving in same direction)
            confirmation = 1.0 if (volume_trend * price_trend) > 0 else -1.0

            # Volume intensity (relative to average)
            avg_volume = sum(volumes) / len(volumes)
            current_volume = volumes[-1]
            intensity = current_volume / avg_volume if avg_volume > 0 else 1.0

            timeframe_volume[timeframe] = {
                "confirmation": confirmation,
                "intensity": intensity,
                "volume_trend": volume_trend,
                "price_trend": price_trend,
            }

            contributions[timeframe] = {
                "confirmation": confirmation,
                "intensity": intensity,
                "avg_volume": avg_volume,
                "current_volume": current_volume,
                "weight": self.timeframe_weights[timeframe],
            }

        if not timeframe_volume:
            return None

        # Calculate overall volume confirmation
        confirmation_score = 0
        intensity_score = 0
        total_weight = 0

        for timeframe, volume_data in timeframe_volume.items():
            weight = self.timeframe_weights[timeframe]
            total_weight += weight

            confirmation_score += volume_data["confirmation"] * weight
            intensity_score += min(volume_data["intensity"], 3.0) * weight  # Cap at 3x average

        if total_weight == 0:
            return None

        confirmation_score /= total_weight
        intensity_score /= total_weight

        # Generate signal based on volume confirmation
        overall_score = (confirmation_score + intensity_score) / 2
        confidence = min(abs(overall_score) * 0.7, 0.85)

        if overall_score > 0.4 and confirmation_score > 0:
            signal_type = "BUY"
            reasoning = f"Strong volume confirmation ({confirmation_score:.2f}) with high intensity ({intensity_score:.2f})"
        elif overall_score < -0.4 and confirmation_score < 0:
            signal_type = "SELL"
            reasoning = f"Strong volume confirmation ({confirmation_score:.2f}) with high intensity ({intensity_score:.2f})"
        else:
            return None  # Insufficient volume confirmation

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.VOLUME_CONFIRMATION,
            timeframe_contributions=contributions,
            overall_score=overall_score,
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    async def _analyze_support_resistance(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze support and resistance levels across timeframes."""
        # This is a simplified implementation - in practice would use more sophisticated SR detection
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        primary_data = symbol_data.get(primary_timeframe)
        if not primary_data or len(primary_data) < 20:
            return None

        recent_data = list(primary_data)[-50:]  # Last 50 candles
        current_price = recent_data[-1].close_price

        # Simple SR detection based on swing highs/lows
        highs = [d.high_price for d in recent_data]
        lows = [d.low_price for d in recent_data]

        # Find potential resistance (recent highs above current price)
        resistance_levels = [h for h in highs[-20:] if h > current_price]  # Last 20 periods
        resistance = max(resistance_levels) if resistance_levels else None

        # Find potential support (recent lows below current price)
        support_levels = [l for l in lows[-20:] if l < current_price]  # Last 20 periods
        support = min(support_levels) if support_levels else None

        if not resistance and not support:
            return None

        # Calculate proximity to levels
        resistance_distance = (
            (resistance - current_price) / current_price if resistance else float("inf")
        )
        support_distance = (current_price - support) / current_price if support else float("inf")

        # Generate signal
        if resistance and resistance_distance < 0.02:  # Within 2% of resistance
            signal_type = "SELL"
            confidence = min((1 - resistance_distance / 0.02) * 0.8, 0.9)
            reasoning = (
                f"Price near resistance level at {resistance:.4f} ({resistance_distance:.1%} away)"
            )
        elif support and support_distance < 0.02:  # Within 2% of support
            signal_type = "BUY"
            confidence = min((1 - support_distance / 0.02) * 0.8, 0.9)
            reasoning = f"Price near support level at {support:.4f} ({support_distance:.1%} away)"
        else:
            return None

        contributions = {
            primary_timeframe: {
                "current_price": current_price,
                "resistance": resistance,
                "support": support,
                "resistance_distance": resistance_distance,
                "support_distance": support_distance,
                "weight": 1.0,
            }
        }

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.SUPPORT_RESISTANCE,
            timeframe_contributions=contributions,
            overall_score=1 - min(resistance_distance, support_distance) / 0.02,
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    async def _analyze_pattern_recognition(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze chart patterns across timeframes."""
        # Simplified pattern recognition - in practice would use more sophisticated algorithms
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        primary_data = symbol_data.get(primary_timeframe)
        if not primary_data or len(primary_data) < 20:
            return None

        recent_data = list(primary_data)[-20:]

        # Simple double bottom/top detection
        lows = [d.low_price for d in recent_data]
        highs = [d.high_price for d in recent_data]

        # Look for double bottom pattern
        min_indices = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                min_indices.append(i)

        # Look for double top pattern
        max_indices = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                max_indices.append(i)

        pattern_detected = None
        confidence = 0.0
        reasoning = ""

        if len(min_indices) >= 2:
            # Check if lows are similar (within 2%)
            recent_mins = [lows[i] for i in min_indices[-2:]]
            if abs(recent_mins[0] - recent_mins[1]) / recent_mins[0] < 0.02:
                pattern_detected = "DOUBLE_BOTTOM"
                confidence = 0.75
                reasoning = "Double bottom pattern detected - potential bullish reversal"

        elif len(max_indices) >= 2:
            # Check if highs are similar (within 2%)
            recent_maxes = [highs[i] for i in max_indices[-2:]]
            if abs(recent_maxes[0] - recent_maxes[1]) / recent_maxes[0] < 0.02:
                pattern_detected = "DOUBLE_TOP"
                confidence = 0.75
                reasoning = "Double top pattern detected - potential bearish reversal"

        if not pattern_detected:
            return None

        signal_type = "BUY" if pattern_detected == "DOUBLE_BOTTOM" else "SELL"

        contributions = {
            primary_timeframe: {
                "pattern": pattern_detected,
                "min_indices": min_indices,
                "max_indices": max_indices,
                "weight": 1.0,
            }
        }

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.PATTERN_RECOGNITION,
            timeframe_contributions=contributions,
            overall_score=confidence,
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    async def _analyze_volatility_regime(
        self, symbol: str, primary_timeframe: Timeframe
    ) -> Optional[MultiTimeframeSignal]:
        """Analyze volatility regime across timeframes."""
        symbol_data = self.market_data.get(symbol)
        if not symbol_data:
            return None

        # Calculate volatility for each timeframe
        timeframe_volatility = {}
        contributions = {}

        for timeframe in Timeframe:
            data_queue = symbol_data.get(timeframe)
            if not data_queue or len(data_queue) < 20:
                continue

            recent_data = list(data_queue)[-30:]  # Last 30 candles
            closes = [d.close_price for d in recent_data]

            # Calculate volatility (standard deviation of returns)
            returns = []
            for i in range(1, len(closes)):
                ret = (closes[i] - closes[i - 1]) / closes[i - 1]
                returns.append(ret)

            if returns:
                volatility = sum(r**2 for r in returns) / len(returns)  # Variance
                volatility = volatility**0.5  # Standard deviation

                # Classify volatility regime
                if volatility > 0.05:  # High volatility
                    regime = "HIGH"
                elif volatility > 0.02:  # Medium volatility
                    regime = "MEDIUM"
                else:  # Low volatility
                    regime = "LOW"

                timeframe_volatility[timeframe] = {"volatility": volatility, "regime": regime}

                contributions[timeframe] = {
                    "volatility": volatility,
                    "regime": regime,
                    "returns_count": len(returns),
                    "weight": self.timeframe_weights[timeframe],
                }

        if not timeframe_volatility:
            return None

        # Determine dominant volatility regime
        regime_counts = defaultdict(int)
        for tf_data in timeframe_volatility.values():
            regime_counts[tf_data["regime"]] += 1

        dominant_regime = max(regime_counts, key=regime_counts.get)

        # Generate signal based on volatility regime
        if dominant_regime == "HIGH":
            signal_type = "HOLD"
            confidence = 0.6
            reasoning = "High volatility regime detected - avoid new positions"
        elif dominant_regime == "LOW":
            signal_type = "BUY"  # Low volatility often precedes breakouts
            confidence = 0.5
            reasoning = "Low volatility regime - potential for breakout"
        else:
            signal_type = "HOLD"
            confidence = 0.4
            reasoning = "Moderate volatility regime - normal conditions"

        return MultiTimeframeSignal(
            symbol=symbol,
            primary_timeframe=primary_timeframe,
            signal_type=signal_type,
            confidence=confidence,
            analysis_type=AnalysisType.VOLATILITY_REGIME,
            timeframe_contributions=contributions,
            overall_score=0.5,  # Neutral score for regime analysis
            timestamp_us=get_timestamp_us(),
            reasoning=reasoning,
        )

    def _calculate_trend_slope(self, values: List[float]) -> float:
        """Calculate linear trend slope for a series of values."""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))
        y = values

        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi**2 for xi in x)

        if n * sum_x2 - sum_x**2 == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)
        return slope

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI for a series of prices."""
        if len(prices) < period + 1:
            return []

        rsi_values = []
        gains = []
        losses = []

        # Calculate price changes
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))

        # Calculate initial averages
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Calculate RSI
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)

        # Calculate subsequent values using smoothed averages
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            rsi_values.append(rsi)

        return rsi_values

    def get_analysis_stats(self) -> Dict[str, Any]:
        """Get comprehensive analysis statistics."""
        symbols_analyzed = len(self.market_data)
        total_data_points = sum(
            sum(len(data_queue) for data_queue in tf_data.values())
            for tf_data in self.market_data.values()
        )

        timeframe_counts = defaultdict(int)
        for symbol_data in self.market_data.values():
            for timeframe in symbol_data.keys():
                timeframe_counts[timeframe] += 1

        return {
            "symbols_analyzed": symbols_analyzed,
            "total_data_points": total_data_points,
            "timeframe_distribution": {tf.value: count for tf, count in timeframe_counts.items()},
            "cache_enabled": self._cache_ready,
            "timestamp_us": get_timestamp_us(),
        }


# Global multi-timeframe analyzer instance
_multi_timeframe_analyzer: Optional[MultiTimeframeAnalyzer] = None


async def get_multi_timeframe_analyzer() -> MultiTimeframeAnalyzer:
    """Get global multi-timeframe analyzer instance."""
    global _multi_timeframe_analyzer
    if _multi_timeframe_analyzer is None:
        _multi_timeframe_analyzer = MultiTimeframeAnalyzer()
        await _multi_timeframe_analyzer.initialize()
    return _multi_timeframe_analyzer
