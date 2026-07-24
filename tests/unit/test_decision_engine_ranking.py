"""Unit tests — lib.core.decision_engine ranking, serialisation, explain shape.

These tests complement `test_decision_engine.py` (rule unit tests) and
`test_decision_engine_audit.py` (audit-log redaction). They focus on:

  - Single signal in → Decision out: rationale fields are populated.
  - Multiple competing signals → ranking by adjusted_confidence is a total order.
  - Determinism: identical inputs evaluate to identical decisions across calls.
  - Round-trip JSON serialisation of Decision / Alert.
  - Stable shape of the "explain" path for the dashboard consumer.
  - Verdict thresholds (BLOCK / REDUCE / ALLOW) at the boundaries.
  - Idempotence of the regime-shift state file.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.core.decision_engine import (
    Alert,
    Decision,
    DecisionEngine,
    StateLoader,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path):
    """Engine with isolated decisions dir + state + audit paths."""
    return DecisionEngine(
        state_loader=StateLoader(chain_path=tmp_path / "chain.json"),
        decisions_dir=tmp_path / "decisions",
        state_path=tmp_path / "last_regime.json",
        audit_path=tmp_path / "autonomy.jsonl",
    )


# ---------------------------------------------------------------------------
# Single-signal contract — rationale is populated
# ---------------------------------------------------------------------------


class TestSingleDecisionContract:
    def test_decision_returned_for_single_signal(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.65},
            world={"regime": "TREND_UP"},
        )
        assert isinstance(d, Decision)
        assert d.symbol == "BTC"
        assert d.direction == "long"
        assert d.original_confidence == 0.65

    def test_rationale_non_empty_when_a_rule_fires(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.50},
            world={"regime": "TREND_UP"},
        )
        # Aligned long in TREND_UP → regime_aligned reason.
        assert d.reasons, "rationale should not be empty when a rule fires"
        assert d.rules_fired, "rules_fired should not be empty when a rule fires"
        # Each fired rule contributes one reason string.
        assert len(d.reasons) == len(d.rules_fired)

    def test_rationale_empty_when_no_rule_fires(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.50},
            world={},
        )
        assert d.reasons == []
        assert d.rules_fired == []

    def test_decision_has_iso_timestamp(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.50},
            world={},
        )
        # `datetime.fromisoformat` doesn't raise → timestamp is well-formed.
        from datetime import datetime

        datetime.fromisoformat(d.timestamp)


# ---------------------------------------------------------------------------
# Ranking — multiple competing signals
# ---------------------------------------------------------------------------


class TestRanking:
    def test_higher_confidence_signal_ranks_above_lower(self, engine):
        """Two equally-aligned longs → higher original confidence ranks higher."""
        a = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.80},
            world={"regime": "TREND_UP"},
        )
        b = engine.evaluate(
            {"symbol": "ETH", "direction": "long", "confidence": 0.55},
            world={"regime": "TREND_UP"},
        )
        ranked = sorted([a, b], key=lambda d: d.adjusted_confidence, reverse=True)
        assert ranked[0].symbol == "BTC"
        assert ranked[1].symbol == "ETH"

    def test_aligned_beats_opposed_at_same_starting_confidence(self, engine):
        """Same starting confidence — aligned regime should beat opposed regime."""
        aligned = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.60},
            world={"regime": "TREND_UP"},
        )
        opposed = engine.evaluate(
            {"symbol": "ETH", "direction": "long", "confidence": 0.60},
            world={"regime": "TREND_DOWN"},
        )
        assert aligned.adjusted_confidence > opposed.adjusted_confidence

    def test_total_order_no_ties_when_confidence_distinct(self, engine):
        """Three distinct setups → strict total order in adjusted_confidence."""
        decisions = [
            engine.evaluate(
                {"symbol": "BTC", "direction": "long", "confidence": 0.80},
                world={"regime": "TREND_UP"},
            ),
            engine.evaluate(
                {"symbol": "ETH", "direction": "long", "confidence": 0.55},
                world={},
            ),
            engine.evaluate(
                {"symbol": "SOL", "direction": "long", "confidence": 0.30},
                world={"regime": "TREND_DOWN"},
            ),
        ]
        scores = [d.adjusted_confidence for d in decisions]
        assert scores[0] > scores[1] > scores[2]
        # Verdicts also follow the threshold scheme.
        assert decisions[0].verdict == "ALLOW"
        assert decisions[2].verdict == "BLOCK"

    def test_ranking_deterministic_across_calls(self, engine):
        """Same inputs → same adjusted_confidence each call (no jitter)."""
        signal = {"symbol": "BTC", "direction": "long", "confidence": 0.55}
        world = {"regime": "TREND_UP", "fear_greed": 18}
        scores = [engine.evaluate(signal, world).adjusted_confidence for _ in range(3)]
        # All three calls produce exactly the same score.
        assert scores[0] == scores[1] == scores[2]

    def test_tie_breaker_identical_inputs_produce_identical_scores(self, engine):
        """Two signals with identical inputs sit at the same score (a true tie).

        Stable sort then preserves the order they were evaluated in — this is
        the deterministic behaviour the dashboard depends on for replays.
        """
        a = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.60},
            world={"regime": "TREND_UP"},
        )
        b = engine.evaluate(
            {"symbol": "ETH", "direction": "long", "confidence": 0.60},
            world={"regime": "TREND_UP"},
        )
        assert a.adjusted_confidence == b.adjusted_confidence
        # Insertion order preserved by Python's stable sort.
        ranked = sorted([a, b], key=lambda d: d.adjusted_confidence, reverse=True)
        assert ranked[0].symbol == "BTC"
        assert ranked[1].symbol == "ETH"


# ---------------------------------------------------------------------------
# Verdict threshold boundaries
# ---------------------------------------------------------------------------


class TestVerdictThresholds:
    def test_at_block_threshold_is_reduce(self, engine):
        """Adjusted confidence == BLOCK_BELOW (0.20) → REDUCE (block is `<`)."""
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.20},
            world={},
        )
        assert d.adjusted_confidence == 0.20
        assert d.verdict == "REDUCE"

    def test_just_below_block_threshold_is_block(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.19},
            world={},
        )
        assert d.verdict == "BLOCK"

    def test_at_reduce_threshold_is_allow(self, engine):
        """Adjusted confidence == REDUCE_BELOW (0.45) → ALLOW (boundary is `<`)."""
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.45},
            world={},
        )
        assert d.adjusted_confidence == 0.45
        assert d.verdict == "ALLOW"

    def test_just_below_reduce_threshold_is_reduce(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.44},
            world={},
        )
        assert d.verdict == "REDUCE"


# ---------------------------------------------------------------------------
# Round-trip JSON serialisation
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_decision_round_trips_through_json(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.65},
            world={"regime": "TREND_UP", "fear_greed": 18},
        )
        # Serialise via dataclass → dict → JSON → dict; survives.
        as_dict = asdict(d)
        encoded = json.dumps(as_dict, default=str)
        decoded = json.loads(encoded)
        assert decoded["symbol"] == d.symbol
        assert decoded["adjusted_confidence"] == d.adjusted_confidence
        assert decoded["verdict"] == d.verdict
        assert decoded["rules_fired"] == d.rules_fired
        # World snapshot survives.
        assert decoded["world_snapshot"] == d.world_snapshot

    def test_alert_round_trips_through_json(self, engine):
        # Trigger a funding_extreme alert.
        alerts = engine.scan_alerts({"funding_apr": 0.80})
        funding_alerts = [a for a in alerts if a.kind == "funding_extreme"]
        assert funding_alerts, "expected a funding_extreme alert"
        a = funding_alerts[0]
        encoded = json.dumps(asdict(a), default=str)
        decoded = json.loads(encoded)
        assert decoded["kind"] == "funding_extreme"
        assert decoded["severity"] == a.severity
        assert decoded["data"]["apr"] == 0.80


# ---------------------------------------------------------------------------
# "Explain" shape — stable contract for the dashboard
# ---------------------------------------------------------------------------


# The dashboard consumes Decision via `asdict(decision)` and expects this exact
# set of keys. Adding/removing a field would break the SSE contract — pin it.
EXPECTED_DECISION_KEYS = frozenset(
    {
        "signal_id",
        "symbol",
        "direction",
        "original_confidence",
        "adjusted_confidence",
        "verdict",
        "reasons",
        "rules_fired",
        "world_snapshot",
        "timestamp",
    }
)


class TestExplainShape:
    def test_decision_has_exact_expected_keys(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.65},
            world={"regime": "TREND_UP"},
        )
        assert set(asdict(d).keys()) == EXPECTED_DECISION_KEYS

    def test_decision_dict_is_strict_json_safe(self, engine):
        """No NaN / Infinity / non-string keys in the decision dict."""
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.65},
            world={"regime": "TREND_UP", "fear_greed": 18, "funding_apr": 0.40},
        )
        # `allow_nan=False` is the strict-JSON mode the dashboard uses.
        encoded = json.dumps(asdict(d), allow_nan=False, default=str)
        decoded = json.loads(encoded)
        # Non-string keys would round-trip to strings — verify all stayed strings.
        for k in decoded:
            assert isinstance(k, str)
        for k in decoded.get("world_snapshot", {}):
            assert isinstance(k, str)

    def test_decision_field_types(self, engine):
        d = engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.65},
            world={"regime": "TREND_UP"},
        )
        assert isinstance(d.symbol, str)
        assert isinstance(d.direction, str)
        assert isinstance(d.original_confidence, float)
        assert isinstance(d.adjusted_confidence, float)
        assert isinstance(d.verdict, str)
        assert isinstance(d.reasons, list)
        assert isinstance(d.rules_fired, list)
        assert isinstance(d.world_snapshot, dict)
        # Verdict comes from a fixed set.
        assert d.verdict in {"ALLOW", "REDUCE", "BLOCK", "ALERT_ONLY"}

    def test_dashboard_replay_consistency(self, engine):
        """A replay of the same signals yields a byte-identical decision payload.

        The dashboard caches recent decisions and replays them on reconnect.
        Two evaluations with identical inputs (modulo timestamp) must produce
        identical state-bearing fields.
        """
        signal = {"symbol": "BTC", "direction": "long", "confidence": 0.55}
        world = {"regime": "TREND_UP"}
        a = engine.evaluate(signal, world)
        b = engine.evaluate(signal, world)
        # Drop the per-call timestamp before comparing.
        a_payload = {k: v for k, v in asdict(a).items() if k != "timestamp"}
        b_payload = {k: v for k, v in asdict(b).items() if k != "timestamp"}
        assert a_payload == b_payload


# ---------------------------------------------------------------------------
# Regime-shift state file behaviour
# ---------------------------------------------------------------------------


class TestRegimeShiftStateFile:
    def test_regime_state_file_persisted_after_first_scan(self, engine, tmp_path):
        """First scan with a known regime writes the persistence file."""
        engine.scan_alerts({"regime": "TREND_UP"})
        state_path = tmp_path / "last_regime.json"
        assert state_path.exists()
        record = json.loads(state_path.read_text(encoding="utf-8"))
        assert record["regime"] == "TREND_UP"
        assert "ts" in record

    def test_unknown_regime_does_not_overwrite_file(self, engine, tmp_path):
        engine.scan_alerts({"regime": "TREND_UP"})
        # Now a scan with unknown regime — must not overwrite.
        engine.scan_alerts({})
        record = json.loads((tmp_path / "last_regime.json").read_text(encoding="utf-8"))
        assert record["regime"] == "TREND_UP"

    def test_corrupt_state_file_treated_as_empty(self, engine, tmp_path):
        """Corrupt JSON in the state file → no shift alert fires (graceful)."""
        state_path = tmp_path / "last_regime.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{not json}")
        # First scan does not raise and emits no regime_shift alert.
        alerts = engine.scan_alerts({"regime": "TREND_DOWN"})
        assert all(a.kind != "regime_shift" for a in alerts)


# ---------------------------------------------------------------------------
# on_event integration
# ---------------------------------------------------------------------------


class TestOnEventIntegration:
    def test_signal_event_is_decision_serialisable(self, engine):
        """on_event for a signal returns a Decision that survives JSON encode."""
        out = engine.on_event(
            "signal.scored",
            {"symbol": "BTC", "direction": "long", "confidence": 0.70},
        )
        assert len(out) == 1
        d = out[0]
        assert isinstance(d, Decision)
        json.dumps(asdict(d), default=str)  # no exception

    def test_chain_refreshed_returns_alerts_serialisable(self, engine):
        """on_event for chain.refreshed returns Alerts that survive JSON encode."""
        # Pre-seed last regime so a shift fires on the second call.
        engine.scan_alerts({"regime": "RANGE"})
        out = engine.on_event(
            "chain.refreshed",
            {"world": {"regime": "TREND_DOWN"}},
        )
        # All returned items must be Alerts and JSON-serialisable.
        for a in out:
            assert isinstance(a, Alert)
            json.dumps(asdict(a), default=str)
