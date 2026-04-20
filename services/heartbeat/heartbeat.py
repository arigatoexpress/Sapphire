#!/usr/bin/env python3
"""Sapphire Heartbeat Daemon — KeepAlive service health monitor.

Runs continuously, pinging all Sapphire services every 5 minutes.
Publishes service.heartbeat events to the event bus and sends Telegram
alerts on state transitions (service goes down/comes back up).

Designed to run as a macOS LaunchAgent with KeepAlive=true.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NOTIFY_DIR = ROOT / "plugins" / "claw-sapphire" / "tools"
HEARTBEAT_LOG = ROOT / "data" / "health" / "heartbeat.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("heartbeat")

INTERVAL_SECONDS = 300  # 5 minutes
ENDPOINTS = [
    ("control-plane", "http://127.0.0.1:8082/health"),
    ("dashboard", "http://127.0.0.1:8080/"),
    ("signal-logger", "http://127.0.0.1:18081/health"),
    ("inference-proxy", "http://127.0.0.1:11435/health"),
    ("openbb", "http://127.0.0.1:6900/api/v1/"),
    ("redis", None),  # checked via subprocess
]

_prev_status: dict[str, str] = {}


def _check_http(url: str, timeout: int = 5) -> bool:
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        # 4xx means the service is up and responding — 401/403/404 etc.
        # are not outages, just auth/routing responses.
        return e.code < 500
    except Exception:
        return False


def _check_redis() -> bool:
    try:
        r = subprocess.run(
            ["redis-cli", "ping"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "PONG"
    except Exception:
        return False


def _notify(message: str, priority: str = "p2") -> None:
    """Send Telegram notification via notify tool."""
    try:
        r = subprocess.run(
            [sys.executable, str(NOTIFY_DIR / "notify.py")],
            input=json.dumps({"message": message, "priority": priority}),
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            log.warning("notify failed: %s", r.stderr[:100])
    except Exception as e:
        log.warning("notify error: %s", e)


def _publish_event(status: dict) -> None:
    """Publish heartbeat event to event bus."""
    try:
        from lib.core.event_bus import get_bus
        get_bus().publish("service.heartbeat", status, source="heartbeat")
    except Exception:
        pass


def check_all() -> dict:
    """Run all health checks and return status dict."""
    global _prev_status
    now = datetime.now(UTC)
    results = {}
    transitions = []

    for name, url in ENDPOINTS:
        if name == "redis":
            alive = _check_redis()
        else:
            alive = _check_http(url)

        status = "up" if alive else "down"
        results[name] = status

        # Detect state transitions
        prev = _prev_status.get(name)
        if prev and prev != status:
            emoji = "🟢" if status == "up" else "🔴"
            transitions.append(f"{emoji} {name}: {prev} → {status}")

    _prev_status = results

    record = {
        "timestamp": now.isoformat(),
        "services": results,
        "up": sum(1 for s in results.values() if s == "up"),
        "down": sum(1 for s in results.values() if s == "down"),
    }

    # Persist
    HEARTBEAT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with HEARTBEAT_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")

    # Publish to event bus
    _publish_event(record)

    # Alert on transitions
    if transitions:
        msg = "🫀 *Heartbeat Alert*\n" + "\n".join(transitions)
        priority = "p1" if any("down" in t for t in transitions) else "p2"
        _notify(msg, priority=priority)
        log.info("State transition: %s", "; ".join(transitions))

    log.info("Heartbeat: %d up / %d down", record["up"], record["down"])
    return record


def main() -> None:
    """Run heartbeat loop (KeepAlive daemon)."""
    log.info("Sapphire heartbeat daemon starting (interval=%ds)", INTERVAL_SECONDS)

    # One-shot mode when piped via stdin
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            params = json.loads(raw)
            if params.get("action") == "check" or params.get("profile") == "brief":
                result = check_all()
                print(json.dumps(result, indent=2))
                return

    while True:
        try:
            check_all()
        except Exception as e:
            log.error("heartbeat check failed: %s", e)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
