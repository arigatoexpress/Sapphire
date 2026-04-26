"""Tests for lib/agents/base.py.

Covers the cycle-oriented `BaseAgent` runtime: plan/act/observe lifecycle,
event emission, stop/run_forever signalling, and the immutable
`Action`/`Result` dataclasses.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from typing import Any

import pytest

from lib.agents.base import Action, BaseAgent, Result

# --- Action / Result dataclasses -------------------------------------------


def test_action_is_frozen():
    a = Action(kind="poll", payload={"k": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.kind = "x"


def test_action_equality():
    a = Action(kind="poll", payload={"k": 1})
    b = Action(kind="poll", payload={"k": 1})
    c = Action(kind="poll", payload={"k": 2})
    assert a == b
    assert a != c


def test_action_payload_default_is_empty_dict():
    a = Action(kind="poll")
    assert a.payload == {}
    # Distinct instances share the SAME default dict factory but each call
    # produces a fresh dict (no shared-reference bug).
    a2 = Action(kind="poll")
    a2.payload  # access; cannot mutate frozen instance, but dict is mutable
    # a.payload and a2.payload should not be the same object
    assert a.payload is not a2.payload


def test_result_is_frozen_and_slotted():
    a = Action(kind="poll")
    r = Result(action=a, status="ok", payload={"v": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.status = "fail"


def test_result_equality():
    a = Action(kind="poll")
    r1 = Result(action=a, status="ok")
    r2 = Result(action=a, status="ok")
    r3 = Result(action=a, status="fail")
    assert r1 == r2
    assert r1 != r3


# --- BaseAgent abstract surface --------------------------------------------


class _NopAgent(BaseAgent):
    """Smallest concrete subclass for lifecycle tests."""

    def __init__(self, name="t", interval_sec=0, event_bus=None):
        super().__init__(name, interval_sec, event_bus)
        self.plan_calls = 0
        self.act_calls = 0
        self.observe_calls = 0
        self.act_actions: list[list[Action]] = []
        self.observation_value: dict[str, Any] = {"ok": True}

    def plan(self) -> list[Action]:
        self.plan_calls += 1
        return [Action(kind="poll", payload={"i": self.plan_calls})]

    def act(self, actions: list[Action]) -> list[Result]:
        self.act_calls += 1
        self.act_actions.append(actions)
        return [Result(action=a, status="ok", payload={}) for a in actions]

    def observe(self, results: list[Result]) -> dict[str, Any]:
        self.observe_calls += 1
        return self.observation_value


def test_baseagent_plan_act_observe_are_abstract():
    raw = BaseAgent("x", 0)
    with pytest.raises(NotImplementedError):
        raw.plan()
    with pytest.raises(NotImplementedError):
        raw.act([])
    with pytest.raises(NotImplementedError):
        raw.observe([])


def test_baseagent_constructor_clamps_negative_interval_to_zero():
    a = _NopAgent(interval_sec=-5)
    assert a.interval_sec == 0


def test_baseagent_constructor_coerces_interval_via_int():
    a = _NopAgent(interval_sec=3.7)  # type: ignore[arg-type]
    assert a.interval_sec == 3


def test_baseagent_initial_state():
    a = _NopAgent()
    assert a.cycle_count == 0
    assert a.last_cycle_started_at is None
    assert a.last_cycle_completed_at is None
    assert a.last_observation == {}


# --- run_once lifecycle ----------------------------------------------------


def test_run_once_invokes_plan_act_observe_in_order():
    a = _NopAgent()
    obs = a.run_once()
    assert obs == {"ok": True}
    assert a.plan_calls == 1
    assert a.act_calls == 1
    assert a.observe_calls == 1
    # plan output reaches act
    assert len(a.act_actions[0]) == 1
    assert a.act_actions[0][0].kind == "poll"


def test_run_once_increments_cycle_count_and_sets_timestamps():
    a = _NopAgent()
    a.run_once()
    assert a.cycle_count == 1
    assert a.last_cycle_started_at is not None
    assert a.last_cycle_completed_at is not None
    assert a.last_cycle_completed_at >= a.last_cycle_started_at


def test_run_once_stores_a_copy_of_observation():
    a = _NopAgent()
    src = {"k": "v"}
    a.observation_value = src
    a.run_once()
    # last_observation should equal but not be the same object as src
    assert a.last_observation == src
    assert a.last_observation is not src


def test_multiple_run_once_calls_increment_cycle_count():
    a = _NopAgent()
    a.run_once()
    a.run_once()
    a.run_once()
    assert a.cycle_count == 3
    assert a.plan_calls == 3
    assert a.act_calls == 3
    assert a.observe_calls == 3


# --- emit_event ------------------------------------------------------------


class _RecordingBus:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def publish(self, event_type: str, data: dict[str, Any], source: str | None = None) -> str:
        self.calls.append({"event_type": event_type, "data": data, "source": source})
        return "evt-1"


class _SourcelessBus:
    """Older bus shape that does not accept the `source` kwarg."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def publish(self, event_type: str, data: dict[str, Any]) -> str:
        self.calls.append({"event_type": event_type, "data": data})
        return "evt-2"


def test_emit_event_returns_none_when_no_bus():
    a = _NopAgent()
    assert a.emit_event("x", {"k": 1}) is None


def test_emit_event_publishes_with_agent_source():
    bus = _RecordingBus()
    a = _NopAgent(name="alpha", event_bus=bus)
    eid = a.emit_event("agent.test", {"k": 1})
    assert eid == "evt-1"
    assert bus.calls == [{"event_type": "agent.test", "data": {"k": 1}, "source": "agent:alpha"}]


def test_emit_event_falls_back_when_bus_lacks_source_kwarg():
    bus = _SourcelessBus()
    a = _NopAgent(name="alpha", event_bus=bus)
    eid = a.emit_event("agent.test", {"k": 1})
    assert eid == "evt-2"
    assert bus.calls == [{"event_type": "agent.test", "data": {"k": 1}}]


def test_run_once_emits_cycle_completed_event():
    bus = _RecordingBus()
    a = _NopAgent(name="alpha", event_bus=bus)
    a.run_once()
    assert any(c["event_type"] == "agent.cycle.completed" for c in bus.calls)
    completed = next(c for c in bus.calls if c["event_type"] == "agent.cycle.completed")
    assert completed["data"]["agent"] == "alpha"
    assert completed["data"]["cycle_count"] == 1
    assert "started_at" in completed["data"]
    assert "completed_at" in completed["data"]
    assert completed["data"]["observation"] == {"ok": True}


# --- stop / run_forever ----------------------------------------------------


def test_stop_sets_stop_event():
    a = _NopAgent()
    assert not a._stop_event.is_set()
    a.stop()
    assert a._stop_event.is_set()


def test_run_forever_exits_when_stop_called(monkeypatch):
    """run_forever should exit cleanly once stop() flips the event."""
    a = _NopAgent(interval_sec=0)

    def stop_after_first():
        time.sleep(0.05)
        a.stop()

    t = threading.Thread(target=stop_after_first, daemon=True)
    t.start()
    a.run_forever()
    t.join(timeout=1.0)
    assert a.cycle_count >= 1


def test_run_forever_continues_through_exception_in_cycle(caplog):
    """A failed cycle should be logged and the loop should continue."""

    class _FailFirstAgent(_NopAgent):
        def plan(self) -> list[Action]:
            self.plan_calls += 1
            if self.plan_calls == 1:
                raise RuntimeError("boom")
            return super().plan()

    a = _FailFirstAgent(interval_sec=0)

    def stop_after_two():
        # let the first (failing) and second (successful) cycle run
        while a.plan_calls < 2:
            time.sleep(0.01)
        time.sleep(0.05)
        a.stop()

    t = threading.Thread(target=stop_after_two, daemon=True)
    t.start()
    a.run_forever()
    t.join(timeout=2.0)
    # cycle_count only advances on successful cycles (run_once raises before increment)
    assert a.cycle_count >= 1
    assert a.plan_calls >= 2


def test_baseagent_exposes_action_and_result_in__all__():
    import lib.agents.base as base_module
    assert "Action" in base_module.__all__
    assert "Result" in base_module.__all__
    assert "BaseAgent" in base_module.__all__
