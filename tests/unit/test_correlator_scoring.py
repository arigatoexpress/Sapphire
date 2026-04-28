"""Pure-math tests for ``lib.correlator.scoring``.

All tests here run in <1ms and assert math invariants (bound,
monotonicity, symmetry, freshness decay) with no I/O.
"""

from __future__ import annotations

import pytest

from lib.correlator.scoring import (
    DEFAULT_AGREEMENT_BONUS_PER_EXTRA,
    DEFAULT_CONTRADICT_PENALTY,
    DEFAULT_FRESHNESS_HALF_LIFE_SECONDS,
    DEFAULT_MAX_AGREEMENT_MULTIPLIER,
    DEFAULT_SOURCE_WEIGHTS,
    SCORING_VERSION,
    ScoringWeights,
    compose_score,
    freshness_factor,
    load_weights,
    normalize_direction,
)


def _bull(conf: float = 1.0, age: float = 0.0) -> dict:
    return {"direction": "bull", "confidence": conf, "age_seconds": age}


def _bear(conf: float = 1.0, age: float = 0.0) -> dict:
    return {"direction": "bear", "confidence": conf, "age_seconds": age}


def _neut(conf: float = 1.0, age: float = 0.0) -> dict:
    return {"direction": "neutral", "confidence": conf, "age_seconds": age}


def test_freshness_factor_zero_age_is_one() -> None:
    assert freshness_factor(0.0, DEFAULT_FRESHNESS_HALF_LIFE_SECONDS) == 1.0


def test_freshness_factor_half_life_is_half() -> None:
    val = freshness_factor(DEFAULT_FRESHNESS_HALF_LIFE_SECONDS, DEFAULT_FRESHNESS_HALF_LIFE_SECONDS)
    assert val == pytest.approx(0.5, abs=1e-9)


def test_freshness_factor_decays_monotonically() -> None:
    half_life = 600.0
    samples = [freshness_factor(t, half_life) for t in (0, 60, 600, 1200, 6000)]
    for prev, nxt in zip(samples, samples[1:]):
        assert nxt <= prev


def test_freshness_factor_handles_garbage_inputs() -> None:
    assert freshness_factor(float("nan"), 100.0) == 0.0
    assert freshness_factor(float("inf"), 100.0) == 0.0
    assert freshness_factor(-1.0, 100.0) == 1.0  # negative ages clamp to fresh


def test_normalize_direction_handles_strings_ints_and_none() -> None:
    assert normalize_direction("bull") == 1
    assert normalize_direction("bullish") == 1
    assert normalize_direction("BUY") == 1
    assert normalize_direction("bear") == -1
    assert normalize_direction(0) == 0
    assert normalize_direction(2) == 1
    assert normalize_direction(-3) == -1
    assert normalize_direction(None) == 0
    assert normalize_direction("garbage") == 0


def test_compose_empty_returns_zero_score() -> None:
    out = compose_score({}, ScoringWeights())
    assert out.edge_score == 0.0
    assert out.contributing == ()
    assert out.bull_count == 0


def test_compose_score_is_within_edge_bound() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 1.0, "c": 1.0})
    res = compose_score({"a": _bull(1.0), "b": _bull(1.0), "c": _bull(1.0)}, weights)
    assert -1.0 <= res.edge_score <= 1.0


def test_compose_full_agreement_is_positive_and_bonus_applied() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 1.0, "c": 1.0})
    out = compose_score({"a": _bull(0.5), "b": _bull(0.5), "c": _bull(0.5)}, weights)
    assert out.edge_score > 0
    assert out.agreement_multiplier > 1.0
    assert out.bear_count == 0
    assert out.bull_count == 3


def test_compose_full_disagreement_dampens_score() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 1.0})
    full_bull = compose_score({"a": _bull(1.0), "b": _bull(1.0)}, weights)
    contradict = compose_score({"a": _bull(1.0), "b": _bear(1.0)}, weights)
    assert contradict.contradict_factor < 1.0
    assert abs(contradict.edge_score) < abs(full_bull.edge_score)


def test_compose_zero_weight_source_is_silently_ignored() -> None:
    weights = ScoringWeights(source_weights={"keeper": 1.0, "ignored": 0.0})
    out = compose_score({"keeper": _bull(1.0), "ignored": _bear(1.0)}, weights)
    assert all(c.source != "ignored" for c in out.contributing)
    assert out.edge_score > 0


def test_compose_unknown_source_silently_ignored() -> None:
    weights = ScoringWeights(source_weights={"keeper": 1.0})
    out = compose_score({"keeper": _bull(1.0), "stranger": _bull(1.0)}, weights)
    assert {c.source for c in out.contributing} == {"keeper"}


def test_compose_freshness_decay_lowers_score() -> None:
    weights = ScoringWeights(
        source_weights={"a": 1.0},
        freshness_half_life_seconds=600.0,
    )
    fresh = compose_score({"a": _bull(1.0, age=0.0)}, weights)
    stale = compose_score({"a": _bull(1.0, age=1200.0)}, weights)
    assert stale.edge_score < fresh.edge_score
    assert stale.edge_score >= 0


def test_compose_symmetry_flipping_directions_flips_sign() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 1.0})
    pos = compose_score({"a": _bull(0.7), "b": _bull(0.3)}, weights)
    neg = compose_score({"a": _bear(0.7), "b": _bear(0.3)}, weights)
    assert pos.edge_score == pytest.approx(-neg.edge_score, abs=1e-6)


@pytest.mark.parametrize("conf", [0.1, 0.3, 0.5, 0.7, 0.9])
def test_compose_score_monotonicity_in_confidence(conf: float) -> None:
    weights = ScoringWeights(source_weights={"a": 1.0})
    base = compose_score({"a": _bull(conf)}, weights).edge_score
    higher = compose_score({"a": _bull(min(1.0, conf + 0.1))}, weights).edge_score
    assert higher >= base


def test_compose_neutral_does_not_add_directional_pressure() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 1.0})
    bull_only = compose_score({"a": _bull(1.0)}, weights)
    bull_plus_neutral = compose_score({"a": _bull(1.0), "b": _neut(1.0)}, weights)
    assert bull_plus_neutral.bull_count == 1
    assert bull_plus_neutral.bear_count == 0
    # Neutral b adds weight to the denominator but no signed contribution.
    assert bull_plus_neutral.edge_score < bull_only.edge_score


def test_compose_max_agreement_multiplier_caps() -> None:
    weights = ScoringWeights(
        source_weights={f"s{i}": 1.0 for i in range(20)},
        max_agreement_multiplier=1.4,
        agreement_bonus_per_extra=0.1,
    )
    out = compose_score({f"s{i}": _bull(1.0) for i in range(20)}, weights)
    assert out.agreement_multiplier <= 1.4 + 1e-9


def test_load_weights_missing_file_uses_defaults(tmp_path) -> None:
    res = load_weights(tmp_path / "absent.yaml")
    assert res.source_weights == DEFAULT_SOURCE_WEIGHTS
    assert res.contradict_penalty == DEFAULT_CONTRADICT_PENALTY


def test_load_weights_overrides_subset(tmp_path) -> None:
    cfg = tmp_path / "weights.yaml"
    cfg.write_text(
        "source_weights:\n"
        "  tradingview: 2.5\n"
        "agreement_bonus_per_extra: 0.25\n"
        "freshness_half_life_seconds: 300\n",
        encoding="utf-8",
    )
    res = load_weights(cfg)
    assert res.weight_for("tradingview") == 2.5
    # Untouched key still has its default value.
    assert res.weight_for("kronos_forecast") == DEFAULT_SOURCE_WEIGHTS["kronos_forecast"]
    assert res.agreement_bonus_per_extra == 0.25
    assert res.freshness_half_life_seconds == 300.0


def test_load_weights_malformed_yaml_falls_back(tmp_path) -> None:
    cfg = tmp_path / "weights.yaml"
    cfg.write_text("source_weights: [\nunclosed: list:\n", encoding="utf-8")
    res = load_weights(cfg)
    assert res.source_weights == DEFAULT_SOURCE_WEIGHTS


def test_default_weights_match_advertised_caps() -> None:
    """Caps in the PR spec must match what the module publishes."""
    assert DEFAULT_AGREEMENT_BONUS_PER_EXTRA == pytest.approx(0.10)
    assert DEFAULT_MAX_AGREEMENT_MULTIPLIER == pytest.approx(1.40)
    assert SCORING_VERSION == "0.1.0"
    # Eight known sources.
    assert set(DEFAULT_SOURCE_WEIGHTS) == {
        "tradingview",
        "telegram_intel",
        "hyperliquid_public_feed",
        "threat_intel",
        "convergence_watchlist",
        "sovereign_thesis",
        "kronos_forecast",
        "ta_scanner",
    }


def test_compose_total_weight_only_counts_listed_sources() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 0.5})
    out = compose_score({"a": _bull(1.0), "b": _bull(1.0), "c": _bull(1.0)}, weights)
    assert out.total_weight == pytest.approx(1.5)
