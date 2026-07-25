"""Sentiment composite must read the FLAT ChainIntelligence.snapshot() shape.

Regression guard for the flat-vs-nested key bug: compute_sentiment used to read
`snap["overview"]`, `snap["funding"]`, `snap["open_interest"]`,
`snap["stablecoins"]` and `snap["regime"]`. None of those keys exist on
`ChainIntelligence.snapshot()` output, so every sub-score silently fell back to
its neutral default and the composite was pinned near 50 regardless of the
market. The failure was invisible because a hardcoded 50 is indistinguishable
from a genuine neutral reading.
"""

from lib.analytics.sentiment import compute_sentiment

# Mirrors a real ChainIntelligence.snapshot() payload (fearful market).
FLAT_SNAPSHOT_FEAR = {
    "timestamp": "2026-07-25T08:28:04+00:00",
    "unix_ts": 1785054484,
    "fear_greed": 27,
    "fear_greed_label": "Fear",
    "btc_dominance": 56.538,
    "btc_dominance_24h_change": -0.027,
    "total_mcap_usd": 3.1e12,
    "total_mcap_24h_change_pct": 0.14,
    "btc_funding_rate_pct": None,
    "eth_funding_rate_pct": None,
    "dxy": 101.47,
    "dxy_1d_change_pct": 0.04,
    "vix": 18.58,
    "vix_1d_change_pct": 0.5,
    "classification": {
        "regime": "NEUTRAL",
        "score": -0.062,
        "reasons": ["Fear&Greed=27 (fear)"],
        "inputs_ok": 5,
        "inputs_total": 6,
    },
}


def _greedy_snapshot() -> dict:
    snap = dict(FLAT_SNAPSHOT_FEAR)
    snap["fear_greed"] = 88
    snap["btc_dominance"] = 42.0
    snap["btc_funding_rate_pct"] = 0.06
    snap["eth_funding_rate_pct"] = 0.05
    snap["classification"] = dict(FLAT_SNAPSHOT_FEAR["classification"])
    snap["classification"]["regime"] = "RISK_ON"
    snap["classification"]["score"] = 0.72
    return snap


def test_fearful_market_is_not_reported_as_neutral():
    """The headline bug: a fearful snapshot must not score the neutral default.

    This snapshot is a genuine blend — F&G 27 is fearful while regime,
    dominance and correlation all read neutral-ish — so the composite lands
    fear-leaning rather than deep in fear. What matters is that it moves off
    the ~50 midpoint at all; the old code returned 51 here.
    """
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    assert s.score < 45, f"fearful market scored {s.score} ({s.label})"


def test_extreme_fear_snapshot_earns_a_fear_label():
    """When the live inputs agree on fear, the label must follow."""
    snap = dict(FLAT_SNAPSHOT_FEAR)
    snap["fear_greed"] = 8
    snap["fear_greed_label"] = "Extreme Fear"
    snap["btc_dominance"] = 64.0  # flight to safety
    snap["btc_funding_rate_pct"] = -0.06  # shorts crowded
    snap["eth_funding_rate_pct"] = -0.05
    snap["classification"] = dict(FLAT_SNAPSHOT_FEAR["classification"])
    snap["classification"]["regime"] = "RISK_OFF"
    snap["classification"]["score"] = -0.8
    s = compute_sentiment(chain_snapshot=snap, correlation_events=[])
    assert s.label in {"fear", "extreme_fear"}, f"scored {s.score} ({s.label})"


def test_dominance_reads_flat_btc_dominance_key():
    """BTC.D 56.5% must be reflected, not the 50.0% default."""
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    assert "56.5" in s.explanations["dominance"]


def test_regime_reads_classification_key():
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    assert "NEUTRAL" in s.explanations["regime"]
    assert "-0.06" in s.explanations["regime"]


def test_real_fear_greed_index_is_an_input():
    """The authoritative sentiment reading must not be ignored."""
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    assert "fear_greed" in s.components
    assert s.components["fear_greed"] == 27


def test_unavailable_inputs_are_excluded_not_scored_neutral():
    """Absent data must not inject fake 50s that drag the composite to neutral."""
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    # Binance funding is None in this snapshot; chain snapshot carries no OI
    # or stablecoin supply at all.
    for absent in ("funding", "oi", "stablecoins"):
        assert absent not in s.components, f"{absent} should be excluded when unavailable"
        assert "unavailable" in s.explanations[absent]


def test_funding_is_scored_when_present():
    s = compute_sentiment(chain_snapshot=_greedy_snapshot(), correlation_events=[])
    assert "funding" in s.components
    assert s.components["funding"] > 50


def test_greedy_market_scores_high():
    s = compute_sentiment(chain_snapshot=_greedy_snapshot(), correlation_events=[])
    assert s.score > 65, f"greedy market scored {s.score} ({s.label})"
    assert s.label in {"greed", "extreme_greed"}


def test_composite_is_not_pinned_across_opposite_regimes():
    """Guard against the whole metric being constant."""
    fear = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    greed = compute_sentiment(chain_snapshot=_greedy_snapshot(), correlation_events=[])
    assert greed.score - fear.score > 25


def test_empty_snapshot_degrades_gracefully():
    """No chain data at all: correlation is the only live input."""
    s = compute_sentiment(chain_snapshot={}, correlation_events=[])
    assert 0 <= s.score <= 100
    assert s.label
    assert "fear_greed" not in s.components


def test_components_stay_renderable_by_the_brief():
    """daily_brief sorts components by abs(v - 50) — all values must be numeric."""
    s = compute_sentiment(chain_snapshot=FLAT_SNAPSHOT_FEAR, correlation_events=[])
    assert s.components
    for name, val in s.components.items():
        assert isinstance(val, (int, float)), f"{name} is {type(val)}"
        assert name in s.explanations
