"""Heartbeat daemon — monitors all Sapphire components every 60s.

State machine per component:
  HEALTHY → DEGRADED → FAILED → RECOVERING → HEALTHY

Escalation:
  Level 1 (DEGRADED): log warning + event bus publish
  Level 2 (FAILED):   log error + Telegram alert + self-heal attempt
  Level 3 (FAILED, heal failed): Telegram escalation every 10min

Self-healing via launchctl kickstart for registered LaunchAgents.

Run standalone:
    python3 -m lib.core.heartbeat [--interval 60] [--dry-run]
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # seconds between full sweeps
FAIL_THRESHOLD = 3  # consecutive failures → FAILED
DEGRADE_THRESHOLD = 1  # consecutive failures → DEGRADED
ESCALATE_INTERVAL = 600  # re-alert for sustained FAILED every 10min
RECOVER_CYCLES = 2  # healthy cycles needed to leave RECOVERING


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class ComponentState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class ComponentStatus:
    name: str
    state: ComponentState = ComponentState.HEALTHY
    consecutive_failures: int = 0
    consecutive_healthy: int = 0
    last_error: str = ""
    last_checked: float = 0.0
    last_alerted: float = 0.0
    restart_attempts: int = 0
    launchctl_label: str = ""  # non-empty → self-healable via launchctl


# ---------------------------------------------------------------------------
# Check primitives
# ---------------------------------------------------------------------------


def _tcp_ok(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except (OSError, TimeoutError) as exc:
        return False, str(exc)


def _http_ok(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-heartbeat/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _ = r.read(512)
        return True, ""
    except urllib.error.HTTPError as exc:
        # 401/403 still means service is up
        if exc.code in {401, 403, 405}:
            return True, ""
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def _launchctl_status(label: str) -> tuple[bool, str]:
    """True if the service is listed and has a non-negative PID."""
    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, f"not listed ({result.stderr.strip()[:80]})"
        # Output: PID  Status  Label — PID "-" means not running
        first_field = result.stdout.split()[0] if result.stdout.split() else "-"
        running = first_field not in {"-", ""}
        return running, "" if running else "not running"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Component definitions
# ---------------------------------------------------------------------------


def _build_components() -> list[ComponentStatus]:
    comps: list[ComponentStatus] = []

    # HTTP services
    http_checks = [
        ("control-plane", "http://127.0.0.1:8082/health"),
        ("dashboard", "http://127.0.0.1:8080/health"),
        ("inference-proxy", "http://127.0.0.1:11435/health"),
        ("signal-logger", "http://127.0.0.1:18081/health"),
        ("openbb", "http://127.0.0.1:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance"),
        ("ollama-mac", "http://127.0.0.1:11434/api/version"),
    ]
    for name, _url in http_checks:
        comps.append(ComponentStatus(name=name))

    # TCP-only
    tcp_checks = [
        ("redis", "127.0.0.1", 6379),
    ]
    for name, _host, _port in tcp_checks:
        comps.append(ComponentStatus(name=name))

    # LaunchAgent-backed (self-healable)
    la_checks = [
        ("hermes-gateway", "ai.hermes.gateway"),
        ("content-engine", "com.sapphire.content-engine"),
    ]
    for name, label in la_checks:
        comps.append(ComponentStatus(name=name, launchctl_label=label))

    return comps


# Mapping component name → check function
def _check_fn(comp: ComponentStatus) -> tuple[bool, str]:
    name = comp.name
    if name == "control-plane":
        return _http_ok("http://127.0.0.1:8082/health")
    if name == "dashboard":
        return _http_ok("http://127.0.0.1:8080/health")
    if name == "inference-proxy":
        return _http_ok("http://127.0.0.1:11435/health")
    if name == "signal-logger":
        return _http_ok("http://127.0.0.1:18081/health")
    if name == "openbb":
        ok, err = _http_ok(
            "http://127.0.0.1:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance",
            timeout=8.0,
        )
        return ok, err
    if name == "ollama-mac":
        return _http_ok("http://127.0.0.1:11434/api/version")
    if name == "redis":
        return _tcp_ok("127.0.0.1", 6379)
    if comp.launchctl_label:
        return _launchctl_status(comp.launchctl_label)
    return False, f"no check defined for {name}"


# ---------------------------------------------------------------------------
# Self-heal
# ---------------------------------------------------------------------------


def _attempt_heal(comp: ComponentStatus) -> bool:
    """Attempt to restart a LaunchAgent. Returns True if kickstart succeeded."""
    if not comp.launchctl_label:
        return False
    label = comp.launchctl_label
    try:
        uid = os.getuid()
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        success = result.returncode == 0
        if success:
            log.info("heartbeat: self-heal kickstart %s succeeded", label)
        else:
            log.warning(
                "heartbeat: self-heal kickstart %s failed: %s", label, result.stderr.strip()[:120]
            )
        comp.restart_attempts += 1
        return success
    except Exception as exc:
        log.warning("heartbeat: self-heal %s error: %s", label, exc)
        comp.restart_attempts += 1
        return False


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------


def _send_telegram(msg: str) -> None:
    notify_tool = ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"
    if not notify_tool.exists():
        log.debug("heartbeat: notify tool not found, skipping telegram")
        return
    try:
        subprocess.run(
            [sys.executable, str(notify_tool), msg, "--priority", "p1"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:
        log.debug("heartbeat: telegram notify failed: %s", exc)


def _publish_event(payload: dict) -> None:
    try:
        from lib.core.event_bus import get_bus

        get_bus().publish("service.health", payload, source="heartbeat")
    except Exception as exc:
        log.debug("heartbeat: event bus publish failed: %s", exc)


# ---------------------------------------------------------------------------
# Monitor core
# ---------------------------------------------------------------------------


class HeartbeatMonitor:
    """60-second sweep monitor with state machine, self-heal, and escalation."""

    def __init__(self, interval: int = CHECK_INTERVAL, dry_run: bool = False):
        self.interval = interval
        self.dry_run = dry_run
        self._components = _build_components()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background monitor thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sapphire-heartbeat", daemon=True)
        self._thread.start()
        log.info(
            "heartbeat: monitor started (interval=%ds, %d components)",
            self.interval,
            len(self._components),
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run_once(self) -> dict[str, Any]:
        """Run a single sweep and return a status report."""
        results: dict[str, Any] = {}
        for comp in self._components:
            self._check(comp)
            results[comp.name] = {
                "state": comp.state.value,
                "consecutive_failures": comp.consecutive_failures,
                "last_error": comp.last_error,
            }
        self._publish_summary()
        return results

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                log.error("heartbeat: sweep error: %s", exc)
            self._stop.wait(self.interval)

    def _check(self, comp: ComponentStatus) -> None:
        ok, err = _check_fn(comp)
        comp.last_checked = time.time()
        prev_state = comp.state

        if ok:
            comp.consecutive_failures = 0
            comp.last_error = ""
            if comp.state == ComponentState.RECOVERING:
                comp.consecutive_healthy += 1
                if comp.consecutive_healthy >= RECOVER_CYCLES:
                    comp.state = ComponentState.HEALTHY
                    comp.consecutive_healthy = 0
                    log.info("heartbeat: %s recovered ✓", comp.name)
            else:
                comp.state = ComponentState.HEALTHY
                comp.consecutive_healthy += 1
        else:
            comp.consecutive_failures += 1
            comp.consecutive_healthy = 0
            comp.last_error = err

            if comp.consecutive_failures >= FAIL_THRESHOLD:
                comp.state = ComponentState.FAILED
            elif comp.consecutive_failures >= DEGRADE_THRESHOLD:
                comp.state = ComponentState.DEGRADED

        # Transitions & actions
        if comp.state == ComponentState.DEGRADED and prev_state == ComponentState.HEALTHY:
            log.warning("heartbeat: %s → DEGRADED: %s", comp.name, err)
            _publish_event({"component": comp.name, "state": "degraded", "error": err})

        if comp.state == ComponentState.FAILED:
            now = time.time()
            if (
                prev_state != ComponentState.FAILED
                or (now - comp.last_alerted) >= ESCALATE_INTERVAL
            ):
                comp.last_alerted = now
                self._handle_failure(comp)

        if comp.state == ComponentState.HEALTHY and prev_state in {
            ComponentState.DEGRADED,
            ComponentState.FAILED,
            ComponentState.RECOVERING,
        }:
            log.info("heartbeat: %s → HEALTHY", comp.name)
            _publish_event({"component": comp.name, "state": "healthy"})

    def _handle_failure(self, comp: ComponentStatus) -> None:
        log.error(
            "heartbeat: %s FAILED (%d× consecutive): %s",
            comp.name,
            comp.consecutive_failures,
            comp.last_error,
        )

        heal_note = ""
        if comp.launchctl_label and not self.dry_run:
            healed = _attempt_heal(comp)
            if healed:
                comp.state = ComponentState.RECOVERING
                comp.consecutive_healthy = 0
                heal_note = " — restart issued, watching"
            else:
                heal_note = " — self-heal failed"

        _publish_event(
            {
                "component": comp.name,
                "state": "failed",
                "error": comp.last_error,
                "consecutive_failures": comp.consecutive_failures,
                "restart_attempts": comp.restart_attempts,
            }
        )

        if not self.dry_run:
            msg = (
                f"🔴 *Heartbeat FAILED*: `{comp.name}`\n"
                f"Error: {comp.last_error[:120]}\n"
                f"Failures: {comp.consecutive_failures}{heal_note}"
            )
            _send_telegram(msg)

    def _publish_summary(self) -> None:
        counts = {s.value: 0 for s in ComponentState}
        failing = []
        for comp in self._components:
            counts[comp.state.value] += 1
            if comp.state in {ComponentState.FAILED, ComponentState.DEGRADED}:
                failing.append(comp.name)

        overall = "nominal"
        if counts["failed"]:
            overall = "critical"
        elif counts["degraded"] or counts["recovering"]:
            overall = "degraded"

        _publish_event(
            {
                "summary": True,
                "overall": overall,
                "counts": counts,
                "failing": failing,
            }
        )

        if counts["failed"] or counts["degraded"]:
            log.warning(
                "heartbeat: sweep done — %d healthy, %d degraded, %d failed, %d recovering",
                counts["healthy"],
                counts["degraded"],
                counts["failed"],
                counts["recovering"],
            )
        else:
            log.info(
                "heartbeat: all %d components healthy",
                counts["healthy"] + counts["recovering"],
            )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sapphire heartbeat monitor")
    parser.add_argument(
        "--interval", type=int, default=CHECK_INTERVAL, help="Sweep interval in seconds"
    )
    parser.add_argument("--once", action="store_true", help="Run one sweep and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="Check only — no Telegram, no restarts"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    monitor = HeartbeatMonitor(interval=args.interval, dry_run=args.dry_run)

    if args.once:
        results = monitor.run_once()
        print(json.dumps(results, indent=2))
        failing = [
            name for name, r in results.items() if r["state"] not in {"healthy", "recovering"}
        ]
        return 1 if failing else 0

    monitor.start()
    log.info("heartbeat: running (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
