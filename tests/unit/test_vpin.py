"""Unit tests for lib/analytics/vpin.py (VPIN flow toxicity)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from datetime import UTC, datetime

from lib.analytics.backtest_engine import Bar, _synthetic_bars  # noqa: E402
from lib.analytics.vpin import (  # noqa: E402
    THRESHOLD_HIGH,
    VPINReading,
    classify_volume,
    classify_vpin,
    compute_vpin,
    vpin_reading,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_bar(close: float, high: float, low: float, volume: float, prev_close: float | None = None) -> Bar:
    return Bar(
        ts=datetime.now(UTC),
        open=prev_close or close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_bars(n: int, trend: float = 0.0) -> list[Bar]:
    """Build synthetic bars with a configurable price trend."""
    bars: list[Bar] = []
    price = 100.0
    for i in range(n):
        price_next = price * (1 + trend + 0.001 * (i % 3 - 1))
        bars.append(Bar(
            ts=datetime.now(UTC),
            open=price,
            high=max(price, price_next) * 1.005,
            low=min(price, price_next) * 0.995,
            close=price_next,
            volume=1_000_000.0,
        ))
        price = price_next
    return bars


# ── classify_volume ────────────────────────────────────────────────────────────


def test_classify_volume_full_buy() -> None:
    # close == high → all volume is buy
    bars = [_make_bar(close=110.0, high=110.0, low=100.0, volume=1000.0)]
    pairs = classify_volume(bars)
    assert len(pairs) == 1
    buy, sell = pairs[0]
    assert abs(buy - 1000.0) < 1e-6
    assert abs(sell) < 1e-6


def test_classify_volume_full_sell() -> None:
    # close == low → all volume is sell
    bars = [_make_bar(close=100.0, high=110.0, low=100.0, volume=1000.0)]
    pairs = classify_volume(bars)
    buy, sell = pairs[0]
    assert abs(sell - 1000.0) < 1e-6
    assert abs(buy) < 1e-6


def test_classify_volume_midpoint() -> None:
    # close == midpoint → 50/50 split
    bars = [_make_bar(close=105.0, high=110.0, low=100.0, volume=1000.0)]
    pairs = classify_volume(bars)
    buy, sell = pairs[0]
    assert abs(buy - 500.0) < 1e-6
    assert abs(sell - 500.0) < 1e-6


def test_classify_volume_tick_rule_doji() -> None:
    # high == low → tick rule applies
    prev = _make_bar(close=100.0, high=100.0, low=100.0, volume=1000.0)
    curr = _make_bar(close=101.0, high=101.0, low=101.0, volume=1000.0)
    bars = [prev, curr]
    pairs = classify_volume(bars)
    buy, sell = pairs[1]  # second bar uses tick rule
    assert buy == 1000.0  # close > prev_close → buy
    assert sell == 0.0


def test_classify_volume_buy_sell_sum_to_volume() -> None:
    bars = _synthetic_bars("BTC", 30)
    pairs = classify_volume(bars)
    for (buy, sell), bar in zip(pairs, bars, strict=False):
        total = buy + sell
        assert abs(total - bar.volume) < 1e-3, f"buy+sell={total} != volume={bar.volume}"


# ── compute_vpin ───────────────────────────────────────────────────────────────


def test_compute_vpin_range() -> None:
    bars = _synthetic_bars("BTC", 60)
    score = compute_vpin(bars)
    assert 0.0 <= score <= 1.0


def test_compute_vpin_insufficient_bars_returns_zero() -> None:
    bars = _synthetic_bars("BTC", 1)
    assert compute_vpin(bars) == 0.0


def test_compute_vpin_extreme_imbalance() -> None:
    # All bars have close == high → pure buy pressure → VPIN should be high
    bars = [_make_bar(close=100.0 + i, high=100.0 + i, low=99.0 + i, volume=1000.0)
            for i in range(60)]
    score = compute_vpin(bars)
    # All volume classified as buy → |buy-sell|/total = 1.0 for every bar
    assert score >= 0.95, f"pure-buy VPIN should be ~1.0, got {score}"


def test_compute_vpin_balanced_flow_low_score() -> None:
    # Alternating close == high and close == low → VPIN close to 1.0 per bar
    # but we want to test the midpoint case → low VPIN
    bars = [_make_bar(close=105.0, high=110.0, low=100.0, volume=1000.0)
            for _ in range(60)]
    score = compute_vpin(bars)
    # All at midpoint → 50/50 buy/sell → imbalance = 0
    assert score < 0.05, f"balanced flow VPIN should be near 0, got {score}"


def test_compute_vpin_n_buckets_respected() -> None:
    # Using more buckets should smooth the score
    bars = _synthetic_bars("BTC", 100)
    s50 = compute_vpin(bars, n_buckets=50)
    s10 = compute_vpin(bars, n_buckets=10)
    # Both in range; different windows may differ
    assert 0.0 <= s50 <= 1.0
    assert 0.0 <= s10 <= 1.0


# ── classify_vpin ──────────────────────────────────────────────────────────────


def test_classify_vpin_normal() -> None:
    r = classify_vpin(0.30)
    assert r.toxicity == "normal"
    assert r.flag is None


def test_classify_vpin_moderate() -> None:
    r = classify_vpin(0.55)
    assert r.toxicity == "moderate"
    assert r.flag is None


def test_classify_vpin_high() -> None:
    r = classify_vpin(0.75)
    assert r.toxicity == "high"
    assert r.flag == "high_flow_toxicity"


def test_classify_vpin_extreme() -> None:
    r = classify_vpin(0.90)
    assert r.toxicity == "extreme"
    assert r.flag == "extreme_flow_toxicity"


def test_classify_vpin_boundaries() -> None:
    # Exactly at threshold → high (not moderate)
    r = classify_vpin(THRESHOLD_HIGH)
    assert r.toxicity == "high"

    # Just below → moderate
    r2 = classify_vpin(THRESHOLD_HIGH - 0.001)
    assert r2.toxicity == "moderate"


# ── vpin_reading ───────────────────────────────────────────────────────────────


def test_vpin_reading_returns_structured_result() -> None:
    bars = _synthetic_bars("BTC", 60)
    reading = vpin_reading(bars)
    assert isinstance(reading, VPINReading)
    assert 0.0 <= reading.score <= 1.0
    assert reading.toxicity in {"normal", "moderate", "high", "extreme"}
    assert reading.n_bars_used > 0
