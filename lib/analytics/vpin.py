"""VPIN — Volume-Synchronized Probability of Informed Trading.

Uses the Lee-Ready bulk classification approximation on OHLCV bars to split
each bar's volume into buy and sell buckets, then computes VPIN as the rolling
average of flow imbalance across the last ``n_buckets`` bars.

  buy_vol  ≈ volume × (close - low)  / (high - low)
  sell_vol ≈ volume × (high - close) / (high - low)
  tick rule fallback when high == low: close > prev_close → buy, else sell

  VPIN[t] = mean(|buy_vol[i] - sell_vol[i]| / total_vol[i], i ∈ [t-n+1, t])

VPIN ∈ [0, 1]. Thresholds (industry convention):
  > 0.7 → high flow toxicity (informed trading dominates, execution risk elevated)
  > 0.5 → moderate flow toxicity
  ≤ 0.5 → normal

Wire into SignalEnhancer to reduce confidence and flag signals during toxic flow.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lib.analytics.backtest_engine import Bar


# ── Core computation ───────────────────────────────────────────────────────────


def classify_volume(bars: list[Bar]) -> list[tuple[float, float]]:
    """Return (buy_vol, sell_vol) pairs using Lee-Ready bulk classification.

    For each bar after the first:
    - If high > low: split proportionally by position of close within range.
    - Else (doji / same H=L): use tick rule vs. previous close.
    """
    result: list[tuple[float, float]] = []
    for i, bar in enumerate(bars):
        vol = bar.volume
        hi, lo, cl = bar.high, bar.low, bar.close
        hl_range = hi - lo

        if hl_range > 0:
            buy_frac = (cl - lo) / hl_range
        else:
            # Tick rule: compare to previous close
            if i > 0:
                buy_frac = 1.0 if cl > bars[i - 1].close else 0.0
            else:
                buy_frac = 0.5  # first bar — no prior, assume neutral

        buy_vol = vol * buy_frac
        sell_vol = vol * (1.0 - buy_frac)
        result.append((buy_vol, sell_vol))
    return result


def compute_vpin(bars: list[Bar], n_buckets: int = 50) -> float:
    """Compute VPIN for the most recent ``n_buckets`` bars.

    Args:
        bars: OHLCV bar list (daily or intraday).
        n_buckets: Rolling window length. Default 50 (standard academic choice).

    Returns:
        VPIN score in [0, 1]. Returns 0.0 if insufficient bars.
    """
    if len(bars) < 2:
        return 0.0

    classified = classify_volume(bars)
    window = classified[-n_buckets:]  # use most recent n_buckets

    imbalances: list[float] = []
    for buy_vol, sell_vol in window:
        total = buy_vol + sell_vol
        if total > 0:
            imbalances.append(abs(buy_vol - sell_vol) / total)
        # zero-volume bar: skip (don't push 0.0 — distorts average)

    if not imbalances:
        return 0.0

    return sum(imbalances) / len(imbalances)


def compute_vpin_from_bars(bars: list[Bar], n_buckets: int = 50) -> float:
    """Alias for ``compute_vpin`` — used by SignalEnhancer integration."""
    return compute_vpin(bars, n_buckets=n_buckets)


# ── Toxicity classifier ────────────────────────────────────────────────────────

THRESHOLD_HIGH = 0.70
THRESHOLD_MODERATE = 0.50


@dataclass
class VPINReading:
    score: float  # VPIN in [0, 1]
    toxicity: str  # normal | moderate | high | extreme
    flag: str | None  # None | high_flow_toxicity | extreme_flow_toxicity
    n_bars_used: int


def classify_vpin(score: float, n_bars_used: int = 0) -> VPINReading:
    """Translate raw VPIN score into a structured toxicity reading."""
    if score >= 0.85:
        return VPINReading(
            score=round(score, 4),
            toxicity="extreme",
            flag="extreme_flow_toxicity",
            n_bars_used=n_bars_used,
        )
    if score >= THRESHOLD_HIGH:
        return VPINReading(
            score=round(score, 4),
            toxicity="high",
            flag="high_flow_toxicity",
            n_bars_used=n_bars_used,
        )
    if score >= THRESHOLD_MODERATE:
        return VPINReading(
            score=round(score, 4), toxicity="moderate", flag=None, n_bars_used=n_bars_used
        )
    return VPINReading(score=round(score, 4), toxicity="normal", flag=None, n_bars_used=n_bars_used)


def vpin_reading(bars: list[Bar], n_buckets: int = 50) -> VPINReading:
    """Compute and classify VPIN from a bar list in one call."""
    score = compute_vpin(bars, n_buckets=n_buckets)
    return classify_vpin(score, n_bars_used=min(len(bars), n_buckets))


# ── Per-symbol cache (used by SignalEnhancer) ──────────────────────────────────


class VPINCache:
    """Thread-safe per-symbol VPIN cache with configurable TTL."""

    TTL_SECS = 300
    DEFAULT_DAYS = 30
    DEFAULT_BUCKETS = 50

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[VPINReading, float]] = {}

    def get(self, symbol: str) -> VPINReading | None:
        """Return cached reading if still fresh, else fetch and recompute."""
        now = time.time()
        with self._lock:
            cached = self._cache.get(symbol)
            if cached and (now - cached[1]) < self.TTL_SECS:
                return cached[0]

        try:
            from lib.analytics.backtest_engine import fetch_ohlcv

            ticker = symbol if "-" in symbol else f"{symbol}-USD"
            bars = fetch_ohlcv(ticker, days=self.DEFAULT_DAYS)
            reading = vpin_reading(bars, n_buckets=self.DEFAULT_BUCKETS)
            with self._lock:
                self._cache[symbol] = (reading, now)
            return reading
        except Exception as e:
            log.debug("VPIN fetch failed for %s: %s", symbol, e)
            return None


# Module-level singleton
_vpin_cache: VPINCache | None = None
_cache_lock = threading.Lock()


def get_vpin_cache() -> VPINCache:
    global _vpin_cache
    with _cache_lock:
        if _vpin_cache is None:
            _vpin_cache = VPINCache()
    return _vpin_cache


__all__ = [
    "VPINCache",
    "VPINReading",
    "classify_vpin",
    "classify_volume",
    "compute_vpin",
    "compute_vpin_from_bars",
    "get_vpin_cache",
    "vpin_reading",
    "THRESHOLD_HIGH",
    "THRESHOLD_MODERATE",
]
