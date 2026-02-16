"""
UMEP - Asset State Encoder

Encodes individual asset state from raw market data into the
AssetState component of the MarketStateTensor.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..market_state_tensor import AssetState, TrendStrength

logger = logging.getLogger(__name__)


@dataclass
class OHLCVCandle:
    """Single OHLCV candle."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class AssetEncoder:
    """
    Encodes raw market data into AssetState.

    Computes:
    - Momentum (rate of change normalized to -1 to 1)
    - Volatility percentile
    - Trend strength and direction
    - Support/resistance distances
    """

    def __init__(self):
        # Historical volatility for percentile calculation
        self._volatility_history: Dict[str, List[float]] = {}

    def encode(
        self,
        symbol: str,
        current_price: float,
        price_1h_ago: Optional[float] = None,
        price_4h_ago: Optional[float] = None,
        price_24h_ago: Optional[float] = None,
        price_7d_ago: Optional[float] = None,
        recent_candles: Optional[List[OHLCVCandle]] = None,
        support_level: Optional[float] = None,
        resistance_level: Optional[float] = None,
        avg_volume_20d: Optional[float] = None,
    ) -> AssetState:
        """
        Encode asset state from raw market data.

        Args:
            symbol: Asset symbol
            current_price: Current price
            price_*_ago: Historical prices for momentum calculation
            recent_candles: Recent OHLCV candles for volatility
            support_level: Nearest support price
            resistance_level: Nearest resistance price
            avg_volume_20d: 20-day average volume for ratio
        """
        state = AssetState(symbol=symbol, price=current_price)

        # Calculate price changes
        if price_24h_ago and price_24h_ago > 0:
            state.change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100

        if price_7d_ago and price_7d_ago > 0:
            state.change_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

        # Calculate momentum (normalized -1 to 1)
        state.momentum_1h = self._calculate_momentum(current_price, price_1h_ago, scale=0.05)
        state.momentum_4h = self._calculate_momentum(current_price, price_4h_ago, scale=0.10)
        state.momentum_1d = self._calculate_momentum(current_price, price_24h_ago, scale=0.20)

        # Calculate volatility
        if recent_candles:
            atr = self._calculate_atr(recent_candles)
            state.atr_percent = (atr / current_price) * 100 if current_price > 0 else 0
            state.volatility_percentile = self._calculate_volatility_percentile(
                symbol, state.atr_percent
            )

        # Determine trend
        state.trend_direction, state.trend_strength = self._determine_trend(
            state.momentum_1h, state.momentum_4h, state.momentum_1d
        )

        # Calculate support/resistance distances
        if support_level and support_level > 0:
            state.nearest_support_pct = ((current_price - support_level) / current_price) * 100

        if resistance_level and resistance_level > 0:
            state.nearest_resistance_pct = (
                (resistance_level - current_price) / current_price
            ) * 100

        # Volume ratio
        if recent_candles and avg_volume_20d and avg_volume_20d > 0:
            recent_volume = sum(c.volume for c in recent_candles[-5:]) / 5  # Last 5 candles avg
            state.volume_ratio = recent_volume / avg_volume_20d

        return state

    def _calculate_momentum(
        self, current: float, historical: Optional[float], scale: float = 0.1
    ) -> float:
        """
        Calculate normalized momentum.

        Returns value between -1 and 1, where:
        - 1 = very bullish (price up by 'scale' or more)
        - -1 = very bearish (price down by 'scale' or more)
        - 0 = unchanged
        """
        if not historical or historical <= 0:
            return 0.0

        pct_change = (current - historical) / historical

        # Normalize to -1 to 1 using tanh-like scaling
        normalized = pct_change / scale

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, normalized))

    def _calculate_atr(self, candles: List[OHLCVCandle], period: int = 14) -> float:
        """Calculate Average True Range."""
        if len(candles) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, min(len(candles), period + 1)):
            current = candles[i]
            previous = candles[i - 1]

            tr = max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
            true_ranges.append(tr)

        return statistics.mean(true_ranges) if true_ranges else 0.0

    def _calculate_volatility_percentile(self, symbol: str, current_vol: float) -> float:
        """Calculate volatility percentile compared to history."""
        # Update history
        if symbol not in self._volatility_history:
            self._volatility_history[symbol] = []

        history = self._volatility_history[symbol]
        history.append(current_vol)

        # Keep last 100 readings
        if len(history) > 100:
            self._volatility_history[symbol] = history[-100:]
            history = self._volatility_history[symbol]

        if len(history) < 5:
            return 50.0  # Default to median if not enough history

        # Calculate percentile
        sorted_history = sorted(history)
        position = sum(1 for v in sorted_history if v <= current_vol)
        percentile = (position / len(sorted_history)) * 100

        return percentile

    def _determine_trend(self, mom_1h: float, mom_4h: float, mom_1d: float) -> tuple:
        """
        Determine trend direction and strength from momentum.

        Returns: (direction, strength)
        """
        # Average momentum across timeframes
        avg_momentum = (mom_1h + mom_4h + mom_1d) / 3

        # Determine direction
        if avg_momentum > 0.1:
            direction = "up"
        elif avg_momentum < -0.1:
            direction = "down"
        else:
            direction = "neutral"

        # Determine strength based on alignment
        same_direction = (mom_1h > 0 and mom_4h > 0 and mom_1d > 0) or (
            mom_1h < 0 and mom_4h < 0 and mom_1d < 0
        )

        abs_sum = abs(mom_1h) + abs(mom_4h) + abs(mom_1d)

        if same_direction and abs_sum > 1.5:
            strength = TrendStrength.STRONG
        elif same_direction and abs_sum > 0.5:
            strength = TrendStrength.MODERATE
        elif abs_sum > 0.3:
            strength = TrendStrength.WEAK
        else:
            strength = TrendStrength.NONE

        return direction, strength

    def encode_from_dict(self, symbol: str, data: Dict[str, Any]) -> AssetState:
        """
        Convenience method to encode from a dictionary.

        Expected keys: price, price_1h, price_4h, price_24h, price_7d,
                       support, resistance, avg_volume
        """
        return self.encode(
            symbol=symbol,
            current_price=data.get("price", 0),
            price_1h_ago=data.get("price_1h"),
            price_4h_ago=data.get("price_4h"),
            price_24h_ago=data.get("price_24h"),
            price_7d_ago=data.get("price_7d"),
            support_level=data.get("support"),
            resistance_level=data.get("resistance"),
            avg_volume_20d=data.get("avg_volume"),
        )


# Global encoder instance
_encoder: Optional[AssetEncoder] = None


def get_asset_encoder() -> AssetEncoder:
    """Get global AssetEncoder instance."""
    global _encoder
    if _encoder is None:
        _encoder = AssetEncoder()
    return _encoder
