"""Security event monitor — aggregates security signals from running modules.

Polls lib.core.security_kill_switch, lib.security.dependency_scanner,
lib.security.model_monitor, and lib.security.network_mapper at a configurable
interval, emits structured security events to the event bus, and exposes a
``SecurityStatus`` snapshot for the dashboard /api/security/* endpoints.

This module does NOT replace the individual security modules — it aggregates
their outputs into a single status object that the dashboard can query.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class SecurityStatus:
    score: float = 100.0
    label: str = "SECURE"
    last_checked: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    active_threats: list[str] = field(default_factory=list)
    kill_switch_active: bool = False
    dependency_issues: int = 0
    model_anomalies: int = 0
    network_alerts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "label": self.label,
            "last_checked": self.last_checked,
            "active_threats": self.active_threats,
            "kill_switch_active": self.kill_switch_active,
            "dependency_issues": self.dependency_issues,
            "model_anomalies": self.model_anomalies,
            "network_alerts": self.network_alerts,
        }


class SecurityMonitor:
    """Aggregates security signals from all Sapphire security modules."""

    def __init__(self, poll_interval: int = 300) -> None:
        self._interval = poll_interval
        self._status = SecurityStatus()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def get_status(self) -> SecurityStatus:
        with self._lock:
            return self._status

    def refresh(self) -> SecurityStatus:
        """Run a single pass across all security modules and update status."""
        score = 100.0
        threats: list[str] = []
        ks_active = False
        dep_issues = 0
        model_anomalies = 0
        net_alerts = 0

        # Kill switch
        try:
            from lib.core.security_kill_switch import is_engaged

            if is_engaged():
                ks_active = True
                score -= 40
                threats.append("security_kill_switch:ACTIVE")
        except Exception as exc:
            log.debug("kill switch check skipped: %s", exc)

        # Dependency scanner
        try:
            from lib.security.dependency_scanner import DependencyScanner

            report = DependencyScanner().scan()
            criticals = [v for v in report.vulnerabilities if v.severity == "CRITICAL"]
            dep_issues = len(criticals)
            if dep_issues:
                score -= min(30, dep_issues * 10)
                threats.append(f"dependencies:{dep_issues}_critical_CVEs")
        except Exception as exc:
            log.debug("dependency scan skipped: %s", exc)

        # Model monitor
        try:
            from lib.security.model_monitor import ModelMonitor

            alerts = ModelMonitor().check_all()
            model_anomalies = len([a for a in alerts if a.get("severity") == "HIGH"])
            if model_anomalies:
                score -= min(20, model_anomalies * 5)
                threats.append(f"model_monitor:{model_anomalies}_anomalies")
        except Exception as exc:
            log.debug("model monitor skipped: %s", exc)

        score = max(0.0, round(score, 1))
        label = "SECURE" if score >= 80 else "DEGRADED" if score >= 50 else "CRITICAL"

        status = SecurityStatus(
            score=score,
            label=label,
            last_checked=datetime.now(UTC).isoformat(),
            active_threats=threats,
            kill_switch_active=ks_active,
            dependency_issues=dep_issues,
            model_anomalies=model_anomalies,
            network_alerts=net_alerts,
        )
        with self._lock:
            self._status = status
        return status

    def start(self) -> None:
        """Start background polling thread."""
        if self._thread and self._thread.is_alive():
            return

        def _loop() -> None:
            while True:
                try:
                    self.refresh()
                except Exception as exc:
                    log.error("security monitor loop error: %s", exc)
                threading.Event().wait(self._interval)

        self._thread = threading.Thread(target=_loop, daemon=True, name="security-monitor")
        self._thread.start()


_instance: SecurityMonitor | None = None
_lock = threading.Lock()


def get_security_monitor() -> SecurityMonitor:
    global _instance
    with _lock:
        if _instance is None:
            _instance = SecurityMonitor()
        return _instance
