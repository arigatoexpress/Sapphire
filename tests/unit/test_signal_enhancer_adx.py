"""Tests for ADX regime filter wiring in SignalEnhancer.enhance().

The chain / correlation / sentiment integrations in SignalEnhancer reach for
live data; we don't need any of that for the ADX unit — we just stub
_load_state() to return the minimal "UNKNOWN" regime and exercise the ADX
code path with deterministic OHLC inputs.
"""

from __future__ import annotations

import pytest

from lib.analytics.signal_enhancer import SignalEnhancer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enhancer(monkeypatch):
    """SignalEnhancer with _load_state stubbed to return an empty state."""
    eng = SignalEnhancer()

    def _empty_state():
        return {
            "regime": "UNKNOWN",
            "regime_score": 0.0,
            "regime_confidence": 0.0,
            "funding": {},
            "decorrelations": [],
            "btc_spy_correlation": None,
            "fear_greed": None,
            "kronos": {},
            "market_intel": {},
            "_chain_snapshot": None,
        }

    monkeypatch.setattr(eng, "_load_state", _empty_state)
    return eng


def _trending_up_bars(n: int = 60):
    """Generate n bars of a clean, rising trend."""
    highs = [100 + i * 2 + 1 for i in range(n)]
    lows = [100 + i * 2 - 1 for i in range(n)]
    closes = [100 + i * 2 for i in range(n)]
    return {"highs": highs, "lows": lows, "closes": closes}


def _trending_down_bars(n: int = 60):
    highs = [200 - i * 2 + 1 for i in range(n)]
    lows = [200 - i * 2 - 1 for i in range(n)]
    closes = [200 - i * 2 for i in range(n)]
    return {"highs": highs, "lows": lows, "closes": closes}


def _ranging_bars(n: int = 80):
    """Tightly mean-reverting bars — ADX should sit below 20."""
    import random
    random.seed(42)
    closes = [100.0]
    for _ in range(n - 1):
        drift = -0.3 * (closes[-1] - 100.0) + random.uniform(-0.3, 0.3)
        closes.append(closes[-1] + drift)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    return {"highs": highs, "lows": lows, "closes": closes}


# ---------------------------------------------------------------------------
# Core ADX behaviour
# ---------------------------------------------------------------------------


def test_no_bars_skips_adx(enhancer):
    """Without bars the ADX fields stay None and confidence is untouched."""
    es = enhancer.enhance("BTC", "buy", 0.80)
    assert es.adx_value is None
    assert es.adx_regime is None
    assert es.plus_di is None
    assert es.minus_di is None
    # Confidence preserved exactly (no regime adjustments with UNKNOWN regime)
    assert es.adjusted_confidence == pytest.approx(0.80)


def test_trending_up_boosts_long(enhancer):
    """Long in an up-trending regime should get the trend boost."""
    bars = _trending_up_bars()
    es = enhancer.enhance("BTC", "buy", 0.70, bars=bars)
    assert es.adx_regime == "trending"
    assert es.adx_value is not None and es.adx_value > 25
    assert es.plus_di > es.minus_di
    # Boost ×1.10 → 0.77 (clamped under 0.99)
    assert es.adjusted_confidence == pytest.approx(0.70 * 1.10, rel=1e-3)
    assert any("reinforced" in r for r in es.reasons)


def test_trending_up_penalises_short(enhancer):
    """Short into an up-trend is a trend contradiction."""
    bars = _trending_up_bars()
    es = enhancer.enhance("BTC", "sell", 0.70, bars=bars)
    assert es.adx_regime == "trending"
    assert "adx_trend_contradiction" in es.flags
    # REGIME_PENALTY = 0.80 → 0.70 * 0.80 = 0.56
    assert es.adjusted_confidence == pytest.approx(0.70 * 0.80, rel=1e-3)


def test_trending_down_boosts_short(enhancer):
    bars = _trending_down_bars()
    es = enhancer.enhance("BTC", "sell", 0.60, bars=bars)
    assert es.adx_regime == "trending"
    assert es.minus_di > es.plus_di
    assert es.adjusted_confidence == pytest.approx(0.60 * 1.10, rel=1e-3)


def test_ranging_penalises_momentum_long(enhancer):
    """Momentum longs in a ranging regime lose 20%."""
    bars = _ranging_bars()
    es = enhancer.enhance("BTC", "buy", 0.80, bars=bars)
    assert es.adx_regime == "ranging"
    assert "adx_ranging" in es.flags
    assert es.adjusted_confidence == pytest.approx(0.80 * 0.80, rel=1e-3)


def test_flat_action_untouched_by_adx(enhancer):
    """Non-directional actions (e.g. "close") bypass direction-specific logic."""
    bars = _trending_up_bars()
    es = enhancer.enhance("BTC", "close", 0.50, bars=bars)
    # ADX regime still reported
    assert es.adx_regime == "trending"
    # but confidence is not multiplied (direction = "flat")
    assert es.adjusted_confidence == pytest.approx(0.50)


def test_bars_as_empty_dict(enhancer):
    """Empty bars dict is treated the same as no bars."""
    es = enhancer.enhance("BTC", "buy", 0.60, bars={})
    # enhance() only activates ADX when bars is truthy, so empty dict → skip
    assert es.adx_value is None
    assert es.adjusted_confidence == pytest.approx(0.60)


def test_insufficient_bars_no_crash(enhancer):
    """Too few bars → compute_adx returns None → no crash, no ADX fields."""
    bars = {"highs": [1, 2, 3], "lows": [0, 1, 2], "closes": [0.5, 1.5, 2.5]}
    es = enhancer.enhance("BTC", "buy", 0.60, bars=bars)
    assert es.adx_value is None
    assert es.adx_regime is None
    assert es.adjusted_confidence == pytest.approx(0.60)


def test_confidence_clamped_on_extreme_boost(enhancer):
    """Near-max confidence + trend boost stays ≤ MAX_CONFIDENCE."""
    bars = _trending_up_bars()
    es = enhancer.enhance("BTC", "buy", 0.95, bars=bars)
    # 0.95 * 1.10 = 1.045 → clamped to 0.99
    assert es.adjusted_confidence <= SignalEnhancer.MAX_CONFIDENCE + 1e-9


def test_alt_bars_key_names_supported(enhancer):
    """Accept singular keys ("high", "low", "close") as well."""
    bars = _trending_up_bars()
    alt = {"high": bars["highs"], "low": bars["lows"], "close": bars["closes"]}
    es = enhancer.enhance("BTC", "buy", 0.70, bars=alt)
    assert es.adx_regime == "trending"
