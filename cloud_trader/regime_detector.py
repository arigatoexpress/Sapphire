"""Simple regime detection from OHLCV data."""

from typing import Optional
import statistics


def detect_regime(
    closes: list,
    highs: list,
    lows: list,
    volumes: Optional[list] = None,
    ema_short_period: int = 10,
    ema_long_period: int = 50,
    atr_period: int = 14,
) -> str:
    """
    Detect market regime from OHLCV data.
    
    Args:
        closes: List of close prices (most recent last)
        highs: List of high prices
        lows: List of low prices
        volumes: Optional list of volumes
        ema_short_period: Short EMA period
        ema_long_period: Long EMA period
        atr_period: ATR calculation period
        
    Returns:
        One of: "trending_up", "trending_down", "ranging", "volatile"
    """
    if len(closes) < ema_long_period:
        return "ranging"  # Not enough data

    # Calculate EMAs
    ema_short = _calculate_ema(closes, ema_short_period)
    ema_long = _calculate_ema(closes, ema_long_period)
    
    # Calculate ATR
    atr = _calculate_atr(highs, lows, closes, atr_period)
    current_price = closes[-1]
    atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
    
    # Calculate trend strength (EMA difference as % of price)
    ema_diff_pct = ((ema_short - ema_long) / current_price) * 100 if current_price > 0 else 0
    
    # Decision logic
    # High volatility (ATR > 3% of price) = volatile
    if atr_pct > 3.0:
        return "volatile"
    
    # Strong trend (EMA diff > 2%)
    if abs(ema_diff_pct) > 2.0:
        return "trending_up" if ema_diff_pct > 0 else "trending_down"
    
    # Moderate trend (EMA diff > 0.5%)
    if abs(ema_diff_pct) > 0.5:
        return "trending_up" if ema_diff_pct > 0 else "trending_down"
    
    # Otherwise ranging
    return "ranging"


def _calculate_ema(prices: list, period: int) -> float:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # SMA for first period
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def _calculate_atr(highs: list, lows: list, closes: list, period: int) -> float:
    """Calculate Average True Range."""
    if len(closes) < 2:
        return 0.0
    
    true_ranges = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return statistics.mean(true_ranges) if true_ranges else 0.0
    
    # Use recent ATR period
    return statistics.mean(true_ranges[-period:])


def calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Public ATR calculation for TP/SL."""
    return _calculate_atr(highs, lows, closes, period)


def get_regime_bias(regime: str) -> dict:
    """
    Get trading bias based on regime.
    
    Returns:
        Dict with recommended agent activation pattern.
    """
    biases = {
        "trending_up": {
            "momentum": 1.2,      # Boost momentum agent
            "market_maker": 0.8,  # Reduce market maker
            "swing": 1.0,         # Normal for swing
            "recommendation": "Favor long momentum entries",
        },
        "trending_down": {
            "momentum": 1.2,
            "market_maker": 0.8,
            "swing": 1.0,
            "recommendation": "Favor short momentum entries",
        },
        "ranging": {
            "momentum": 0.7,      # Reduce momentum (false breakouts)
            "market_maker": 1.3,  # Boost market maker
            "swing": 0.8,
            "recommendation": "Market maker thrives, avoid momentum",
        },
        "volatile": {
            "momentum": 0.5,      # Reduce all
            "market_maker": 0.6,
            "swing": 0.4,
            "recommendation": "Reduce position sizes, tighten stops",
        },
    }
    return biases.get(regime, biases["ranging"])
