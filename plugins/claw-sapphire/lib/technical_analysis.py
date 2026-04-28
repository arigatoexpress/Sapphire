"""Real technical analysis — calculated mathematically, never hallucinated.

All indicators computed from actual OHLCV data via OpenBB.
No LLM involvement in number generation.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

OPENBB_BASE = "http://127.0.0.1:6900/api/v1"

SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
}


@dataclass
class OHLCV:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TechnicalProfile:
    """Complete technical profile for one symbol — all math, no LLM."""

    symbol: str
    price: float
    timestamp: str

    # Price action
    change_24h_pct: float
    change_7d_pct: float
    high_7d: float
    low_7d: float
    range_position: float  # 0.0 = at 7d low, 1.0 = at 7d high

    # Moving averages
    sma_7: float
    sma_20: float
    sma_50: float | None  # None if not enough data
    above_sma_7: bool
    above_sma_20: bool
    ma_trend: str  # "bullish" (7>20), "bearish" (7<20), "flat"

    # RSI (14-period)
    rsi_14: float
    rsi_zone: str  # "oversold" (<30), "neutral" (30-70), "overbought" (>70)

    # Volatility
    atr_14: float  # Average True Range
    atr_pct: float  # ATR as % of price
    volatility_regime: str  # "low" (<2%), "normal" (2-5%), "high" (>5%)

    # Volume
    volume_avg_7d: float
    volume_ratio: float  # today's vol / 7d avg (>1.5 = high, <0.5 = low)
    volume_signal: str  # "high", "normal", "low"

    # Momentum
    macd_line: float
    macd_signal: float
    macd_histogram: float
    macd_cross: str  # "bullish_cross", "bearish_cross", "none"

    # Bollinger Bands
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: str  # "above_upper", "upper_half", "lower_half", "below_lower"

    # Overall
    signal_count_bullish: int
    signal_count_bearish: int
    net_signal: str  # "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"


def _fetch_ohlcv(symbol: str, days: int = 60) -> list[OHLCV]:
    """Fetch OHLCV data from OpenBB."""
    yf_symbol = SYMBOLS.get(symbol, f"{symbol}-USD")
    start = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{OPENBB_BASE}/crypto/price/historical?symbol={yf_symbol}&provider=yfinance&start_date={start}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        return [
            OHLCV(
                date=bar["date"][:10],
                open=bar.get("open", 0),
                high=bar.get("high", 0),
                low=bar.get("low", 0),
                close=bar.get("close", 0),
                volume=bar.get("volume", 0),
            )
            for bar in data.get("results", [])
        ]
    except Exception:
        return []


def _sma(closes: list[float], period: int) -> float:
    """Simple Moving Average."""
    if len(closes) < period:
        return closes[-1] if closes else 0
    return sum(closes[-period:]) / period


def _ema(closes: list[float], period: int) -> float:
    """Exponential Moving Average."""
    if len(closes) < period:
        return closes[-1] if closes else 0
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(bars: list[OHLCV], period: int = 14) -> float:
    """Average True Range."""
    if len(bars) < period + 1:
        return 0
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def _macd(closes: list[float]) -> tuple[float, float, float]:
    """MACD (12, 26, 9)."""
    if len(closes) < 26:
        return 0, 0, 0
    macd_line = _ema(closes, 12) - _ema(closes, 26)
    # Signal line needs MACD history — simplified
    signal = _ema(closes[-9:], 9) - _ema(closes[-26:], 26) if len(closes) >= 26 else macd_line
    # Better: compute MACD for each point then EMA of MACD
    macd_values = []
    for i in range(26, len(closes) + 1):
        subset = closes[:i]
        macd_values.append(_ema(subset, 12) - _ema(subset, 26))
    signal = sum(macd_values[-9:]) / min(9, len(macd_values)) if macd_values else 0
    histogram = macd_line - signal
    return macd_line, signal, histogram


def _bollinger(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[float, float, float]:
    """Bollinger Bands."""
    if len(closes) < period:
        mid = closes[-1] if closes else 0
        return mid + mid * 0.02, mid, mid - mid * 0.02
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = variance**0.5
    return mid + std_dev * std, mid, mid - std_dev * std


def analyze(symbol: str) -> TechnicalProfile | None:
    """Run full technical analysis on a symbol. Pure math, no LLM."""
    bars = _fetch_ohlcv(symbol, days=60)
    if len(bars) < 7:
        return None

    closes = [b.close for b in bars]
    price = closes[-1]
    ts = datetime.now(UTC).isoformat()

    # Price action
    day_ago = closes[-2] if len(closes) >= 2 else price
    week_ago = closes[-7] if len(closes) >= 7 else closes[0]
    change_24h = (price - day_ago) / max(day_ago, 0.01) * 100
    change_7d = (price - week_ago) / max(week_ago, 0.01) * 100
    high_7d = max(b.high for b in bars[-7:])
    low_7d = min(b.low for b in bars[-7:])
    rng = high_7d - low_7d
    range_pos = (price - low_7d) / rng if rng > 0 else 0.5

    # Moving averages
    sma7 = _sma(closes, 7)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50) if len(closes) >= 50 else None
    ma_trend = "bullish" if sma7 > sma20 else "bearish" if sma7 < sma20 * 0.998 else "flat"

    # RSI
    rsi = _rsi(closes)
    rsi_zone = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"

    # ATR / Volatility
    atr = _atr(bars)
    atr_pct = atr / max(price, 0.01) * 100
    vol_regime = "low" if atr_pct < 2 else "high" if atr_pct > 5 else "normal"

    # Volume
    volumes = [b.volume for b in bars[-7:]]
    vol_avg = sum(volumes) / len(volumes) if volumes else 1
    vol_ratio = bars[-1].volume / max(vol_avg, 1)
    vol_signal = "high" if vol_ratio > 1.5 else "low" if vol_ratio < 0.5 else "normal"

    # MACD
    macd_line, macd_sig, macd_hist = _macd(closes)
    prev_hist = 0
    if len(closes) > 27:
        prev_closes = closes[:-1]
        _, _, prev_hist = _macd(prev_closes)
    macd_cross = "none"
    if macd_hist > 0 and prev_hist <= 0:
        macd_cross = "bullish_cross"
    elif macd_hist < 0 and prev_hist >= 0:
        macd_cross = "bearish_cross"

    # Bollinger Bands
    bb_up, bb_mid, bb_low = _bollinger(closes)
    if price > bb_up:
        bb_pos = "above_upper"
    elif price > bb_mid:
        bb_pos = "upper_half"
    elif price > bb_low:
        bb_pos = "lower_half"
    else:
        bb_pos = "below_lower"

    # Signal counting
    bullish = 0
    bearish = 0

    if price > sma7:
        bullish += 1
    else:
        bearish += 1
    if price > sma20:
        bullish += 1
    else:
        bearish += 1
    if ma_trend == "bullish":
        bullish += 1
    elif ma_trend == "bearish":
        bearish += 1
    if rsi < 30:
        bullish += 1  # Oversold = potential reversal up
    elif rsi > 70:
        bearish += 1  # Overbought = potential reversal down
    if macd_hist > 0:
        bullish += 1
    else:
        bearish += 1
    if macd_cross == "bullish_cross":
        bullish += 2
    elif macd_cross == "bearish_cross":
        bearish += 2
    if vol_ratio > 1.5 and change_24h > 0:
        bullish += 1
    elif vol_ratio > 1.5 and change_24h < 0:
        bearish += 1
    if bb_pos == "below_lower":
        bullish += 1  # Oversold
    elif bb_pos == "above_upper":
        bearish += 1  # Overbought

    diff = bullish - bearish
    if diff >= 4:
        net = "strong_bullish"
    elif diff >= 2:
        net = "bullish"
    elif diff <= -4:
        net = "strong_bearish"
    elif diff <= -2:
        net = "bearish"
    else:
        net = "neutral"

    return TechnicalProfile(
        symbol=symbol,
        price=round(price, 2),
        timestamp=ts,
        change_24h_pct=round(change_24h, 2),
        change_7d_pct=round(change_7d, 2),
        high_7d=round(high_7d, 2),
        low_7d=round(low_7d, 2),
        range_position=round(range_pos, 2),
        sma_7=round(sma7, 2),
        sma_20=round(sma20, 2),
        sma_50=round(sma50, 2) if sma50 else None,
        above_sma_7=price > sma7,
        above_sma_20=price > sma20,
        ma_trend=ma_trend,
        rsi_14=round(rsi, 1),
        rsi_zone=rsi_zone,
        atr_14=round(atr, 2),
        atr_pct=round(atr_pct, 2),
        volatility_regime=vol_regime,
        volume_avg_7d=round(vol_avg, 0),
        volume_ratio=round(vol_ratio, 2),
        volume_signal=vol_signal,
        macd_line=round(macd_line, 2),
        macd_signal=round(macd_sig, 2),
        macd_histogram=round(macd_hist, 2),
        macd_cross=macd_cross,
        bb_upper=round(bb_up, 2),
        bb_middle=round(bb_mid, 2),
        bb_lower=round(bb_low, 2),
        bb_position=bb_pos,
        signal_count_bullish=bullish,
        signal_count_bearish=bearish,
        net_signal=net,
    )


def analyze_all() -> dict[str, TechnicalProfile]:
    """Analyze all tracked symbols."""
    results = {}
    for symbol in SYMBOLS:
        profile = analyze(symbol)
        if profile:
            results[symbol] = profile
    return results


if __name__ == "__main__":
    profiles = analyze_all()
    for sym, p in profiles.items():
        print(f"\n{'='*50}")
        print(f"  {sym}: ${p.price:,.2f} | {p.net_signal.upper()}")
        print(f"  24h: {p.change_24h_pct:+.1f}% | 7d: {p.change_7d_pct:+.1f}%")
        print(f"  RSI: {p.rsi_14:.0f} ({p.rsi_zone}) | MACD: {p.macd_cross}")
        print(f"  MA: {p.ma_trend} (7:{p.sma_7:,.0f} 20:{p.sma_20:,.0f})")
        print(f"  BB: {p.bb_position} | Vol: {p.volume_signal} ({p.volume_ratio:.1f}x)")
        print(f"  Signals: {p.signal_count_bullish}↑ {p.signal_count_bearish}↓")
