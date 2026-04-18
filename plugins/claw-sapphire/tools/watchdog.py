#!/usr/bin/env python3
"""Sapphire Watchdog — monitors services and sends Telegram alerts on failures.

Runs the health check and sends alerts when services go red.
Tracks previous state to avoid duplicate alerts (only alerts on NEW failures).

Usage:
    python3 watchdog.py                    # Check all, alert on new failures
    python3 watchdog.py --force            # Alert even if already alerted
    echo '{"check":"services"}' | python3 watchdog.py  # Check specific section
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
STATE_FILE = SAPPHIRE_DIR / "data" / ".watchdog_state.json"
NOTIFY_TOOL = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools" / "notify.py"
HEALTH_TOOL = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools" / "health_check.py"


def _run_health_check() -> dict:
    """Run the ecosystem health check."""
    try:
        r = subprocess.run(
            ["python3", str(HEALTH_TOOL)],
            input="{}", capture_output=True, text=True, timeout=45,
        )
        return json.loads(r.stdout) if r.stdout else {}
    except Exception as e:
        return {"error": str(e)}


def _send_alert(message: str, priority: str = "p0"):
    """Send a Telegram alert."""
    with contextlib.suppress(Exception):
        subprocess.run(
            ["python3", str(NOTIFY_TOOL), message, "--priority", priority],
            capture_output=True, timeout=15,
        )


def _load_previous_state() -> dict:
    """Load previous watchdog state to avoid duplicate alerts."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    """Save current state for next run."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def check_and_alert(force: bool = False) -> dict:
    """Run health check, compare to previous state, alert on new failures."""
    health = _run_health_check()
    if "error" in health:
        _send_alert(f"🔴 Watchdog failed to run health check: {health['error']}")
        return health

    prev = _load_previous_state()
    prev_reds = set(prev.get("red_items", []))

    # Collect current reds
    current_reds = []
    alerts = []

    for section in ["services", "repos", "data_freshness", "inference"]:
        for name, info in health.get(section, {}).items():
            if info.get("status") == "red":
                item_key = f"{section}/{name}"
                current_reds.append(item_key)

                if force or item_key not in prev_reds:
                    alerts.append(f"🔴 {name}: {info.get('detail', 'unknown')[:80]}")

    # Also alert on recovery (red → green)
    recovered = prev_reds - set(current_reds)
    for item in recovered:
        alerts.append(f"✅ RECOVERED: {item.split('/')[-1]}")

    # Send consolidated alert if there are new issues
    if alerts:
        header = f"*Watchdog — {health.get('overall', '?')}*\n{health.get('summary', '')}\n"
        body = "\n".join(alerts)
        _send_alert(f"{header}\n{body}", priority="p0" if current_reds else "p1")

    # Save state
    _save_state({
        "timestamp": datetime.now().isoformat(),
        "overall": health.get("overall"),
        "red_items": current_reds,
        "summary": health.get("summary"),
    })

    return {
        "overall": health.get("overall"),
        "summary": health.get("summary"),
        "new_alerts": len(alerts),
        "current_reds": current_reds,
        "recovered": list(recovered),
    }


def main():
    force = "--force" in sys.argv
    result = check_and_alert(force=force)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
