"""Unit tests — lib.core.decision_engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.core.decision_engine import (
    Alert,
    Decision,
    DecisionEngine,
    FearContrarianRule,
    FundingCrowdingRule,
    RegimePenaltyRule,
    StateLoader,
    _normalize_world,
)


@pytest.fixture
def tmp_engine(tmp_path):
    """Engine with isolated decisions dir + state file."""
    loader = StateLoader(chain_path=tmp_path / "chain.json")
    return DecisionEngine(
        state_loader=loader,
        decisions_dir=tmp_path / "decisions",
        state_path=tmp_path / "last_regime.json",
        audit_path=tmp_path / "autonomy.jsonl",
    )


class TestRegimePenaltyRule:
    def test_long_in_trend_up_aligned(self):
        r = RegimePenaltyRule()
        res = r.evaluate({"direction": "long"}, {"regime": "TREND_UP"})
        assert res is not None
        delta, reason = res
        assert delta > 0
        assert "aligned" in reason

    def test_long_in_trend_down_opposed(self):
        r = RegimePenaltyRule()
        res = r.evaluate({"direction": "long"}, {"regime": "TREND_DOWN"})
        assert res is not None
        delta, _ = res
        assert delta < 0

    def test_unknown_regime_no_effect(self):
        r = RegimePenaltyRule()
        assert r.evaluate({"direction": "long"}, {"regime": "UNKNOWN"}) is None

    def test_no_direction_no_effect(self):
        r = RegimePenaltyRule()
        assert r.evaluate({}, {"regime": "TREND_UP"}) is None


class TestFundingCrowdingRule:
    def test_longs_crowded_penalized(self):
        r = FundingCrowdingRule()
        res = r.evaluate({"direction": "long"}, {"funding_apr": 0.50})
        assert res is not None
        delta, reason = res
        assert delta < 0
        assert "crowded" in reason

    def test_shorts_fade_crowded_longs_gets_bonus(self):
        r = FundingCrowdingRule()
        res = r.evaluate({"direction": "short"}, {"funding_apr": 0.50})
        assert res is not None
        delta, _ = res
        assert delta > 0

    def test_below_threshold_no_effect(self):
        r = FundingCrowdingRule()
        assert r.evaluate({"direction": "long"}, {"funding_apr": 0.05}) is None

    def test_missing_funding_no_effect(self):
        r = FundingCrowdingRule()
        assert r.evaluate({"direction": "long"}, {}) is None


class TestFearContrarianRule:
    def test_extreme_fear_long_bonus(self):
        r = FearContrarianRule()
        res = r.evaluate({"direction": "long"}, {"fear_greed": 15})
        assert res is not None
        delta, _ = res
        assert delta > 0

    def test_extreme_greed_short_bonus(self):
        r = FearContrarianRule()
        res = r.evaluate({"direction": "short"}, {"fear_greed": 90})
        assert res is not None
        assert res[0] > 0

    def test_neutral_fg_no_effect(self):
        r = FearContrarianRule()
        assert r.evaluate({"direction": "long"}, {"fear_greed": 50}) is None

    def test_longs_into_greed_penalized(self):
        r = FearContrarianRule()
        res = r.evaluate({"direction": "long"}, {"fear_greed": 85})
        assert res is not None
        assert res[0] < 0


class TestNormalizeWorld:
    def test_flattens_nested_regime_block(self):
        w = _normalize_world(
            {
                "regime": {"state": "trend_up", "score": 0.8, "confidence": 0.7},
                "funding": {"apr": 0.4},
                "sentiment": {"fear_greed": 18},
            }
        )
        assert w["regime"] == "TREND_UP"
        assert w["regime_score"] == 0.8
        assert w["funding_apr"] == 0.4
        assert w["fear_greed"] == 18

    def test_flat_keys_also_work(self):
        w = _normalize_world({"regime": "RISK_ON", "fear_greed": 72})
        assert w["regime"] == "RISK_ON"
        assert w["fear_greed"] == 72

    def test_empty_input_defaults_to_unknown_regime(self):
        # No chain data → regime defaults to UNKNOWN so downstream rules skip cleanly.
        w = _normalize_world({})
        assert w == {"regime": "UNKNOWN"}


class TestDecisionEngine:
    def test_allow_verdict_when_no_rules_fire(self, tmp_engine):
        d = tmp_engine.evaluate(
            {
                "symbol": "BTC",
                "direction": "long",
                "confidence": 0.70,
            },
            world={},
        )
        assert d.verdict == "ALLOW"
        assert d.adjusted_confidence == 0.70
        assert d.rules_fired == []

    def test_opposed_regime_reduces_confidence(self, tmp_engine):
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.55},
            world={"regime": "TREND_DOWN"},
        )
        assert d.adjusted_confidence < 0.55
        assert "regime_penalty" in d.rules_fired

    def test_block_verdict_when_confidence_drops_below_threshold(self, tmp_engine):
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.30},
            world={"regime": "TREND_DOWN", "funding_apr": 0.50, "fear_greed": 85},
        )
        # All three rules penalize
        assert d.adjusted_confidence < 0.20
        assert d.verdict == "BLOCK"

    def test_aligned_regime_boosts_confidence(self, tmp_engine):
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.60},
            world={"regime": "TREND_UP"},
        )
        assert d.adjusted_confidence > 0.60
        assert d.verdict == "ALLOW"

    def test_contrarian_stack_fear_and_regime(self, tmp_engine):
        """Long into extreme fear during a TREND_UP aligns + contrarian bonus."""
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.50},
            world={"regime": "TREND_UP", "fear_greed": 15},
        )
        assert d.adjusted_confidence > 0.55  # cumulative boost
        assert "regime_penalty" in d.rules_fired
        assert "fear_contrarian" in d.rules_fired

    def test_evaluation_is_logged(self, tmp_engine, tmp_path):
        tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.70},
            world={"regime": "TREND_UP"},
        )
        logs = list((tmp_path / "decisions").glob("*.jsonl"))
        assert len(logs) == 1
        record = json.loads(logs[0].read_text().strip().splitlines()[0])
        assert record["symbol"] == "BTC"
        assert record["verdict"] == "ALLOW"
        assert "regime_penalty" in record["rules_fired"]

    def test_confidence_clamped(self, tmp_engine):
        # Stack everything bullish — should cap at 1.0
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.95},
            world={"regime": "TREND_UP", "funding_apr": -0.50, "fear_greed": 15},
        )
        assert d.adjusted_confidence <= 1.0

    def test_rule_exception_does_not_abort(self, tmp_engine):
        class BadRule:
            name = "bad"

            def evaluate(self, signal, world):
                raise RuntimeError("boom")

        tmp_engine.rules.append(BadRule())
        d = tmp_engine.evaluate(
            {"symbol": "BTC", "direction": "long", "confidence": 0.50},
            world={},
        )
        assert any("rule_error" in r for r in d.reasons)
        assert d.verdict in {"ALLOW", "REDUCE", "BLOCK"}


class TestScanAlerts:
    def test_regime_shift_fires_once(self, tmp_engine):
        # First pass — baseline, no prior state
        alerts1 = tmp_engine.scan_alerts({"regime": "TREND_UP"})
        assert all(a.kind != "regime_shift" for a in alerts1)
        # Second pass — same regime, no alert
        alerts2 = tmp_engine.scan_alerts({"regime": "TREND_UP"})
        assert all(a.kind != "regime_shift" for a in alerts2)
        # Third pass — regime changed
        alerts3 = tmp_engine.scan_alerts({"regime": "TREND_DOWN"})
        shifts = [a for a in alerts3 if a.kind == "regime_shift"]
        assert len(shifts) == 1
        assert "TREND_UP → TREND_DOWN" in shifts[0].message

    def test_funding_extreme_alert(self, tmp_engine):
        alerts = tmp_engine.scan_alerts({"funding_apr": 0.80})
        kinds = [a.kind for a in alerts]
        assert "funding_extreme" in kinds
        fa = next(a for a in alerts if a.kind == "funding_extreme")
        assert fa.severity == "critical"

    def test_fear_extreme_alert(self, tmp_engine):
        alerts = tmp_engine.scan_alerts({"fear_greed": 12})
        kinds = [a.kind for a in alerts]
        assert "fear_extreme" in kinds

    def test_no_alerts_in_normal_state(self, tmp_engine):
        alerts = tmp_engine.scan_alerts(
            {
                "regime": "RANGE",
                "funding_apr": 0.05,
                "fear_greed": 55,
            }
        )
        # Possibly an initial regime baseline entry, but nothing flagged.
        flagged = [a for a in alerts if a.severity in {"warn", "critical"}]
        assert flagged == []


class TestOnEvent:
    def test_signal_event_returns_decision(self, tmp_engine):
        out = tmp_engine.on_event(
            "signal.emitted",
            {
                "symbol": "BTC",
                "direction": "long",
                "confidence": 0.70,
            },
        )
        assert len(out) == 1
        assert isinstance(out[0], Decision)

    def test_regime_event_returns_alerts(self, tmp_engine):
        # Seed last-regime then shift
        tmp_engine.scan_alerts({"regime": "RANGE"})
        out = tmp_engine.on_event("regime.refreshed", {"world": {"regime": "TREND_DOWN"}})
        assert any(isinstance(a, Alert) and a.kind == "regime_shift" for a in out)

    def test_unknown_event_returns_empty(self, tmp_engine):
        assert tmp_engine.on_event("random.thing", {}) == []


class TestStateLoader:
    def test_missing_file_returns_empty(self, tmp_path):
        loader = StateLoader(chain_path=tmp_path / "nope.json")
        assert loader.load() == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "chain.json"
        p.write_text("not json")
        loader = StateLoader(chain_path=p)
        assert loader.load() == {}

    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "chain.json"
        p.write_text(json.dumps({"regime": {"state": "RISK_ON"}, "fear_greed": 70}))
        loader = StateLoader(chain_path=p)
        w = loader.load()
        assert w["regime"] == "RISK_ON"
        assert w["fear_greed"] == 70
