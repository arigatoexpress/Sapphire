"""Unit tests for lib/analytics/indicators.py (ATR, ADX)."""

from __future__ import annotations

import math
import random

import pytest

from lib.analytics.indicators import (
    classify_adx_regime,
    compute_adx,
    compute_atr,
    compute_true_range,
)

# ---------------------------------------------------------------------------
# True Range / ATR
# ---------------------------------------------------------------------------


def test_true_range_basic():
    # H=105, L=95, PC=100 → max(10, 5, 5) = 10
    assert compute_true_range(105, 95, 100) == 10

    # Gap up: H=110, L=106, PC=100 → max(4, 10, 6) = 10
    assert compute_true_range(110, 106, 100) == 10

    # Gap down: H=95, L=90, PC=100 → max(5, 5, 10) = 10
    assert compute_true_range(95, 90, 100) == 10


def test_atr_returns_none_when_insufficient_data():
    assert compute_atr([1, 2], [1, 2], [1, 2], period=14) is None


def test_atr_constant_range():
    # 30 bars of 5-point range → ATR should converge to 5
    highs = [105] * 30
    lows = [100] * 30
    closes = [102] * 30
    atr = compute_atr(highs, lows, closes, period=14)
    assert atr is not None
    # Constant H-L=5 and constant close → TR dominated by H-L
    assert abs(atr - 5.0) < 0.5


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------


def test_adx_returns_none_when_insufficient_data():
    # Need 2 * period + 1 = 29 bars
    highs = [i + 1 for i in range(20)]
    lows = [i for i in range(20)]
    closes = [i + 0.5 for i in range(20)]
    assert compute_adx(highs, lows, closes) is None


def test_adx_strong_uptrend():
    # Monotonically rising price — ADX should be very high, +DI >> -DI
    n = 60
    highs = [100 + i * 2 + 1 for i in range(n)]
    lows = [100 + i * 2 - 1 for i in range(n)]
    closes = [100 + i * 2 for i in range(n)]

    res = compute_adx(highs, lows, closes, period=14)
    assert res is not None
    assert res["adx"] > 40.0, f"expected strong trend ADX>40, got {res['adx']}"
    assert res["plus_di"] > res["minus_di"]
    assert classify_adx_regime(res["adx"]) == "trending"


def test_adx_strong_downtrend():
    # Monotonically falling price — -DI >> +DI
    n = 60
    highs = [200 - i * 2 + 1 for i in range(n)]
    lows = [200 - i * 2 - 1 for i in range(n)]
    closes = [200 - i * 2 for i in range(n)]

    res = compute_adx(highs, lows, closes, period=14)
    assert res is not None
    assert res["adx"] > 40.0
    assert res["minus_di"] > res["plus_di"]


def test_adx_choppy_range():
    # Mean-reverting noise around a flat price — ADX should be low
    random.seed(42)
    n = 80
    closes = [100.0]
    for _ in range(n - 1):
        # Strong mean reversion: tiny random walk centered on 100
        drift = -0.3 * (closes[-1] - 100.0) + random.uniform(-0.3, 0.3)
        closes.append(closes[-1] + drift)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]

    res = compute_adx(highs, lows, closes, period=14)
    assert res is not None
    # Ranging regimes historically come out well below the 25 threshold
    assert res["adx"] < 25.0, f"expected low ADX for chop, got {res['adx']}"


def test_adx_values_bounded():
    # ADX and DIs must stay in [0, 100]
    random.seed(7)
    n = 100
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + random.gauss(0, 0.01)))
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]

    res = compute_adx(highs, lows, closes)
    assert res is not None
    assert 0 <= res["adx"] <= 100
    assert 0 <= res["plus_di"] <= 100
    assert 0 <= res["minus_di"] <= 100
    assert not math.isnan(res["adx"])


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("adx", "expected"),
    [
        (None, "unknown"),
        (0.0, "ranging"),
        (15.0, "ranging"),
        (19.99, "ranging"),
        (20.0, "transition"),
        (22.0, "transition"),
        (25.0, "trending"),
        (50.0, "trending"),
        (100.0, "trending"),
    ],
)
def test_classify_adx_regime(adx, expected):
    assert classify_adx_regime(adx) == expected
