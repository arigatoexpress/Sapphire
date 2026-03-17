"""Advanced market regime detection for adaptive trading strategies."""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"
    UNKNOWN = "unknown"


@dataclass
class RegimeMetrics:
    """Comprehensive market regime metrics."""

    regime: MarketRegime
    confidence: float
    trend_strength: float
    volatility_level: float
    range_bound_score: float
    momentum_score: float
    timestamp_us: int

    # Component scores
    adx_score: float  # Average Directional Index
    rsi_score: float  # Relative Strength Index divergence
    bb_position: float  # Bollinger Band position
    volume_trend: float  # Volume trend analysis

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "trend_strength": self.trend_strength,
            "volatility_level": self.volatility_level,
            "range_bound_score": self.range_bound_score,
            "momentum_score": self.momentum_score,
            "timestamp_us": self.timestamp_us,
            "adx_score": self.adx_score,
            "rsi_score": self.rsi_score,
            "bb_position": self.bb_position,
            "volume_trend": self.volume_trend,
        }


class MarketRegimeDetector:
    """Advanced market regime detector using multiple technical indicators."""

    def __init__(self, window_size: int = 100, min_periods: int = 20):
        self.window_size = window_size
        self.min_periods = min_periods

        # Price and volume data buffers
        self.prices: Deque[float] = Deque(maxlen=window_size)
        self.volumes: Deque[float] = Deque(maxlen=window_size)
        self.highs: Deque[float] = Deque(maxlen=window_size)
        self.lows: Deque[float] = Deque(maxlen=window_size)

        # Indicator buffers
        self.sma_20: Deque[float] = Deque(maxlen=window_size)
        self.sma_50: Deque[float] = Deque(maxlen=window_size)
        self.ema_12: Deque[float] = Deque(maxlen=window_size)
        self.ema_26: Deque[float] = Deque(maxlen=window_size)
        self.rsi_values: Deque[float] = Deque(maxlen=window_size)
        self.adx_values: Deque[float] = Deque(maxlen=window_size)

        # Bollinger Bands
        self.bb_upper: Deque[float] = Deque(maxlen=window_size)
        self.bb_lower: Deque[float] = Deque(maxlen=window_size)
        self.bb_middle: Deque[float] = Deque(maxlen=window_size)

        # Historical regime tracking
        self.regime_history: Deque[RegimeMetrics] = Deque(maxlen=1000)
        self.regime_stability: Dict[MarketRegime, int] = {regime: 0 for regime in MarketRegime}

    def add_price_data(
        self, price: float, volume: float, high: float, low: float
    ) -> Optional[RegimeMetrics]:
        """
        Add new price/volume data and return current regime analysis.
        Returns None if insufficient data for analysis.
        """
        self.prices.append(price)
        self.volumes.append(volume)
        self.highs.append(high)
        self.lows.append(low)

        if len(self.prices) < self.min_periods:
            return None

        # Calculate all indicators
        self._calculate_indicators()

        # Determine regime
        regime_metrics = self._analyze_regime()

        # Update stability tracking
        if regime_metrics:
            self.regime_history.append(regime_metrics)
            self._update_regime_stability(regime_metrics.regime)

        return regime_metrics

    def _calculate_indicators(self):
        """Calculate all technical indicators."""
        prices_list = list(self.prices)

        # Simple Moving Averages
        if len(prices_list) >= 20:
            self.sma_20.append(statistics.mean(prices_list[-20:]))
        if len(prices_list) >= 50:
            self.sma_50.append(statistics.mean(prices_list[-50:]))

        # Exponential Moving Averages
        self._calculate_ema(prices_list, 12, self.ema_12)
        self._calculate_ema(prices_list, 26, self.ema_26)

        # RSI
        self._calculate_rsi(prices_list)

        # ADX (Average Directional Index)
        self._calculate_adx()

        # Bollinger Bands
        self._calculate_bollinger_bands(prices_list)

    def _calculate_ema(self, prices: List[float], period: int, target_buffer: Deque):
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return

        multiplier = 2 / (period + 1)

        if not target_buffer:
            # Initialize with SMA
            target_buffer.append(statistics.mean(prices[:period]))
        else:
            # Calculate EMA
            current_ema = target_buffer[-1]
            ema_value = (prices[-1] - current_ema) * multiplier + current_ema
            target_buffer.append(ema_value)

    def _calculate_rsi(self, prices: List[float], period: int = 14):
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))

        if len(gains) >= period:
            avg_gain = statistics.mean(gains[-period:])
            avg_loss = statistics.mean(losses[-period:])

            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            self.rsi_values.append(rsi)

    def _calculate_adx(self, period: int = 14):
        """Calculate Average Directional Index."""
        if len(self.highs) < period or len(self.lows) < period or len(self.prices) < period:
            return

        highs = list(self.highs)[-period:]
        lows = list(self.lows)[-period:]
        closes = list(self.prices)[-period:]

        # Calculate True Range, +DI, -DI
        tr_values = []
        plus_dm_values = []
        minus_dm_values = []

        for i in range(1, len(highs)):
            # True Range
            tr = max(
                highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])
            )
            tr_values.append(tr)

            # Directional Movement
            move_up = highs[i] - highs[i - 1]
            move_down = lows[i - 1] - lows[i]

            plus_dm = move_up if move_up > move_down and move_up > 0 else 0
            minus_dm = move_down if move_down > move_up and move_down > 0 else 0

            plus_dm_values.append(plus_dm)
            minus_dm_values.append(minus_dm)

        if len(tr_values) >= period - 1:
            # Average TR, +DI, -DI
            avg_tr = statistics.mean(tr_values)
            avg_plus_dm = statistics.mean(plus_dm_values)
            avg_minus_dm = statistics.mean(minus_dm_values)

            plus_di = (avg_plus_dm / avg_tr) * 100 if avg_tr > 0 else 0
            minus_di = (avg_minus_dm / avg_tr) * 100 if avg_tr > 0 else 0

            # DX and ADX
            dx = (
                abs(plus_di - minus_di) / (plus_di + minus_di) * 100
                if (plus_di + minus_di) > 0
                else 0
            )
            self.adx_values.append(dx)

    def _calculate_bollinger_bands(
        self, prices: List[float], period: int = 20, std_dev: float = 2.0
    ):
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return

        recent_prices = prices[-period:]
        sma = statistics.mean(recent_prices)
        std = statistics.stdev(recent_prices) if len(recent_prices) > 1 else 0

        self.bb_middle.append(sma)
        self.bb_upper.append(sma + std_dev * std)
        self.bb_lower.append(sma - std_dev * std)

    def _analyze_regime(self) -> Optional[RegimeMetrics]:
        """Analyze current market regime using all indicators."""
        if (
            len(self.prices) < self.min_periods
            or not self.adx_values
            or not self.rsi_values
            or not self.bb_upper
        ):
            return None

        current_price = self.prices[-1]

        # Calculate component scores
        adx_score = self.adx_values[-1] if self.adx_values else 0

        # Trend strength (ADX > 25 indicates trending market)
        trend_strength = min(adx_score / 25.0, 1.0)

        # RSI divergence (extreme RSI can indicate regime changes)
        rsi_score = abs(50 - self.rsi_values[-1]) / 50.0 if self.rsi_values else 0

        # Bollinger Band position (how far price is from middle band)
        bb_middle = self.bb_middle[-1] if self.bb_middle else current_price
        bb_upper = self.bb_upper[-1] if self.bb_upper else current_price
        bb_lower = self.bb_lower[-1] if self.bb_lower else current_price

        if bb_upper > bb_lower:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            bb_position = max(0, min(1, bb_position))  # Clamp to [0,1]
        else:
            bb_position = 0.5

        # Volume trend analysis
        volume_trend = self._analyze_volume_trend()

        # Volatility level (BB width relative to price)
        bb_width = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0
        volatility_level = min(bb_width * 100, 1.0)  # Scale and cap

        # Range-bound score (low ADX + price near BB middle)
        range_bound_score = (1 - trend_strength) * (1 - abs(bb_position - 0.5) * 2)

        # Momentum score (MACD-like signal)
        momentum_score = self._calculate_momentum_score()

        # Regime classification logic
        regime, confidence = self._classify_regime(
            trend_strength,
            volatility_level,
            range_bound_score,
            momentum_score,
            adx_score,
            bb_position,
        )

        return RegimeMetrics(
            regime=regime,
            confidence=confidence,
            trend_strength=trend_strength,
            volatility_level=volatility_level,
            range_bound_score=range_bound_score,
            momentum_score=momentum_score,
            timestamp_us=get_timestamp_us(),
            adx_score=adx_score,
            rsi_score=rsi_score,
            bb_position=bb_position,
            volume_trend=volume_trend,
        )

    def _analyze_volume_trend(self) -> float:
        """Analyze volume trend (increasing/decreasing volume)."""
        if len(self.volumes) < 10:
            return 0.0

        recent_volumes = list(self.volumes)[-20:]
        if len(recent_volumes) < 10:
            return 0.0

        # Simple linear regression slope
        x = list(range(len(recent_volumes)))
        y = recent_volumes

        try:
            slope = statistics.linear_regression(x, y).slope
            avg_volume = statistics.mean(recent_volumes)
            return slope / avg_volume if avg_volume > 0 else 0.0
        except:
            return 0.0

    def _calculate_momentum_score(self) -> float:
        """Calculate momentum score using EMA crossover."""
        if len(self.ema_12) < 2 or len(self.ema_26) < 2:
            return 0.0

        ema12_current = self.ema_12[-1]
        ema26_current = self.ema_26[-1]
        ema12_prev = self.ema_12[-2]
        ema26_prev = self.ema_26[-2]

        # MACD-like momentum
        momentum = (ema12_current - ema26_current) - (ema12_prev - ema26_prev)
        return momentum / abs(ema26_current) if ema26_current != 0 else 0.0

    def _classify_regime(
        self,
        trend_strength: float,
        volatility_level: float,
        range_bound_score: float,
        momentum_score: float,
        adx_score: float,
        bb_position: float,
    ) -> Tuple[MarketRegime, float]:
        """Classify market regime based on indicator scores."""

        # Trending regimes
        if trend_strength > 0.6:  # Strong trend (ADX > 15)
            if momentum_score > 0.001:
                return MarketRegime.TRENDING_UP, min(trend_strength, 0.95)
            elif momentum_score < -0.001:
                return MarketRegime.TRENDING_DOWN, min(trend_strength, 0.95)
            else:
                # Neutral trend - check direction
                if bb_position > 0.6:
                    return MarketRegime.TRENDING_UP, trend_strength * 0.8
                elif bb_position < 0.4:
                    return MarketRegime.TRENDING_DOWN, trend_strength * 0.8
                else:
                    return MarketRegime.RANGING, 0.6

        # Volatile regime
        elif volatility_level > 0.7:  # High volatility (wide BB)
            return MarketRegime.VOLATILE, min(volatility_level, 0.9)

        # Calm regime
        elif volatility_level < 0.3 and range_bound_score > 0.6:
            return MarketRegime.CALM, min((1 - volatility_level) * range_bound_score, 0.85)

        # Ranging regime
        elif range_bound_score > 0.5 and trend_strength < 0.4:
            return MarketRegime.RANGING, min(range_bound_score, 0.8)

        # Default to ranging if unclear
        else:
            return MarketRegime.RANGING, 0.5

    def _update_regime_stability(self, regime: MarketRegime):
        """Update regime stability counters."""
        # Decay all counters
        for r in self.regime_stability:
            self.regime_stability[r] *= 0.99

        # Increment current regime
        self.regime_stability[regime] += 1

    def get_regime_stability_score(self, regime: MarketRegime) -> float:
        """Get stability score for a regime (0-1)."""
        total = sum(self.regime_stability.values())
        if total == 0:
            return 0.0
        return self.regime_stability[regime] / total

    def get_regime_transition_probability(
        self, from_regime: MarketRegime, to_regime: MarketRegime
    ) -> float:
        """Calculate probability of transitioning from one regime to another."""
        if len(self.regime_history) < 10:
            return 0.1  # Default low probability

        transitions = 0
        opportunities = 0

        prev_regime = None
        for metrics in self.regime_history:
            if prev_regime == from_regime:
                opportunities += 1
                if metrics.regime == to_regime:
                    transitions += 1
            prev_regime = metrics.regime

        if opportunities == 0:
            return 0.1

        return transitions / opportunities

    def get_market_regime_stats(self) -> Dict:
        """Get comprehensive market regime statistics."""
        if not self.regime_history:
            return {"total_regimes": 0}

        regimes = [r.regime for r in self.regime_history]
        regime_counts = {}

        for regime in MarketRegime:
            count = regimes.count(regime)
            regime_counts[regime.value] = count

        most_common = max(regime_counts, key=regime_counts.get)
        total_regimes = len(regimes)

        return {
            "total_regimes": total_regimes,
            "regime_distribution": regime_counts,
            "most_common_regime": most_common,
            "regime_stability": {r.value: self.get_regime_stability_score(r) for r in MarketRegime},
            "current_regime": self.regime_history[-1].regime.value if self.regime_history else None,
            "current_confidence": (
                self.regime_history[-1].confidence if self.regime_history else 0.0
            ),
        }


# Global market regime detector instance
_market_regime_detector: Optional[MarketRegimeDetector] = None


async def get_market_regime_detector() -> MarketRegimeDetector:
    """Get global market regime detector instance."""
    global _market_regime_detector
    if _market_regime_detector is None:
        _market_regime_detector = MarketRegimeDetector()
    return _market_regime_detector
