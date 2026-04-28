"""
Unit tests — CircuitBreaker state machine.

Critical paths:
  - CLOSED → OPEN after fail_max consecutive failures
  - OPEN raises CircuitBreakerOpen on check()
  - OPEN → HALF_OPEN after reset_timeout elapses
  - HALF_OPEN: success → CLOSED; failure → OPEN again
  - record_success resets failure count
  - on_open / on_close callbacks fire at the right moments
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared"))

from circuit_breaker import CircuitBreaker, CircuitBreakerOpen

# ── Helpers ──────────────────────────────────────────────────────────────────


def _open_breaker(cb: CircuitBreaker) -> None:
    """Force a breaker from CLOSED to OPEN by recording fail_max failures."""
    for _ in range(cb.fail_max):
        cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN


# ── State machine ─────────────────────────────────────────────────────────────


class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_opens_after_fail_max_consecutive_failures(self):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED  # not open yet
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_check_raises_when_open(self):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=60)
        _open_breaker(cb)
        try:
            cb.check()
            raise AssertionError("Should have raised CircuitBreakerOpen")
        except CircuitBreakerOpen:
            pass

    def test_check_passes_when_closed(self):
        cb = CircuitBreaker("test", fail_max=3, reset_timeout=60)
        cb.check()  # should not raise

    def test_transitions_to_half_open_after_timeout(self, monkeypatch):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=1)
        _open_breaker(cb)
        # Advance internal clock past reset_timeout
        cb._last_failure_time = time.monotonic() - 2  # 2s ago, reset is 1s
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_success_in_half_open_closes_breaker(self, monkeypatch):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=1)
        _open_breaker(cb)
        cb._last_failure_time = time.monotonic() - 2
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_failure_in_half_open_reopens(self, monkeypatch):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=1)
        _open_breaker(cb)
        cb._last_failure_time = time.monotonic() - 2
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_record_success_resets_failure_count(self):
        cb = CircuitBreaker("test", fail_max=5, reset_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitBreaker.CLOSED

    def test_does_not_open_twice(self):
        """Recording extra failures while already OPEN should not re-notify."""
        notifications = []
        cb = CircuitBreaker(
            "test", fail_max=2, reset_timeout=60, on_open=lambda n: notifications.append(n)
        )
        _open_breaker(cb)
        cb.record_failure()  # extra failure while already OPEN
        assert len(notifications) == 1  # on_open called exactly once

    def test_failure_count_increments_even_when_open(self):
        cb = CircuitBreaker("test", fail_max=2, reset_timeout=60)
        _open_breaker(cb)
        initial = cb._failure_count
        cb.record_failure()
        assert cb._failure_count == initial + 1


# ── Callbacks ─────────────────────────────────────────────────────────────────


class TestCircuitBreakerCallbacks:
    def test_on_open_fires_when_breaker_opens(self):
        events = []
        cb = CircuitBreaker(
            "cb1", fail_max=2, reset_timeout=60, on_open=lambda n: events.append(("open", n))
        )
        _open_breaker(cb)
        assert events == [("open", "cb1")]

    def test_on_close_fires_on_recovery_from_open(self, monkeypatch):
        events = []
        cb = CircuitBreaker(
            "cb2",
            fail_max=2,
            reset_timeout=1,
            on_open=lambda n: None,
            on_close=lambda n: events.append(("close", n)),
        )
        _open_breaker(cb)
        cb._last_failure_time = time.monotonic() - 2
        _ = cb.state  # trigger HALF_OPEN transition
        cb.record_success()
        assert events == [("close", "cb2")]

    def test_on_close_not_fired_on_normal_success(self):
        events = []
        cb = CircuitBreaker(
            "cb3", fail_max=3, reset_timeout=60, on_close=lambda n: events.append(n)
        )
        cb.record_success()
        assert events == []

    def test_callback_exception_does_not_crash_breaker(self):
        def bad_callback(name):
            raise RuntimeError("boom")

        cb = CircuitBreaker("cb4", fail_max=1, reset_timeout=60, on_open=bad_callback)
        cb.record_failure()  # triggers on_open → callback raises → should be swallowed
        assert cb.state == CircuitBreaker.OPEN


# ── Status / repr ─────────────────────────────────────────────────────────────


class TestCircuitBreakerIntrospection:
    def test_status_returns_dict(self):
        cb = CircuitBreaker("cb5", fail_max=3, reset_timeout=60)
        s = cb.status()
        assert s["name"] == "cb5"
        assert s["state"] == CircuitBreaker.CLOSED
        assert s["failure_count"] == 0

    def test_status_seconds_until_retry_positive_when_open(self):
        cb = CircuitBreaker("cb6", fail_max=2, reset_timeout=60)
        _open_breaker(cb)
        s = cb.status()
        assert s["seconds_until_retry"] > 0

    def test_repr_contains_name_and_state(self):
        cb = CircuitBreaker("mybreaker", fail_max=3, reset_timeout=60)
        assert "mybreaker" in repr(cb)
        assert "closed" in repr(cb)
