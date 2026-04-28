"""Tests for ``lib.correlator.engine``.

Covers:
- consensus labelling across all 7 buckets
- freshness hard-limit enforcement (silent drop)
- max-source fan-in capping (lowest-weight first)
- divergent / corroborated source bookkeeping
- universe orchestration with a mock SignalSource
- adapter-error containment
- idempotence (deterministic given fixed inputs)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from lib.correlator.engine import (
    CONSENSUS_LABELS,
    EDGE_SCORE_BOUND,
    FRESHNESS_HARD_LIMIT_SECONDS,
    MAX_CORRELATIONS_PER_HOUR,
    MAX_SOURCES_PER_CORRELATION,
    CorrelatedSignal,
    CorrelatorConfig,
    UniversePair,
    correlate_once,
    correlate_universe,
)
from lib.correlator.scoring import ScoringWeights
from lib.correlator.sources import SourceSignal


def _sig(direction: str, conf: float = 0.7, age: float = 60.0, source: str = "tradingview") -> dict:
    return {
        "source": source,
        "symbol": "BTC",
        "timeframe": "1h",
        "direction": direction,
        "confidence": conf,
        "age_seconds": age,
        "timestamp_iso": "",
        "raw": {},
    }


FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def test_caps_match_spec() -> None:
    assert MAX_SOURCES_PER_CORRELATION == 16
    assert MAX_CORRELATIONS_PER_HOUR == 1200
    assert FRESHNESS_HARD_LIMIT_SECONDS == 86_400
    assert EDGE_SCORE_BOUND == (-1.0, +1.0)


def test_consensus_label_set_is_documented() -> None:
    assert "AGREE_BULL" in CONSENSUS_LABELS
    assert "AGREE_BEAR" in CONSENSUS_LABELS
    assert "PARTIAL_BULL" in CONSENSUS_LABELS
    assert "PARTIAL_BEAR" in CONSENSUS_LABELS
    assert "CONTRADICT" in CONSENSUS_LABELS
    assert "NEUTRAL" in CONSENSUS_LABELS
    assert "INSUFFICIENT_DATA" in CONSENSUS_LABELS


def test_empty_input_returns_insufficient_data() -> None:
    out = correlate_once(symbol="BTC", timeframe="1h", signals_by_source={}, now=FROZEN_NOW)
    assert isinstance(out, CorrelatedSignal)
    assert out.consensus == "INSUFFICIENT_DATA"
    assert out.edge_score == 0.0
    assert out.contributing == 0
    assert out.corroborated_by == ()


def test_full_agreement_bull_yields_agree_bull() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bull", 0.8),
            "ta_scanner": _sig("bull", 0.7),
            "kronos_forecast": _sig("bull", 0.6),
        },
        now=FROZEN_NOW,
    )
    assert out.consensus == "AGREE_BULL"
    assert out.edge_score > 0
    assert set(out.corroborated_by) == {"tradingview", "ta_scanner", "kronos_forecast"}
    assert out.divergent_sources == ()


def test_full_agreement_bear_yields_agree_bear() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bear", 0.8),
            "ta_scanner": _sig("bear", 0.7),
        },
        now=FROZEN_NOW,
    )
    assert out.consensus == "AGREE_BEAR"
    assert out.edge_score < 0


def test_one_bull_yields_partial_bull() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 0.7)},
        now=FROZEN_NOW,
    )
    assert out.consensus == "PARTIAL_BULL"
    assert out.edge_score > 0
    assert out.bull_sources == ("tradingview",)


def test_one_bear_yields_partial_bear() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={"ta_scanner": _sig("bear", 0.7)},
        now=FROZEN_NOW,
    )
    assert out.consensus == "PARTIAL_BEAR"
    assert out.edge_score < 0


def test_mixed_directions_yield_contradict() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bull", 0.8),
            "ta_scanner": _sig("bear", 0.8),
        },
        now=FROZEN_NOW,
    )
    assert out.consensus == "CONTRADICT"


def test_only_neutral_signals_yield_neutral() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={"tradingview": _sig("neutral", 0.7)},
        now=FROZEN_NOW,
    )
    assert out.consensus == "NEUTRAL"
    assert out.edge_score == 0


def test_freshness_hard_limit_drops_stale_signals() -> None:
    out = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bull", 0.8, age=FRESHNESS_HARD_LIMIT_SECONDS + 1),
        },
        now=FROZEN_NOW,
    )
    assert out.consensus == "INSUFFICIENT_DATA"
    assert out.contributing == 0


def test_freshness_decay_reduces_edge_when_stale() -> None:
    fresh = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 1.0, age=0)},
        now=FROZEN_NOW,
    )
    aged = correlate_once(
        symbol="BTC",
        timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 1.0, age=3 * 3600)},
        now=FROZEN_NOW,
    )
    assert aged.edge_score < fresh.edge_score
    assert aged.edge_score >= 0


def test_max_sources_per_correlation_caps_fan_in() -> None:
    # Build a synthetic set of 20 known sources by extending weights.
    weights = ScoringWeights(
        source_weights={f"s{i}": 1.0 - 0.01 * i for i in range(20)},
    )
    config = CorrelatorConfig(weights=weights)
    payload = {f"s{i}": _sig("bull", 0.5, source=f"s{i}") for i in range(20)}
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source=payload,
        config=config, now=FROZEN_NOW,
    )
    assert out.contributing == MAX_SOURCES_PER_CORRELATION
    # The 4 lowest-weight sources should have been dropped.
    kept = set(out.bull_sources)
    assert "s0" in kept and "s15" in kept
    assert "s19" not in kept and "s16" not in kept


def test_zero_weight_sources_silently_ignored_in_engine() -> None:
    weights = ScoringWeights(source_weights={"a": 1.0, "b": 0.0})
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={
            "a": _sig("bull", 0.5, source="a"),
            "b": _sig("bear", 0.5, source="b"),
        },
        config=CorrelatorConfig(weights=weights),
        now=FROZEN_NOW,
    )
    # 'b' is weight 0 → not in contributing breakdown, but split_directions
    # still classifies its raw direction. The engine drops zero-weight sources
    # before scoring so consensus comes from 'a' only.
    assert out.consensus == "PARTIAL_BULL"


def test_single_source_no_agreement_bonus() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 1.0)},
        now=FROZEN_NOW,
    )
    assert out.agreement_multiplier == 1.0


def test_three_source_agreement_applies_bonus() -> None:
    weights = ScoringWeights(
        source_weights={"tradingview": 1.0, "ta_scanner": 1.0, "kronos_forecast": 1.0},
        agreement_bonus_per_extra=0.2,
    )
    config = CorrelatorConfig(weights=weights)
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bull", 0.5, source="tradingview"),
            "ta_scanner": _sig("bull", 0.5, source="ta_scanner"),
            "kronos_forecast": _sig("bull", 0.5, source="kronos_forecast"),
        },
        config=config, now=FROZEN_NOW,
    )
    assert out.agreement_multiplier == pytest.approx(1.4, abs=1e-6)


def test_edge_score_is_bounded() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={f"s{i}": _sig("bull", 1.0, source=f"s{i}") for i in range(8)},
        now=FROZEN_NOW,
    )
    assert -1.0 <= out.edge_score <= 1.0


def test_contradict_score_corroboration_picks_dominant_side() -> None:
    weights = ScoringWeights(source_weights={"big": 2.0, "small": 0.5})
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={
            "big": _sig("bull", 1.0, source="big"),
            "small": _sig("bear", 1.0, source="small"),
        },
        config=CorrelatorConfig(weights=weights),
        now=FROZEN_NOW,
    )
    assert out.consensus == "CONTRADICT"
    assert out.edge_score > 0  # bull side dominates
    assert "big" in out.corroborated_by
    assert "small" in out.divergent_sources


def test_idempotence_same_input_same_output() -> None:
    payload = {
        "tradingview": _sig("bull", 0.7),
        "ta_scanner": _sig("bull", 0.6),
        "kronos_forecast": _sig("bear", 0.4),
    }
    runs = [
        correlate_once(symbol="BTC", timeframe="1h", signals_by_source=payload, now=FROZEN_NOW)
        for _ in range(5)
    ]
    assert all(r.edge_score == runs[0].edge_score for r in runs)
    assert all(r.consensus == runs[0].consensus for r in runs)


class _StubSource:
    def __init__(self, name: str, signals: dict[tuple[str, str], dict | None]) -> None:
        self.name = name
        self._signals = signals

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        sig = self._signals.get((symbol, timeframe))
        if sig is None:
            return None
        return SourceSignal(
            source=self.name,
            symbol=symbol,
            timeframe=timeframe,
            direction=sig["direction"],
            confidence=sig.get("confidence", 0.7),
            age_seconds=sig.get("age_seconds", 60.0),
            timestamp_iso="",
            raw={},
        )


def test_correlate_universe_orchestrates_sources() -> None:
    src = _StubSource(
        name="tradingview",
        signals={
            ("BTC", "1h"): {"direction": "bull", "confidence": 0.7},
            ("ETH", "1h"): {"direction": "bear", "confidence": 0.6},
        },
    )
    pairs = [UniversePair("BTC", "1h"), UniversePair("ETH", "1h")]
    out = correlate_universe(pairs, sources=[src], now=FROZEN_NOW)
    assert len(out) == 2
    assert out[0].symbol == "BTC" and out[0].consensus == "PARTIAL_BULL"
    assert out[1].symbol == "ETH" and out[1].consensus == "PARTIAL_BEAR"


def test_correlate_universe_accepts_tuple_pairs() -> None:
    src = _StubSource(
        name="tradingview",
        signals={("BTC", "1h"): {"direction": "bull", "confidence": 0.5}},
    )
    out = correlate_universe([("BTC", "1h")], sources=[src], now=FROZEN_NOW)
    assert len(out) == 1


def test_correlate_universe_swallows_adapter_errors() -> None:
    class _Bomb:
        name = "bomb"

        def latest_for(self, symbol: str, timeframe: str) -> Any:
            raise RuntimeError("kaboom")

    src = _StubSource(name="tradingview", signals={("BTC", "1h"): {"direction": "bull"}})
    out = correlate_universe(
        [("BTC", "1h")], sources=[src, _Bomb()], now=FROZEN_NOW
    )
    assert len(out) == 1
    # The non-broken source still contributed.
    assert out[0].consensus == "PARTIAL_BULL"


def test_correlated_signal_to_dict_roundtrips() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 0.5)},
        now=FROZEN_NOW,
    )
    blob = out.to_dict()
    assert blob["symbol"] == "BTC"
    assert blob["timeframe"] == "1h"
    assert blob["consensus"] == "PARTIAL_BULL"
    assert "provenance_envelope" in blob


def test_provenance_envelope_includes_weights_signature() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 0.5)},
        now=FROZEN_NOW,
    )
    env = out.provenance_envelope
    assert env["generator"] == "lib.correlator.engine"
    assert "weights_signature" in env
    assert "tradingview" in env["weights_signature"]["source_weights"]


def test_engine_handles_source_signal_dataclass_inputs() -> None:
    sig = SourceSignal(
        source="tradingview",
        symbol="BTC",
        timeframe="1h",
        direction="bull",
        confidence=0.7,
        age_seconds=60.0,
        timestamp_iso="",
        raw={},
    )
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={"tradingview": sig},
        now=FROZEN_NOW,
    )
    assert out.consensus == "PARTIAL_BULL"


def test_negative_age_treated_as_fresh_not_stale() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={"tradingview": _sig("bull", 0.7, age=-100)},
        now=FROZEN_NOW,
    )
    assert out.consensus == "PARTIAL_BULL"


def test_universe_pair_can_be_constructed() -> None:
    p = UniversePair("BTC", "1h")
    assert p.symbol == "BTC" and p.timeframe == "1h"


def test_freshness_seconds_reports_min_age_across_sources() -> None:
    out = correlate_once(
        symbol="BTC", timeframe="1h",
        signals_by_source={
            "tradingview": _sig("bull", 0.5, age=120),
            "ta_scanner": _sig("bull", 0.5, age=30),
        },
        now=FROZEN_NOW,
    )
    assert out.freshness_seconds == 30.0
