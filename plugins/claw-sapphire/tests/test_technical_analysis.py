"""Tests for technical analysis library — pure math verification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from technical_analysis import _bollinger, _ema, _rsi, _sma


def test_sma_basic():
    """SMA of [1,2,3,4,5] period 3 = (3+4+5)/3 = 4.0."""
    assert _sma([1, 2, 3, 4, 5], 3) == 4.0


def test_sma_single():
    """SMA of single value."""
    assert _sma([42], 1) == 42.0


def test_sma_short_data():
    """SMA with less data than period returns last value."""
    assert _sma([10, 20], 5) == 20


def test_ema_basic():
    """EMA should be close to SMA for uniform data."""
    data = [100] * 20
    ema = _ema(data, 10)
    assert abs(ema - 100) < 0.01


def test_ema_trending():
    """EMA of rising data should be between oldest and newest."""
    data = list(range(1, 21))  # 1 to 20
    ema = _ema(data, 10)
    assert 10 < ema < 20  # Between middle and end


def test_rsi_neutral():
    """RSI of oscillating data should be ~50."""
    data = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101]
    rsi = _rsi(data)
    assert 45 <= rsi <= 55


def test_rsi_all_up():
    """RSI of purely rising data should be 100."""
    data = list(range(100, 120))
    rsi = _rsi(data)
    assert rsi == 100.0


def test_rsi_all_down():
    """RSI of purely falling data should be near 0."""
    data = list(range(120, 100, -1))
    rsi = _rsi(data)
    assert rsi < 5


def test_rsi_range():
    """RSI should always be 0-100."""
    for data in [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
                  [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                  [100] * 20]:
        rsi = _rsi(data)
        assert 0 <= rsi <= 100, f"RSI {rsi} out of range for {data[:5]}..."


def test_bollinger_basic():
    """Bollinger bands should have upper > middle > lower."""
    data = [100 + i % 5 for i in range(30)]
    upper, middle, lower = _bollinger(data)
    assert upper > middle > lower


def test_bollinger_tight():
    """Flat data should have tight bands."""
    data = [100.0] * 25
    upper, middle, lower = _bollinger(data)
    assert abs(upper - lower) < 1  # Very tight


def test_bollinger_wide():
    """Volatile data should have wide bands."""
    data = [100 if i % 2 == 0 else 200 for i in range(25)]
    upper, middle, lower = _bollinger(data)
    assert upper - lower > 50  # Wide bands
