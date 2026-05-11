"""Tests for ``lib/core/heartbeat.py`` — the 60-second component state machine.

Heartbeat is safety-critical: it owns the per-component HEALTHY → DEGRADED
→ FAILED → RECOVERING state machine, the self-heal kickstart path, and
the Telegram escalation cadence. This module had no test coverage before
this file. All tests mock subprocess + Telegram + event_bus so nothing
real fires — the focus is the state-machine contract.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix only (getuid)")

from lib.core import heartbeat as hb

# ── _tcp_ok ────────────────────────────────────────────────────────────


def test_tcp_ok_success(monkeypatch):
    fake_sock = MagicMock()
    fake_sock.__enter__.return_value = fake_sock
    fake_sock.__exit__.return_value = False
    monkeypatch.setattr(hb.socket, "create_connection", lambda *a, **kw: fake_sock)

    ok, err = hb._tcp_ok("127.0.0.1", 6379)

    assert ok is True
    assert err == ""


def test_tcp_ok_connection_refused(monkeypatch):
    def boom(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(hb.socket, "create_connection", boom)

    ok, err = hb._tcp_ok("127.0.0.1", 6379)

    assert ok is False
    assert "refused" in err


def test_tcp_ok_timeout(monkeypatch):
    def boom(*a, **kw):
        raise TimeoutError("took too long")

    monkeypatch.setattr(hb.socket, "create_connection", boom)

    ok, err = hb._tcp_ok("127.0.0.1", 6379)

    assert ok is False
    assert "took too long" in err


# ── _http_ok ───────────────────────────────────────────────────────────


def test_http_ok_success(monkeypatch):
    fake_response = MagicMock()
    fake_response.read.return_value = b"ok"
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    monkeypatch.setattr(hb.urllib.request, "urlopen", lambda *a, **kw: fake_response)

    ok, err = hb._http_ok("http://x.local/health")

    assert ok is True
    assert err == ""


@pytest.mark.parametrize("status_code", [401, 403, 405])
def test_http_ok_treats_auth_codes_as_alive(monkeypatch, status_code):
    """401/403/405 means the service is up — it just won't authorize us."""

    def raise_http_error(*a, **kw):
        raise urllib.error.HTTPError(url="http://x", code=status_code, msg="x", hdrs={}, fp=None)

    monkeypatch.setattr(hb.urllib.request, "urlopen", raise_http_error)

    ok, err = hb._http_ok("http://x.local/health")

    assert ok is True
    assert err == ""


@pytest.mark.parametrize("status_code", [500, 502, 503, 404])
def test_http_ok_other_http_errors_fail(monkeypatch, status_code):
    def raise_http_error(*a, **kw):
        raise urllib.error.HTTPError(url="http://x", code=status_code, msg="x", hdrs={}, fp=None)

    monkeypatch.setattr(hb.urllib.request, "urlopen", raise_http_error)

    ok, err = hb._http_ok("http://x.local/health")

    assert ok is False
    assert str(status_code) in err


def test_http_ok_network_error_fails(monkeypatch):
    def boom(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(hb.urllib.request, "urlopen", boom)

    ok, err = hb._http_ok("http://x.local/health")

    assert ok is False
    assert "refused" in err


# ── _launchctl_status ──────────────────────────────────────────────────


def test_launchctl_status_running(monkeypatch):
    monkeypatch.setattr(
        hb.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0], returncode=0, stdout="12345 0 ai.test.gateway\n", stderr=""
        ),
    )

    ok, err = hb._launchctl_status("ai.test.gateway")

    assert ok is True
    assert err == ""


def test_launchctl_status_not_running_dash_pid(monkeypatch):
    """launchctl prints '-' for the PID column when the job isn't running."""
    monkeypatch.setattr(
        hb.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0], returncode=0, stdout="-\t0\tai.test.gateway\n", stderr=""
        ),
    )

    ok, err = hb._launchctl_status("ai.test.gateway")

    assert ok is False
    assert "not running" in err


def test_launchctl_status_not_listed(monkeypatch):
    monkeypatch.setattr(
        hb.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0], returncode=1, stdout="", stderr="Could not find service\n"
        ),
    )

    ok, err = hb._launchctl_status("ai.missing.gateway")

    assert ok is False
    assert "not listed" in err


def test_launchctl_status_subprocess_error(monkeypatch):
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="launchctl", timeout=5)

    monkeypatch.setattr(hb.subprocess, "run", boom)

    ok, err = hb._launchctl_status("ai.x.gateway")

    assert ok is False
    assert err  # any error string is fine


# ── ComponentStatus defaults ───────────────────────────────────────────


def test_component_status_defaults():
    comp = hb.ComponentStatus(name="x")

    assert comp.state == hb.ComponentState.HEALTHY
    assert comp.consecutive_failures == 0
    assert comp.consecutive_healthy == 0
    assert comp.last_error == ""
    assert comp.last_checked == 0.0
    assert comp.last_alerted == 0.0
    assert comp.restart_attempts == 0
    assert comp.launchctl_label == ""


# ── State machine: HEALTHY → DEGRADED → FAILED ──────────────────────────


def _patch_check(monkeypatch, ok: bool, err: str = "") -> None:
    monkeypatch.setattr(hb, "_check_fn", lambda comp: (ok, err))
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: None)


def _make_monitor(monkeypatch, dry_run: bool = True) -> hb.HeartbeatMonitor:
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: None)
    monitor = hb.HeartbeatMonitor(interval=1, dry_run=dry_run)
    monitor._components = [hb.ComponentStatus(name="alpha")]
    return monitor


def test_state_healthy_after_first_success(monkeypatch):
    _patch_check(monkeypatch, ok=True)
    monitor = _make_monitor(monkeypatch)

    monitor.run_once()
    comp = monitor._components[0]

    assert comp.state == hb.ComponentState.HEALTHY
    assert comp.consecutive_failures == 0
    assert comp.consecutive_healthy == 1


def test_state_degraded_after_first_failure(monkeypatch):
    _patch_check(monkeypatch, ok=False, err="boom")
    monitor = _make_monitor(monkeypatch)

    monitor.run_once()
    comp = monitor._components[0]

    assert comp.state == hb.ComponentState.DEGRADED
    assert comp.consecutive_failures == 1
    assert comp.last_error == "boom"


def test_state_failed_after_threshold_failures(monkeypatch):
    _patch_check(monkeypatch, ok=False, err="still down")
    monitor = _make_monitor(monkeypatch)

    for _ in range(hb.FAIL_THRESHOLD):
        monitor.run_once()
    comp = monitor._components[0]

    assert comp.state == hb.ComponentState.FAILED
    assert comp.consecutive_failures == hb.FAIL_THRESHOLD


def test_state_failed_recovers_after_success(monkeypatch):
    """FAILED → HEALTHY directly when launchctl_label is empty (no heal path)."""
    monitor = _make_monitor(monkeypatch)

    _patch_check(monkeypatch, ok=False, err="down")
    for _ in range(hb.FAIL_THRESHOLD):
        monitor.run_once()
    assert monitor._components[0].state == hb.ComponentState.FAILED

    _patch_check(monkeypatch, ok=True)
    monitor.run_once()
    comp = monitor._components[0]

    # Direct HEALTHY transition because no launchctl_label was assigned.
    assert comp.state == hb.ComponentState.HEALTHY
    assert comp.consecutive_failures == 0
    assert comp.last_error == ""


def test_state_degraded_resets_to_healthy_on_success(monkeypatch):
    monitor = _make_monitor(monkeypatch)

    _patch_check(monkeypatch, ok=False, err="dropped")
    monitor.run_once()
    assert monitor._components[0].state == hb.ComponentState.DEGRADED

    _patch_check(monkeypatch, ok=True)
    monitor.run_once()

    assert monitor._components[0].state == hb.ComponentState.HEALTHY
    assert monitor._components[0].consecutive_failures == 0


# ── Self-heal RECOVERING flow ──────────────────────────────────────────


def test_failed_with_launchctl_heals_to_recovering(monkeypatch):
    monitor = _make_monitor(monkeypatch, dry_run=False)
    monitor._components = [hb.ComponentStatus(name="pm-bot", launchctl_label="com.sapphire.pm-bot")]

    _patch_check(monkeypatch, ok=False, err="down")
    monkeypatch.setattr(hb, "_attempt_heal", lambda comp: True)

    for _ in range(hb.FAIL_THRESHOLD):
        monitor.run_once()
    comp = monitor._components[0]

    assert comp.state == hb.ComponentState.RECOVERING
    assert comp.consecutive_healthy == 0


def test_recovering_returns_to_healthy_after_recover_cycles(monkeypatch):
    monitor = _make_monitor(monkeypatch, dry_run=False)
    monitor._components = [
        hb.ComponentStatus(
            name="pm-bot",
            launchctl_label="com.sapphire.pm-bot",
            state=hb.ComponentState.RECOVERING,
        )
    ]

    _patch_check(monkeypatch, ok=True)

    for _ in range(hb.RECOVER_CYCLES - 1):
        monitor.run_once()
        assert monitor._components[0].state == hb.ComponentState.RECOVERING

    monitor.run_once()
    comp = monitor._components[0]
    assert comp.state == hb.ComponentState.HEALTHY
    assert comp.consecutive_healthy == 0


def test_dry_run_skips_telegram_and_heal(monkeypatch):
    """Dry run: failure transition must NOT call _send_telegram or _attempt_heal."""
    sent: list[str] = []
    healed: list[str] = []
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: sent.append(msg))
    monkeypatch.setattr(hb, "_attempt_heal", lambda comp: healed.append(comp.name) or True)
    monkeypatch.setattr(hb, "_check_fn", lambda comp: (False, "down"))
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [hb.ComponentStatus(name="pm-bot", launchctl_label="com.sapphire.pm-bot")]

    for _ in range(hb.FAIL_THRESHOLD):
        monitor.run_once()

    assert sent == []
    assert healed == []
    # State machine still progresses normally.
    assert monitor._components[0].state == hb.ComponentState.FAILED


# ── Escalation cadence ─────────────────────────────────────────────────


def test_failed_re_alert_only_after_escalate_interval(monkeypatch):
    """A FAILED component re-alerts only every ESCALATE_INTERVAL seconds."""
    sent: list[str] = []
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: sent.append(msg))
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)
    monkeypatch.setattr(hb, "_check_fn", lambda comp: (False, "down"))
    monkeypatch.setattr(hb, "_attempt_heal", lambda comp: False)

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=False)
    monitor._components = [hb.ComponentStatus(name="alpha")]

    fake_time = {"value": 1_000.0}
    monkeypatch.setattr(hb.time, "time", lambda: fake_time["value"])

    # First three failures push alpha to FAILED — one alert fires.
    for _ in range(hb.FAIL_THRESHOLD):
        monitor.run_once()
    assert len(sent) == 1

    # Run again immediately — still FAILED, but no re-alert.
    monitor.run_once()
    assert len(sent) == 1

    # Advance just under ESCALATE_INTERVAL — still no re-alert.
    fake_time["value"] += hb.ESCALATE_INTERVAL - 1
    monitor.run_once()
    assert len(sent) == 1

    # Cross the boundary — re-alert fires.
    fake_time["value"] += 2
    monitor.run_once()
    assert len(sent) == 2


# ── _publish_summary overall status ────────────────────────────────────


def test_publish_summary_overall_critical_when_any_failed(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(hb, "_publish_event", lambda payload: captured.append(payload))
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: None)

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [
        hb.ComponentStatus(name="ok-1", state=hb.ComponentState.HEALTHY),
        hb.ComponentStatus(name="bad-1", state=hb.ComponentState.FAILED),
    ]

    monitor._publish_summary()

    summary_events = [e for e in captured if e.get("summary")]
    assert summary_events
    assert summary_events[-1]["overall"] == "critical"
    assert "bad-1" in summary_events[-1]["failing"]


def test_publish_summary_overall_degraded_with_no_failed(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(hb, "_publish_event", lambda payload: captured.append(payload))

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [
        hb.ComponentStatus(name="ok-1", state=hb.ComponentState.HEALTHY),
        hb.ComponentStatus(name="degraded-1", state=hb.ComponentState.DEGRADED),
    ]

    monitor._publish_summary()

    summary = next(e for e in captured if e.get("summary"))
    assert summary["overall"] == "degraded"
    assert "degraded-1" in summary["failing"]


def test_publish_summary_overall_nominal_when_all_healthy(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(hb, "_publish_event", lambda payload: captured.append(payload))

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [
        hb.ComponentStatus(name=f"ok-{i}", state=hb.ComponentState.HEALTHY) for i in range(3)
    ]

    monitor._publish_summary()

    summary = next(e for e in captured if e.get("summary"))
    assert summary["overall"] == "nominal"
    assert summary["failing"] == []


def test_publish_summary_recovering_counts_as_degraded(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(hb, "_publish_event", lambda payload: captured.append(payload))

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [
        hb.ComponentStatus(name="ok-1", state=hb.ComponentState.HEALTHY),
        hb.ComponentStatus(name="recovering-1", state=hb.ComponentState.RECOVERING),
    ]

    monitor._publish_summary()

    summary = next(e for e in captured if e.get("summary"))
    assert summary["overall"] == "degraded"
    # RECOVERING is NOT counted in `failing` (it's mid-recovery, not failing).
    assert summary["failing"] == []


# ── run_once contract ──────────────────────────────────────────────────


def test_run_once_returns_per_component_status(monkeypatch):
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)
    monkeypatch.setattr(hb, "_send_telegram", lambda msg: None)

    def varying_check(comp):
        if comp.name == "ok":
            return (True, "")
        return (False, "down")

    monkeypatch.setattr(hb, "_check_fn", varying_check)

    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)
    monitor._components = [
        hb.ComponentStatus(name="ok"),
        hb.ComponentStatus(name="bad"),
    ]

    results = monitor.run_once()

    assert results["ok"]["state"] == "healthy"
    assert results["ok"]["consecutive_failures"] == 0
    assert results["bad"]["state"] == "degraded"
    assert results["bad"]["consecutive_failures"] == 1
    assert results["bad"]["last_error"] == "down"


# ── _attempt_heal ──────────────────────────────────────────────────────


def test_attempt_heal_no_label_returns_false():
    comp = hb.ComponentStatus(name="x")  # no launchctl_label

    assert hb._attempt_heal(comp) is False


def test_attempt_heal_kickstart_success(monkeypatch):
    monkeypatch.setattr(hb.os, "getuid", lambda: 501)
    monkeypatch.setattr(
        hb.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=a[0], returncode=0, stdout="", stderr=""),
    )

    comp = hb.ComponentStatus(name="pm-bot", launchctl_label="com.sapphire.pm-bot")
    result = hb._attempt_heal(comp)

    assert result is True
    assert comp.restart_attempts == 1


def test_attempt_heal_kickstart_failure_still_increments(monkeypatch):
    monkeypatch.setattr(hb.os, "getuid", lambda: 501)
    monkeypatch.setattr(
        hb.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=a[0], returncode=1, stdout="", stderr="not loaded"
        ),
    )

    comp = hb.ComponentStatus(name="pm-bot", launchctl_label="com.sapphire.pm-bot")
    result = hb._attempt_heal(comp)

    assert result is False
    assert comp.restart_attempts == 1


def test_attempt_heal_subprocess_exception_returns_false(monkeypatch):
    monkeypatch.setattr(hb.os, "getuid", lambda: 501)

    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="launchctl", timeout=15)

    monkeypatch.setattr(hb.subprocess, "run", boom)

    comp = hb.ComponentStatus(name="pm-bot", launchctl_label="com.sapphire.pm-bot")
    result = hb._attempt_heal(comp)

    assert result is False
    assert comp.restart_attempts == 1


# ── Telegram + event_bus best-effort ───────────────────────────────────


def test_send_telegram_swallows_exceptions(monkeypatch):
    """Telegram must never crash the heartbeat sweep."""

    def boom(*a, **kw):
        raise OSError("notify tool errored")

    monkeypatch.setattr(hb.subprocess, "run", boom)
    monkeypatch.setattr(hb.Path, "exists", lambda self: True)

    # Should not raise.
    hb._send_telegram("test message")


def test_publish_event_swallows_exceptions(monkeypatch):
    """Event bus failure must never crash the heartbeat sweep."""

    def boom(*a, **kw):
        raise RuntimeError("redis is down")

    with patch("lib.core.event_bus.get_bus", side_effect=boom):
        hb._publish_event({"x": 1})  # Should not raise.


# ── HeartbeatMonitor lifecycle ─────────────────────────────────────────


def test_monitor_default_components_built():
    monitor = hb.HeartbeatMonitor(interval=1, dry_run=True)

    names = {comp.name for comp in monitor._components}
    assert "control-plane" in names
    assert "dashboard" in names
    assert "inference-proxy" in names
    assert "redis" in names


def test_monitor_start_is_idempotent(monkeypatch):
    monkeypatch.setattr(hb, "_check_fn", lambda comp: (True, ""))
    monkeypatch.setattr(hb, "_publish_event", lambda payload: None)

    monitor = hb.HeartbeatMonitor(interval=10_000, dry_run=True)
    monitor._components = [hb.ComponentStatus(name="ok")]

    monitor.start()
    first_thread = monitor._thread
    monitor.start()  # second call must NOT spawn a new thread
    assert monitor._thread is first_thread

    monitor.stop()
