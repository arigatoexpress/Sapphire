"""Unit tests for lib/core/decision_engine.py.

Uses the EventBus in fallback mode (JSONL-backed) so no Redis is required.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB_CORE = ROOT / "lib" / "core"
if str(LIB_CORE) not in sys.path:
    sys.path.insert(0, str(LIB_CORE))

from decision_engine import (  # noqa: E402
    DEFAULT_WEIGHT,
    MAX_WEIGHT,
    MIN_PUBLISH_CONFIDENCE,
    MIN_WEIGHT,
    Decision,
    DecisionEngine,
)
from event_bus import Event, EventBus  # noqa: E402


@pytest.fixture
def bus(tmp_path) -> EventBus:
    b = EventBus(redis_url="redis://127.0.0.1:1/0", fallback_path=tmp_path / "bus.jsonl")
    assert not b.healthy()
    return b


def _make_event(event_type: str, data: dict) -> Event:
    return Event(
        id=f"test-{event_type}",
        type=event_type,
        ts=datetime.now(UTC).isoformat(),
        source="test",
        data=data,
    )


# ---------------------------------------------------------------------------
# Rule evaluation (synchronous path — evaluate_once)
# ---------------------------------------------------------------------------


def test_regime_shift_to_risk_off_emits_derisk(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("regime.shifted", {"regime": "RISK_OFF", "confidence": 0.8})
    decisions = eng.evaluate_once(ev)
    names = [d.rule for d in decisions]
    assert "regime_shift_derisk" in names
    d = next(d for d in decisions if d.rule == "regime_shift_derisk")
    assert d.action == "derisk"
    assert d.confidence == pytest.approx(0.8, abs=0.01)


def test_regime_shift_to_risk_on_does_not_fire_derisk(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("regime.shifted", {"regime": "RISK_ON", "confidence": 0.9})
    decisions = eng.evaluate_once(ev)
    assert all(d.rule != "regime_shift_derisk" for d in decisions)


def test_threat_critical_emits_tighten_stops(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("threat.detected", {"level": "critical", "cve": "CVE-2026-0001"})
    decisions = eng.evaluate_once(ev)
    names = [d.rule for d in decisions]
    assert "threat_tighten_stops" in names
    d = next(d for d in decisions if d.rule == "threat_tighten_stops")
    assert d.action == "tighten_stops"
    assert d.confidence >= 0.8


def test_threat_low_does_not_fire(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("threat.detected", {"level": "low"})
    decisions = eng.evaluate_once(ev)
    assert all(d.rule != "threat_tighten_stops" for d in decisions)


def test_correlation_broken_flags_attention(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("correlation.broken", {
        "pair": ["BTC", "SPY"],
        "severity": "severe",
    })
    decisions = eng.evaluate_once(ev)
    names = [d.rule for d in decisions]
    assert "decorrelation_attention" in names
    d = next(d for d in decisions if d.rule == "decorrelation_attention")
    assert d.symbol == "BTC"
    assert d.action == "attention"


def test_sentiment_extreme_fear_contrarian_accumulate(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("sentiment.update", {"fear_greed": 15})
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "fear_greed_contrarian")
    assert d.action == "accumulate"


def test_sentiment_extreme_greed_contrarian_trim(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("sentiment.update", {"fear_greed": 85})
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "fear_greed_contrarian")
    assert d.action == "trim"


def test_sentiment_neutral_does_not_fire(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("sentiment.update", {"fear_greed": 50})
    decisions = eng.evaluate_once(ev)
    assert all(d.rule != "fear_greed_contrarian" for d in decisions)


def test_extreme_funding_fade_long(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("funding.extreme", {
        "symbol": "BTC", "bias": "long", "rate": 0.0008,
    })
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "extreme_funding_fade")
    assert d.action == "fade_long"
    assert d.symbol == "BTC"


def test_service_health_critical_pauses(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("service.health", {
        "status": "critical", "service": "webhook",
    })
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "service_health_pause")
    assert d.action == "pause_entries"
    assert d.confidence >= 0.9


def test_unrelated_event_produces_no_decisions(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    ev = _make_event("signal.generated", {"symbol": "BTC", "confidence": 0.6})
    decisions = eng.evaluate_once(ev)
    # None of the default rules target signal.generated
    assert decisions == []


# ---------------------------------------------------------------------------
# Confidence weighting and gates
# ---------------------------------------------------------------------------


def test_rule_weight_scales_confidence(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    # Bump weight of threat_tighten_stops to 0.5 → critical → 0.85 * 0.5 = 0.425
    for r in eng._rules:
        if r.name == "threat_tighten_stops":
            r.weight = 0.5
    ev = _make_event("threat.detected", {"level": "critical"})
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "threat_tighten_stops")
    assert d.base_confidence == pytest.approx(0.85, abs=0.01)
    assert d.confidence == pytest.approx(0.425, abs=0.01)


def test_confidence_clamped_to_one(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    for r in eng._rules:
        if r.name == "service_health_pause":
            r.weight = 3.0  # 0.90 * 3.0 = 2.7 → must clamp to 1.0
    ev = _make_event("service.health", {"status": "critical"})
    decisions = eng.evaluate_once(ev)
    d = next(d for d in decisions if d.rule == "service_health_pause")
    assert d.confidence == 1.0


# ---------------------------------------------------------------------------
# Adaptive weighting
# ---------------------------------------------------------------------------


def test_signal_closed_win_increases_rule_weight(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    # Simulate that decorrelation_attention recently fired on BTC.
    eng._record_attribution("BTC", "decorrelation_attention", datetime.now(UTC))

    before = {r.name: r.weight for r in eng._rules}
    close_ev = _make_event("signal.closed", {"symbol": "BTC", "pnl_usd": 150.0})
    eng._attribute_outcome(close_ev)
    after = {r.name: r.weight for r in eng._rules}
    assert after["decorrelation_attention"] > before["decorrelation_attention"]
    # Other rules untouched
    for name in after:
        if name != "decorrelation_attention":
            assert after[name] == before[name]


def test_signal_closed_loss_decreases_rule_weight(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    eng._record_attribution("ETH", "extreme_funding_fade", datetime.now(UTC))

    before = next(r.weight for r in eng._rules if r.name == "extreme_funding_fade")
    close_ev = _make_event("signal.closed", {"symbol": "ETH", "pnl_usd": -200.0})
    eng._attribute_outcome(close_ev)
    after = next(r.weight for r in eng._rules if r.name == "extreme_funding_fade")
    assert after < before


def test_rule_weight_respects_bounds(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    # Find a rule and slam it with many losses → must floor at MIN_WEIGHT
    target = eng._rules[0].name
    for _ in range(200):
        eng._record_attribution("BTC", target, datetime.now(UTC))
        eng._attribute_outcome(_make_event("signal.closed", {"symbol": "BTC", "pnl_usd": -10.0}))
    floored = next(r.weight for r in eng._rules if r.name == target)
    assert floored >= MIN_WEIGHT
    assert floored <= DEFAULT_WEIGHT

    # And many wins → caps at MAX_WEIGHT
    for _ in range(500):
        eng._record_attribution("BTC", target, datetime.now(UTC))
        eng._attribute_outcome(_make_event("signal.closed", {"symbol": "BTC", "pnl_usd": 10.0}))
    capped = next(r.weight for r in eng._rules if r.name == target)
    assert capped <= MAX_WEIGHT


def test_signal_closed_zero_pnl_is_ignored(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    eng._record_attribution("BTC", "regime_shift_derisk", datetime.now(UTC))
    before = next(r.weight for r in eng._rules if r.name == "regime_shift_derisk")
    eng._attribute_outcome(_make_event("signal.closed", {"symbol": "BTC", "pnl_usd": 0.0}))
    after = next(r.weight for r in eng._rules if r.name == "regime_shift_derisk")
    assert before == after


def test_rule_stats_and_weights_accessors(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    weights = eng.rule_weights()
    assert "regime_shift_derisk" in weights
    stats = eng.rule_stats()
    assert all("name" in s and "weight" in s and "fires" in s for s in stats)


# ---------------------------------------------------------------------------
# Custom rule registration
# ---------------------------------------------------------------------------


def test_custom_rule_can_be_registered_and_fires(bus: EventBus):
    eng = DecisionEngine(bus=bus, rules=[])

    def always_fires(ev: Event, ws) -> Decision | None:
        return Decision(
            rule="custom", action="noop", symbol="BTC",
            confidence=0.8, base_confidence=0.8,
            rationale="test", triggered_by=ev.type,
        )

    eng.register_rule("custom", always_fires, patterns=["regime.*"])
    ev = _make_event("regime.shifted", {"regime": "RISK_ON"})
    decisions = eng.evaluate_once(ev)
    assert any(d.rule == "custom" for d in decisions)


def test_rule_that_raises_is_isolated(bus: EventBus):
    eng = DecisionEngine(bus=bus, rules=[])

    def boom(ev, ws):
        raise RuntimeError("intentional")

    def fine(ev, ws):
        return Decision(
            rule="fine", action="noop", symbol=None,
            confidence=0.7, base_confidence=0.7,
            rationale="", triggered_by=ev.type,
        )

    eng.register_rule("boom", boom, patterns=["*"])
    eng.register_rule("fine", fine, patterns=["*"])
    ev = _make_event("regime.shifted", {"regime": "RISK_OFF"})
    decisions = eng.evaluate_once(ev)
    # The good rule still produces a decision even though `boom` raised.
    assert any(d.rule == "fine" for d in decisions)


# ---------------------------------------------------------------------------
# End-to-end with the live bus (subscribe → publish → verify decision.made)
# ---------------------------------------------------------------------------


def test_end_to_end_publishes_decision_made(bus: EventBus):
    eng = DecisionEngine(bus=bus)
    eng.start(start_id="0")
    try:
        bus.publish("threat.detected", {"level": "critical", "cve": "CVE-X"})
        # Fallback subscriber polls at 1s intervals — allow two cycles.
        deadline = time.time() + 5.0
        decisions = []
        while time.time() < deadline and not decisions:
            decisions = bus.replay(
                "decision.made",
                since=datetime(2000, 1, 1, tzinfo=UTC),
                limit=20,
            )
            if decisions:
                break
            time.sleep(0.2)
        assert decisions, "expected a decision.made event to be published"
        actions = [d.data.get("action") for d in decisions]
        assert "tighten_stops" in actions
    finally:
        eng.stop()


# ---------------------------------------------------------------------------
# Sanity: MIN_PUBLISH_CONFIDENCE is respected (via _evaluate path)
# ---------------------------------------------------------------------------


def test_low_confidence_decision_not_published(bus: EventBus, tmp_path):
    eng = DecisionEngine(bus=bus, rules=[])

    def weak(ev, ws):
        return Decision(
            rule="weak", action="noop", symbol=None,
            confidence=0.1, base_confidence=0.1,
            rationale="", triggered_by=ev.type,
        )

    eng.register_rule("weak", weak, patterns=["regime.*"], weight=1.0)
    # Fire via the internal _evaluate path (same one used by the subscriber).
    ev = _make_event("regime.shifted", {"regime": "RISK_ON"})
    eng._evaluate(ev, bus.get_world_state())

    # No decision.made should have been published.
    published = bus.replay(
        "decision.made",
        since=datetime(2000, 1, 1, tzinfo=UTC),
        limit=10,
    )
    assert all(p.data.get("rule") != "weak" for p in published)
    # Also sanity-check our threshold value
    assert MIN_PUBLISH_CONFIDENCE > 0.1
