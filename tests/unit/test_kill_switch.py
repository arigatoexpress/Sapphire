"""Tests for lib/core/kill_switch.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

UTC = UTC

import pytest

from lib.core.kill_switch import (
    KillSwitch,
    KillSwitchEvent,
    get_kill_switch,
    reset_kill_switch,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Clock:
    """Deterministic clock for time-based tests."""

    def __init__(self, start: datetime | None = None):
        self.t = start or datetime(2026, 4, 18, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.t

    def advance(self, **kwargs) -> None:
        self.t = self.t + timedelta(**kwargs)


class _EventRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class _NotifyRecorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def __call__(self, text: str, *, priority: str = "p1", **_) -> dict:
        self.messages.append({"text": text, "priority": priority})
        return {"ok": True}


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def recorders():
    return _EventRecorder(), _NotifyRecorder()


@pytest.fixture
def switch(clock, recorders):
    publisher, notifier = recorders
    return KillSwitch(
        max_drawdown_24h=0.05,
        max_drawdown_total=0.15,
        recovery_threshold=0.02,
        publish_event=publisher,
        notify=notifier,
        now=clock.now,
    )


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


def test_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        KillSwitch(max_drawdown_24h=0)
    with pytest.raises(ValueError):
        KillSwitch(max_drawdown_total=1.5)
    with pytest.raises(ValueError):
        KillSwitch(recovery_threshold=-0.01)


def test_initial_state_is_clean(switch):
    assert not switch.is_active
    status = switch.status()
    assert status.drawdown_24h == 0.0
    assert status.drawdown_total == 0.0
    assert status.peak_all_time is None


# ---------------------------------------------------------------------------
# Normal operation
# ---------------------------------------------------------------------------


def test_shallow_drawdown_does_not_trigger(switch, recorders, clock):
    pub, notifier = recorders
    assert switch.check(100_000) is False
    clock.advance(hours=1)
    assert switch.check(97_000) is False  # 3% DD, under 5%
    assert not switch.is_active
    assert pub.events == []
    assert notifier.messages == []


def test_24h_drawdown_activates(switch, recorders, clock):
    pub, notifier = recorders
    switch.check(100_000)
    clock.advance(hours=2)
    halted = switch.check(94_500)  # 5.5% DD, crosses 5%
    assert halted is True
    assert switch.is_active
    assert len(pub.events) == 1
    assert pub.events[0][0] == "kill_switch.activated"
    assert len(notifier.messages) == 1
    assert notifier.messages[0]["priority"] == "p0"
    assert "KILL SWITCH ACTIVATED" in notifier.messages[0]["text"]


def test_total_drawdown_activates_independently(switch, recorders, clock):
    """A long slow bleed can trip total DD without ever tripping 24h DD."""
    pub, _ = recorders
    # Seed a high peak
    switch.check(100_000)
    # Slide down in small 24h windows, each < 5%, cumulatively > 15%
    values = [96_000, 92_000, 88_000, 84_000]
    for v in values:
        clock.advance(hours=25)  # push previous samples out of the 24h window
        switch.check(v)
        if switch.is_active:
            break
    assert switch.is_active
    assert pub.events[-1][0] == "kill_switch.activated"
    assert "total drawdown" in switch.status().reason


def test_already_active_no_double_emit(switch, recorders, clock):
    pub, notifier = recorders
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(90_000)  # activate
    clock.advance(hours=1)
    switch.check(88_000)  # still halted, should NOT emit a second activation
    assert len([e for e in pub.events if e[0] == "kill_switch.activated"]) == 1
    assert len(notifier.messages) == 1


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


def test_recovery_below_threshold_stays_active(switch, clock):
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(90_000)  # activate
    assert switch.is_active
    assert switch.check_recovery(0.01) is False  # < 2% threshold
    assert switch.is_active


def test_recovery_at_or_above_threshold_deactivates(switch, recorders, clock):
    pub, notifier = recorders
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(90_000)
    assert switch.check_recovery(0.025) is True
    assert not switch.is_active
    deactivations = [e for e in pub.events if e[0] == "kill_switch.deactivated"]
    assert len(deactivations) == 1
    assert "DEACTIVATED" in notifier.messages[-1]["text"]


def test_recovery_on_inactive_is_noop(switch, recorders):
    pub, _ = recorders
    assert switch.check_recovery(0.50) is True
    assert pub.events == []


# ---------------------------------------------------------------------------
# Sizing / halting behavior
# ---------------------------------------------------------------------------


def test_scale_confidence_zeros_when_active(switch, clock):
    assert switch.scale_confidence(0.8) == pytest.approx(0.8)
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(90_000)  # activate
    assert switch.scale_confidence(0.8) == 0.0
    assert switch.should_halt() is True


def test_check_rejects_invalid_value(switch):
    with pytest.raises(ValueError):
        switch.check(0)
    with pytest.raises(ValueError):
        switch.check(-1000)


# ---------------------------------------------------------------------------
# Peak / 24h-window semantics
# ---------------------------------------------------------------------------


def test_peak_all_time_is_monotonic(switch, clock):
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(110_000)
    clock.advance(hours=1)
    switch.check(105_000)
    assert switch.status().peak_all_time == 110_000


def test_24h_window_forgets_old_samples(switch, clock):
    switch.check(100_000)  # old peak at T0
    clock.advance(hours=25)  # push it out of the 24h window
    switch.check(95_000)
    # Within the 24h window, the only peak is 95k, so DD = 0
    assert switch.status().drawdown_24h == 0.0
    # But all-time peak stays 100k → total DD = 5%
    assert switch.status().drawdown_total == pytest.approx(0.05, rel=1e-3)


def test_event_payload_fields(switch, recorders, clock):
    pub, _ = recorders
    switch.check(100_000)
    clock.advance(hours=2)
    switch.check(90_000)
    event_type, data = pub.events[0]
    assert event_type == "kill_switch.activated"
    assert data["portfolio_value"] == 90_000
    assert "drawdown_24h" in data
    assert "drawdown_total" in data
    assert "timestamp" in data
    assert "reason" in data


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


def test_publisher_failure_does_not_break_check(clock):
    def broken_pub(*args, **kwargs):
        raise RuntimeError("redis is sad")

    ks = KillSwitch(publish_event=broken_pub, notify=lambda *a, **k: None, now=clock.now)
    ks.check(100_000)
    clock.advance(hours=1)
    # Must not raise even though publisher blows up
    assert ks.check(90_000) is True
    assert ks.is_active


def test_notifier_failure_does_not_break_check(clock):
    def broken_notify(*args, **kwargs):
        raise RuntimeError("telegram 502")

    ks = KillSwitch(publish_event=lambda *a, **k: None, notify=broken_notify, now=clock.now)
    ks.check(100_000)
    clock.advance(hours=1)
    assert ks.check(90_000) is True
    assert ks.is_active


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance():
    reset_kill_switch()
    a = get_kill_switch()
    b = get_kill_switch()
    assert a is b
    reset_kill_switch()


def test_reset_clears_state(switch, clock):
    switch.check(100_000)
    clock.advance(hours=1)
    switch.check(90_000)
    assert switch.is_active
    switch.reset()
    assert not switch.is_active
    assert switch.status().peak_all_time is None


def test_event_dataclass_serialization():
    ev = KillSwitchEvent(
        kind="activated",
        timestamp=datetime(2026, 4, 18, tzinfo=UTC),
        reason="test",
        portfolio_value=90_000.123,
        drawdown_24h=0.055,
        drawdown_total=0.055,
    )
    d = ev.to_dict()
    assert d["kind"] == "activated"
    assert d["portfolio_value"] == 90_000.12
    assert d["drawdown_24h"] == 0.055
    assert d["timestamp"].startswith("2026-04-18")
