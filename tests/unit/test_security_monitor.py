"""Tests for lib/core/security_monitor.py.

The security monitor aggregates signals from the kill switch + the
:mod:`lib.security` family. ``refresh()`` swallows every per-module
exception so a single broken collector cannot destabilize the
dashboard. Status scoring, label thresholds, the singleton, and
``start()`` idempotency are all unit-testable without touching the
network or any LaunchAgent.
"""

from __future__ import annotations

import sys
import threading

import lib.core.security_monitor as sm

# ---------------------------------------------------------------------------
# SecurityStatus dataclass
# ---------------------------------------------------------------------------


def test_security_status_to_dict_round_trip_default():
    status = sm.SecurityStatus()
    payload = status.to_dict()
    assert payload["score"] == 100.0
    assert payload["label"] == "SECURE"
    assert payload["active_threats"] == []
    assert payload["kill_switch_active"] is False
    assert payload["dependency_issues"] == 0
    assert payload["model_anomalies"] == 0
    assert payload["network_alerts"] == 0
    assert isinstance(payload["last_checked"], str)


def test_security_status_to_dict_with_active_threats():
    status = sm.SecurityStatus(
        score=42.5,
        label="DEGRADED",
        active_threats=["x", "y"],
        kill_switch_active=True,
        dependency_issues=2,
        model_anomalies=1,
        network_alerts=0,
    )
    payload = status.to_dict()
    assert payload["score"] == 42.5
    assert payload["label"] == "DEGRADED"
    assert payload["active_threats"] == ["x", "y"]
    assert payload["kill_switch_active"] is True
    assert payload["dependency_issues"] == 2


# ---------------------------------------------------------------------------
# SecurityMonitor.refresh — graceful degradation
# ---------------------------------------------------------------------------


def test_refresh_returns_secure_when_collectors_missing(monkeypatch):
    """When every optional collector raises ImportError, refresh must
    still complete and report SECURE — fail-open for visibility, not
    fail-closed for trading. The aggregator only reports observed
    threats, never imagined ones."""
    # Strip the lazily imported modules so the in-function imports raise.
    for name in (
        "lib.core.security_kill_switch",
        "lib.security.dependency_scanner",
        "lib.security.model_monitor",
    ):
        monkeypatch.setitem(sys.modules, name, None)
    monitor = sm.SecurityMonitor(poll_interval=1)
    status = monitor.refresh()
    assert status.score == 100.0
    assert status.label == "SECURE"
    assert status.active_threats == []
    assert status.kill_switch_active is False


def test_refresh_marks_critical_when_kill_switch_active(monkeypatch):
    """Active kill switch (-40) plus 5 critical CVEs (capped at -30) crosses
    the CRITICAL threshold. Verifies score arithmetic + label boundary."""

    fake_ks_module = type(sys)("lib.core.security_kill_switch")

    class _Switch:
        def is_active(self) -> bool:
            return True

    fake_ks_module.get_security_kill_switch = lambda: _Switch()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.core.security_kill_switch", fake_ks_module)

    fake_dep_module = type(sys)("lib.security.dependency_scanner")

    class _Vuln:
        severity = "CRITICAL"

    class _Report:
        vulnerabilities = [_Vuln() for _ in range(5)]

    class _Scanner:
        def scan(self):
            return _Report()

    fake_dep_module.DependencyScanner = _Scanner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.dependency_scanner", fake_dep_module)

    monitor = sm.SecurityMonitor()
    status = monitor.refresh()
    # 100 - 40 - 30 = 30 → CRITICAL.
    assert status.score == 30.0
    assert status.label == "CRITICAL"
    assert status.kill_switch_active is True
    assert any("security_kill_switch:ACTIVE" in t for t in status.active_threats)


def test_refresh_score_floor_at_zero(monkeypatch):
    """Score never goes below zero, even if collectors over-deduct."""
    fake_ks_module = type(sys)("lib.core.security_kill_switch")

    class _Switch:
        def is_active(self) -> bool:
            return True

    fake_ks_module.get_security_kill_switch = lambda: _Switch()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.core.security_kill_switch", fake_ks_module)

    # Lots of CVEs and model anomalies → cap means minimum score is 100-40-30-20=10.
    fake_dep = type(sys)("lib.security.dependency_scanner")

    class _Vuln:
        severity = "CRITICAL"

    class _Report:
        vulnerabilities = [_Vuln() for _ in range(50)]

    class _Scanner:
        def scan(self):
            return _Report()

    fake_dep.DependencyScanner = _Scanner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.dependency_scanner", fake_dep)

    fake_model = type(sys)("lib.security.model_monitor")

    class _MM:
        def check_all(self):
            return [{"severity": "HIGH"}] * 50

    fake_model.ModelMonitor = _MM  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.model_monitor", fake_model)

    monitor = sm.SecurityMonitor()
    status = monitor.refresh()
    assert status.score >= 0
    # 100-40-30-20 = 10 → still CRITICAL.
    assert status.score == 10.0
    assert status.label == "CRITICAL"


def test_refresh_label_thresholds(monkeypatch):
    """Label boundaries: >=80 SECURE, 50-79 DEGRADED, <50 CRITICAL."""
    fake_ks_module = type(sys)("lib.core.security_kill_switch")

    class _Switch:
        def is_active(self) -> bool:
            return False

    fake_ks_module.get_security_kill_switch = lambda: _Switch()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.core.security_kill_switch", fake_ks_module)

    # 2 critical CVEs → -20 → 80 → still SECURE (boundary).
    fake_dep = type(sys)("lib.security.dependency_scanner")

    class _Vuln:
        severity = "CRITICAL"

    class _Report:
        vulnerabilities = [_Vuln() for _ in range(2)]

    class _Scanner:
        def scan(self):
            return _Report()

    fake_dep.DependencyScanner = _Scanner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.dependency_scanner", fake_dep)

    monitor = sm.SecurityMonitor()
    status = monitor.refresh()
    assert status.score == 80.0
    assert status.label == "SECURE"


def test_refresh_label_degraded_when_score_in_middle_band(monkeypatch):
    """Force score=60 → DEGRADED."""
    fake_ks_module = type(sys)("lib.core.security_kill_switch")

    class _Switch:
        def is_active(self) -> bool:
            return False

    fake_ks_module.get_security_kill_switch = lambda: _Switch()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.core.security_kill_switch", fake_ks_module)

    fake_dep = type(sys)("lib.security.dependency_scanner")

    class _Vuln:
        severity = "CRITICAL"

    class _Report:
        vulnerabilities = [_Vuln() for _ in range(4)]  # capped at -30 → 70

    class _Scanner:
        def scan(self):
            return _Report()

    fake_dep.DependencyScanner = _Scanner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.dependency_scanner", fake_dep)

    fake_model = type(sys)("lib.security.model_monitor")

    class _MM:
        def check_all(self):
            return [{"severity": "HIGH"}, {"severity": "HIGH"}]  # -10 → 60

    fake_model.ModelMonitor = _MM  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.model_monitor", fake_model)

    monitor = sm.SecurityMonitor()
    status = monitor.refresh()
    assert status.score == 60.0
    assert status.label == "DEGRADED"


def test_refresh_skips_collector_that_raises(monkeypatch):
    """If a collector raises arbitrarily (e.g. network down), refresh still
    completes and the others contribute their share."""
    fake_ks_module = type(sys)("lib.core.security_kill_switch")

    class _Switch:
        def is_active(self) -> bool:
            return True

    fake_ks_module.get_security_kill_switch = lambda: _Switch()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.core.security_kill_switch", fake_ks_module)

    fake_dep = type(sys)("lib.security.dependency_scanner")

    class _Scanner:
        def scan(self):
            raise RuntimeError("OSV.dev down")

    fake_dep.DependencyScanner = _Scanner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "lib.security.dependency_scanner", fake_dep)

    monitor = sm.SecurityMonitor()
    status = monitor.refresh()
    # Kill switch contributes -40. Dependency scan failed → 0 issues recorded.
    assert status.score == 60.0
    assert status.label == "DEGRADED"
    assert status.kill_switch_active is True
    assert status.dependency_issues == 0


# ---------------------------------------------------------------------------
# get_status / start / singleton
# ---------------------------------------------------------------------------


def test_get_status_returns_latest_refresh(monkeypatch):
    monitor = sm.SecurityMonitor()
    # Strip collectors so refresh produces a deterministic baseline.
    for name in (
        "lib.core.security_kill_switch",
        "lib.security.dependency_scanner",
        "lib.security.model_monitor",
    ):
        monkeypatch.setitem(sys.modules, name, None)
    monitor.refresh()
    status = monitor.get_status()
    assert status.score == 100.0
    assert status.label == "SECURE"


def test_start_is_idempotent(monkeypatch):
    """Calling start() while a thread is already alive must be a no-op."""
    monitor = sm.SecurityMonitor(poll_interval=3600)

    # Pre-seed the monitor with an alive thread we control, so start() takes
    # the early-return branch without spawning a real worker.
    holder: dict[str, threading.Event] = {"stop": threading.Event()}

    def _idle() -> None:
        holder["stop"].wait()

    fake_thread = threading.Thread(target=_idle, daemon=True, name="fake-monitor")
    fake_thread.start()
    monitor._thread = fake_thread  # type: ignore[attr-defined]
    try:
        monitor.start()  # must not raise, must not replace the thread
        assert monitor._thread is fake_thread  # type: ignore[attr-defined]
    finally:
        holder["stop"].set()
        fake_thread.join(timeout=2)


def test_get_security_monitor_singleton_returns_same_instance(monkeypatch):
    # Reset module-level singleton to keep this test independent of order.
    monkeypatch.setattr(sm, "_instance", None)
    a = sm.get_security_monitor()
    b = sm.get_security_monitor()
    assert a is b
    assert isinstance(a, sm.SecurityMonitor)
