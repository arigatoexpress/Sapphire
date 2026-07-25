"""SignalEnhancer must read the FLAT chain snapshot shape.

`ChainIntelligence.snapshot()` emits a flat dict (`classification`,
`btc_funding_rate_pct`, …). The enhancer used to read a nested shape
(`snap["regime"]["state"]`, `snap["funding"]["perps"]`) that snapshot() has
never produced, so regime silently resolved to "UNKNOWN" and the funding map
was always empty — REGIME_PENALTY, REGIME_BOOST and crowded-entry detection
could never fire. These tests pin the real shape so the drift cannot return.
"""

from __future__ import annotations

import pytest

from lib.analytics.signal_enhancer import (
    SignalEnhancer,
    _base_symbol,
    _build_funding_map,
    _funding_flag,
)


def _flat_snapshot(
    *,
    regime: str = "NEUTRAL",
    score: float = 0.0,
    inputs_ok: int = 6,
    inputs_total: int = 6,
    btc_pct: float | None = 0.01,
    eth_pct: float | None = 0.01,
) -> dict:
    """A snapshot in the shape ChainIntelligence.snapshot() actually returns."""
    return {
        "fear_greed": 50,
        "btc_dominance": 56.5,
        "btc_funding_rate_pct": btc_pct,
        "eth_funding_rate_pct": eth_pct,
        "classification": {
            "regime": regime,
            "score": score,
            "inputs_ok": inputs_ok,
            "inputs_total": inputs_total,
        },
    }


@pytest.fixture
def enhancer(monkeypatch):
    """Enhancer with chain state stubbed to a flat snapshot, everything else off."""

    def _make(snapshot: dict) -> SignalEnhancer:
        e = SignalEnhancer()
        state = {
            "regime": "UNKNOWN",
            "regime_score": 0.0,
            "regime_confidence": 0.0,
            "funding": {},
            "decorrelations": [],
            "btc_spy_correlation": None,
            "fear_greed": None,
            "kronos": {},
            "_chain_snapshot": snapshot,
        }
        clf = snapshot["classification"]
        state["regime"] = str(clf["regime"])
        state["regime_score"] = float(clf["score"])
        state["regime_confidence"] = float(clf["inputs_ok"]) / float(clf["inputs_total"])
        state["funding"] = _build_funding_map(snapshot)
        monkeypatch.setattr(e, "_load_state", lambda: state)
        return e

    return _make


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTC", "BTC"),
        ("btc", "BTC"),
        ("BTC-USD", "BTC"),
        ("BTCUSDT", "BTC"),
        ("BTCUSD", "BTC"),
        ("ETH-PERP", "ETH"),
        ("SOL", "SOL"),
    ],
)
def test_base_symbol_strips_quote_suffixes(raw, expected):
    assert _base_symbol(raw) == expected


def test_base_symbol_does_not_eat_a_whole_symbol():
    # "USD" itself must not reduce to the empty string.
    assert _base_symbol("USD") == "USD"


# ---------------------------------------------------------------------------
# Funding map — units and flags
# ---------------------------------------------------------------------------


def test_funding_map_converts_percent_to_fraction():
    # enhance() renders the stored rate as rate * 100, so it must hold a
    # fraction. 0.05% in the snapshot -> 0.0005 stored.
    fmap = _build_funding_map(_flat_snapshot(btc_pct=0.05, eth_pct=None))
    rate, _flag = fmap["BTC"]
    assert rate == pytest.approx(0.0005)
    assert "ETH" not in fmap


def test_funding_map_skips_missing_and_unparsable_rates():
    snap = _flat_snapshot(btc_pct=None, eth_pct="not_a_number")
    assert _build_funding_map(snap) == {}


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (0.08, "crowded_long"),
        (0.05, "crowded_long"),
        (-0.05, "crowded_short"),
        (-0.09, "crowded_short"),
        (0.03, "elevated_long"),
        (-0.03, "elevated_short"),
        (0.01, None),
        (0.0, None),
    ],
)
def test_funding_flag_thresholds(pct, expected):
    assert _funding_flag(pct) == expected


# ---------------------------------------------------------------------------
# Regime penalty / boost actually fire off the flat shape
# ---------------------------------------------------------------------------


def test_long_in_risk_off_is_penalized(enhancer):
    e = enhancer(_flat_snapshot(regime="RISK_OFF", score=-0.6))
    r = e.enhance("BTC", "buy", 0.80)
    assert r.regime == "RISK_OFF"
    assert "regime_contradiction" in r.flags
    assert r.adjusted_confidence == pytest.approx(0.80 * SignalEnhancer.REGIME_PENALTY)


def test_short_in_risk_on_is_penalized(enhancer):
    e = enhancer(_flat_snapshot(regime="RISK_ON", score=0.6))
    r = e.enhance("BTC", "sell", 0.80)
    assert "regime_contradiction" in r.flags
    assert r.adjusted_confidence == pytest.approx(0.80 * SignalEnhancer.REGIME_PENALTY)


def test_long_aligned_with_risk_on_is_boosted(enhancer):
    e = enhancer(_flat_snapshot(regime="RISK_ON", score=0.6, inputs_ok=6, inputs_total=6))
    r = e.enhance("BTC", "buy", 0.50)
    assert r.regime_confidence == pytest.approx(1.0)
    assert r.adjusted_confidence == pytest.approx(0.50 * SignalEnhancer.REGIME_BOOST)


def test_boost_withheld_when_regime_confidence_is_low(enhancer):
    # Only 2 of 6 inputs resolved -> 33% confidence, below the 0.5 gate.
    e = enhancer(_flat_snapshot(regime="RISK_ON", score=0.6, inputs_ok=2, inputs_total=6))
    r = e.enhance("BTC", "buy", 0.50)
    # EnhancedSignal rounds regime_confidence to 3dp.
    assert r.regime_confidence == pytest.approx(2 / 6, abs=1e-3)
    assert r.adjusted_confidence == pytest.approx(0.50)


def test_neutral_regime_neither_penalizes_nor_boosts(enhancer):
    e = enhancer(_flat_snapshot(regime="NEUTRAL", score=0.0))
    r = e.enhance("BTC", "buy", 0.70)
    assert r.adjusted_confidence == pytest.approx(0.70)
    assert "regime_contradiction" not in r.flags


# ---------------------------------------------------------------------------
# Crowded-entry detection
# ---------------------------------------------------------------------------


def test_crowded_long_flagged_on_extreme_positive_funding(enhancer):
    e = enhancer(_flat_snapshot(btc_pct=0.09))
    r = e.enhance("BTC", "buy", 0.80)
    assert r.funding_flag == "crowded_long"
    assert "crowded_entry" in r.flags


def test_crowded_short_flagged_on_extreme_negative_funding(enhancer):
    e = enhancer(_flat_snapshot(btc_pct=-0.09))
    r = e.enhance("BTC", "sell", 0.80)
    assert r.funding_flag == "crowded_short"
    assert "crowded_entry" in r.flags


def test_crowded_entry_not_flagged_when_direction_opposes_the_crowd(enhancer):
    # Extreme positive funding + a SHORT is the contrarian side, not crowded.
    e = enhancer(_flat_snapshot(btc_pct=0.09))
    r = e.enhance("BTC", "sell", 0.80)
    assert r.funding_flag == "crowded_long"
    assert "crowded_entry" not in r.flags


def test_funding_resolves_through_a_venue_suffixed_symbol(enhancer):
    e = enhancer(_flat_snapshot(btc_pct=0.09))
    r = e.enhance("BTC-USD", "buy", 0.80)
    assert r.funding_flag == "crowded_long"


def test_symbol_without_funding_data_is_left_alone(enhancer):
    e = enhancer(_flat_snapshot())
    r = e.enhance("SOL", "buy", 0.80)
    assert r.funding_rate is None
    assert r.funding_flag is None


# ---------------------------------------------------------------------------
# Regime enum round-trip
# ---------------------------------------------------------------------------


def test_regime_enum_is_unwrapped_to_its_value(enhancer, monkeypatch):
    from lib.chain.intelligence import Regime

    e = SignalEnhancer()
    snap = _flat_snapshot(regime="RISK_OFF", score=-0.6)
    snap["classification"]["regime"] = Regime.RISK_OFF  # in-process: an enum

    monkeypatch.setattr(
        "lib.chain.ChainIntelligence.snapshot", lambda self, *a, **k: snap, raising=False
    )
    state = e._load_state()
    assert state["regime"] == "RISK_OFF"
    assert state["regime_score"] == pytest.approx(-0.6)
