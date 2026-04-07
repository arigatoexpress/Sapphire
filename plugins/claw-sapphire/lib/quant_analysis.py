"""Advanced quantitative analysis — multi-timeframe, correlation, support/resistance.

Builds on technical_analysis.py with higher-order analysis:
- Multi-timeframe confluence (do 1H, 4H, 1D agree?)
- Cross-asset correlation (BTC→ETH→SOL lead/lag)
- Support/resistance detection from price pivots
- Volatility regime classification
- Trend strength scoring (ADX-like)
"""

from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from technical_analysis import OHLCV, SYMBOLS, TechnicalProfile, _fetch_ohlcv, _rsi, _sma, _atr, _ema, analyze

OPENBB_BASE = "http://127.0.0.1:6900/api/v1"


@dataclass
class SupportResistance:
    """A price level that has acted as support or resistance."""

    price: float
    strength: int  # How many times tested (more = stronger)
    type: str  # "support" | "resistance"
    last_tested: str  # Date


@dataclass
class CorrelationPair:
    """Correlation between two assets."""

    asset_a: str
    asset_b: str
    correlation: float  # -1 to 1
    period_days: int
    interpretation: str  # "strong_positive", "moderate_positive", etc.


@dataclass
class MultiTimeframeSignal:
    """Confluence signal across timeframes."""

    symbol: str
    tf_short: str  # e.g., "1H" signal
    tf_medium: str  # e.g., "4H" signal
    tf_long: str  # e.g., "1D" signal
    confluence: str  # "strong_bullish" (all agree), "mixed", "strong_bearish"
    confluence_score: float  # -1 (all bearish) to +1 (all bullish)


@dataclass
class QuantProfile:
    """Full quantitative profile combining all analysis."""

    symbol: str
    price: float
    timestamp: str

    # Technical (from technical_analysis.py)
    technical: TechnicalProfile

    # Support/Resistance
    support_levels: list[SupportResistance]
    resistance_levels: list[SupportResistance]
    nearest_support: float
    nearest_resistance: float
    risk_reward: float  # distance to resistance / distance to support

    # Trend strength
    trend_strength: float  # 0-100, ADX-like
    trend_direction: str  # "strong_up", "up", "sideways", "down", "strong_down"

    # Multi-timeframe
    mtf_signal: MultiTimeframeSignal | None


def find_support_resistance(bars: list[OHLCV], lookback: int = 5, tolerance_pct: float = 1.5) -> tuple[list[SupportResistance], list[SupportResistance]]:
    """Find support and resistance levels from price pivots.

    A pivot high is a high that's higher than `lookback` bars on either side.
    A pivot low is a low that's lower than `lookback` bars on either side.
    Levels that are tested multiple times are stronger.
    """
    if len(bars) < lookback * 2 + 1:
        return [], []

    pivot_highs = []
    pivot_lows = []

    for i in range(lookback, len(bars) - lookback):
        # Check for pivot high
        is_pivot_high = all(bars[i].high >= bars[i + j].high for j in range(-lookback, lookback + 1) if j != 0)
        if is_pivot_high:
            pivot_highs.append((bars[i].high, bars[i].date))

        # Check for pivot low
        is_pivot_low = all(bars[i].low <= bars[i + j].low for j in range(-lookback, lookback + 1) if j != 0)
        if is_pivot_low:
            pivot_lows.append((bars[i].low, bars[i].date))

    # Cluster nearby levels
    def cluster_levels(pivots: list[tuple[float, str]], level_type: str) -> list[SupportResistance]:
        if not pivots:
            return []
        pivots.sort(key=lambda x: x[0])
        clusters = []
        current_cluster = [pivots[0]]

        for i in range(1, len(pivots)):
            price, date = pivots[i]
            cluster_avg = sum(p for p, _ in current_cluster) / len(current_cluster)
            if abs(price - cluster_avg) / cluster_avg * 100 < tolerance_pct:
                current_cluster.append(pivots[i])
            else:
                avg_price = sum(p for p, _ in current_cluster) / len(current_cluster)
                clusters.append(SupportResistance(
                    price=round(avg_price, 2),
                    strength=len(current_cluster),
                    type=level_type,
                    last_tested=current_cluster[-1][1],
                ))
                current_cluster = [pivots[i]]

        if current_cluster:
            avg_price = sum(p for p, _ in current_cluster) / len(current_cluster)
            clusters.append(SupportResistance(
                price=round(avg_price, 2),
                strength=len(current_cluster),
                type=level_type,
                last_tested=current_cluster[-1][1],
            ))

        return sorted(clusters, key=lambda x: -x.strength)[:5]

    supports = cluster_levels(pivot_lows, "support")
    resistances = cluster_levels(pivot_highs, "resistance")

    return supports, resistances


def calculate_correlation(symbol_a: str, symbol_b: str, days: int = 30) -> CorrelationPair:
    """Calculate Pearson correlation between two assets' daily returns."""
    bars_a = _fetch_ohlcv(symbol_a, days + 5)
    bars_b = _fetch_ohlcv(symbol_b, days + 5)

    if len(bars_a) < 10 or len(bars_b) < 10:
        return CorrelationPair(symbol_a, symbol_b, 0, days, "insufficient_data")

    # Align by date
    dates_a = {b.date: b.close for b in bars_a}
    dates_b = {b.date: b.close for b in bars_b}
    common = sorted(set(dates_a.keys()) & set(dates_b.keys()))

    if len(common) < 5:
        return CorrelationPair(symbol_a, symbol_b, 0, days, "insufficient_overlap")

    # Calculate daily returns
    returns_a = []
    returns_b = []
    for i in range(1, len(common)):
        ra = (dates_a[common[i]] - dates_a[common[i - 1]]) / max(dates_a[common[i - 1]], 0.01)
        rb = (dates_b[common[i]] - dates_b[common[i - 1]]) / max(dates_b[common[i - 1]], 0.01)
        returns_a.append(ra)
        returns_b.append(rb)

    n = len(returns_a)
    if n < 3:
        return CorrelationPair(symbol_a, symbol_b, 0, days, "insufficient_data")

    # Pearson correlation
    mean_a = sum(returns_a) / n
    mean_b = sum(returns_b) / n
    cov = sum((returns_a[i] - mean_a) * (returns_b[i] - mean_b) for i in range(n)) / n
    std_a = (sum((r - mean_a) ** 2 for r in returns_a) / n) ** 0.5
    std_b = (sum((r - mean_b) ** 2 for r in returns_b) / n) ** 0.5

    if std_a == 0 or std_b == 0:
        corr = 0
    else:
        corr = cov / (std_a * std_b)

    corr = max(-1, min(1, corr))

    if corr > 0.7:
        interp = "strong_positive"
    elif corr > 0.3:
        interp = "moderate_positive"
    elif corr > -0.3:
        interp = "weak"
    elif corr > -0.7:
        interp = "moderate_negative"
    else:
        interp = "strong_negative"

    return CorrelationPair(symbol_a, symbol_b, round(corr, 3), days, interp)


def calculate_trend_strength(closes: list[float], period: int = 14) -> tuple[float, str]:
    """Calculate trend strength (0-100, similar to ADX).

    Uses directional movement concept:
    - High trend strength = strong directional movement
    - Low trend strength = sideways/range-bound
    """
    if len(closes) < period + 1:
        return 50, "sideways"

    # Calculate directional changes
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    pos_changes = [max(0, c) for c in changes[-period:]]
    neg_changes = [max(0, -c) for c in changes[-period:]]

    avg_pos = sum(pos_changes) / period
    avg_neg = sum(neg_changes) / period
    total = avg_pos + avg_neg

    if total == 0:
        return 0, "sideways"

    # Directional index (0-100)
    di_diff = abs(avg_pos - avg_neg) / total * 100

    # Smooth with price trend
    sma_short = sum(closes[-7:]) / 7
    sma_long = sum(closes[-20:]) / min(20, len(closes))
    trend_bias = (sma_short - sma_long) / max(sma_long, 0.01) * 100

    strength = min(100, di_diff)

    if strength > 60 and trend_bias > 1:
        direction = "strong_up"
    elif strength > 30 and trend_bias > 0.5:
        direction = "up"
    elif strength > 60 and trend_bias < -1:
        direction = "strong_down"
    elif strength > 30 and trend_bias < -0.5:
        direction = "down"
    else:
        direction = "sideways"

    return round(strength, 1), direction


def analyze_full(symbol: str) -> QuantProfile | None:
    """Full quantitative analysis including advanced metrics."""
    technical = analyze(symbol)
    if not technical:
        return None

    bars = _fetch_ohlcv(symbol, days=60)
    if len(bars) < 14:
        return None

    closes = [b.close for b in bars]
    price = closes[-1]

    # Support/Resistance
    supports, resistances = find_support_resistance(bars)

    # Nearest levels
    support_below = [s for s in supports if s.price < price]
    resistance_above = [r for r in resistances if r.price > price]
    nearest_sup = support_below[0].price if support_below else price * 0.95
    nearest_res = resistance_above[0].price if resistance_above else price * 1.05

    # Risk/Reward
    dist_to_support = price - nearest_sup
    dist_to_resistance = nearest_res - price
    rr = dist_to_resistance / max(dist_to_support, 0.01) if dist_to_support > 0 else 999

    # Trend strength
    strength, direction = calculate_trend_strength(closes)

    return QuantProfile(
        symbol=symbol,
        price=round(price, 2),
        timestamp=datetime.now(UTC).isoformat(),
        technical=technical,
        support_levels=supports,
        resistance_levels=resistances,
        nearest_support=round(nearest_sup, 2),
        nearest_resistance=round(nearest_res, 2),
        risk_reward=round(rr, 2),
        trend_strength=strength,
        trend_direction=direction,
        mtf_signal=None,  # Set by caller if TV data available
    )


def correlation_matrix() -> list[CorrelationPair]:
    """Calculate correlation matrix for all tracked assets."""
    symbols = list(SYMBOLS.keys())
    pairs = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            pairs.append(calculate_correlation(symbols[i], symbols[j], days=30))
    return pairs


if __name__ == "__main__":
    from dataclasses import asdict

    print("=" * 60)
    print("  SAPPHIRE QUANT ANALYSIS")
    print("=" * 60)

    for symbol in SYMBOLS:
        profile = analyze_full(symbol)
        if not profile:
            print(f"\n  {symbol}: No data")
            continue

        print(f"\n  {'='*50}")
        print(f"  {symbol}: ${profile.price:,.2f} | Trend: {profile.trend_direction} ({profile.trend_strength:.0f}/100)")
        print(f"  Support: ${profile.nearest_support:,.2f} | Resistance: ${profile.nearest_resistance:,.2f} | R:R = {profile.risk_reward:.1f}")

        if profile.support_levels:
            print(f"  Support levels: {', '.join(f'${s.price:,.2f} (x{s.strength})' for s in profile.support_levels[:3])}")
        if profile.resistance_levels:
            print(f"  Resistance levels: {', '.join(f'${r.price:,.2f} (x{r.strength})' for r in profile.resistance_levels[:3])}")

    print(f"\n  {'='*50}")
    print("  CORRELATION MATRIX")
    print(f"  {'='*50}")

    for pair in correlation_matrix():
        icon = "🟢" if pair.correlation > 0.5 else "🔴" if pair.correlation < -0.5 else "⚪"
        print(f"  {icon} {pair.asset_a}/{pair.asset_b}: {pair.correlation:+.3f} ({pair.interpretation})")
