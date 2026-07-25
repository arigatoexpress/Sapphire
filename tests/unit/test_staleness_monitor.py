"""Dedup / cooldown behavior for the staleness monitor's alert path.

The `monitor` fixture lives in conftest.py alongside the other unit tests.
"""

from __future__ import annotations

import time


def test_fingerprint_ignores_age_drift(monitor):
    """Ages advance every run; including them would defeat dedup entirely."""
    a = [monitor.Row("x", "p", "STALE", 10.0, 1.0, "p")]
    b = [monitor.Row("x", "p", "STALE", 99.0, 1.0, "p")]

    assert monitor.alert_fingerprint(a, []) == monitor.alert_fingerprint(b, [])


def test_fingerprint_changes_when_a_new_problem_appears(monitor):
    one = [monitor.Row("x", "p", "STALE", 10.0, 1.0, "p")]
    two = one + [monitor.Row("y", "q", "STALE", 10.0, 1.0, "q")]

    assert monitor.alert_fingerprint(one, []) != monitor.alert_fingerprint(two, [])


def test_repeat_alert_suppressed_within_cooldown(monitor, tmp_path):
    state = tmp_path / "alert_state.json"
    now = time.time()

    assert monitor.should_alert("fp1", now=now, state_path=state) is True
    monitor.record_alert("fp1", now=now, state_path=state)

    # Same problem set an hour later: stay quiet.
    assert monitor.should_alert("fp1", now=now + 3600, state_path=state) is False
    # A different problem set: alert immediately, cooldown or not.
    assert monitor.should_alert("fp2", now=now + 3600, state_path=state) is True
    # Same problem set past the cooldown: alert again.
    assert monitor.should_alert("fp1", now=now + 25 * 3600, state_path=state) is True
