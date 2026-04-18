"""Emergency security kill switch — stops external connections on demand.

Intended for use during a suspected account compromise or SIM-swap attack.
Actions are non-destructive and reversible; nothing is permanently deleted.

Quick usage:
    python3 -m lib.core.security_kill_switch

    from lib.core.security_kill_switch import engage

    result = engage(reason="Suspected SIM-swap attack")
    print(result.summary())
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Paths
_SAPPHIRE = Path.home() / "Code" / "Sapphire"
_EVENTS_PATH = _SAPPHIRE / "data" / "system_events.jsonl"
_KILL_FLAG = _SAPPHIRE / "data" / ".security_kill_switch_active"


@dataclass
class KillSwitchResult:
    engaged_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""
    actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Security Kill Switch ENGAGED at {self.engaged_at.isoformat()}",
            f"Reason: {self.reason}",
            "",
            "Actions taken:",
        ]
        for a in self.actions:
            lines.append(f"  ✓ {a}")
        if self.errors:
            lines.append("")
            lines.append("Errors (non-fatal):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        return "\n".join(lines)


def _log_event(result: KillSwitchResult) -> None:
    event = {
        "timestamp": result.engaged_at.isoformat(),
        "type": "security.kill_switch.engaged",
        "message": f"Security kill switch engaged: {result.reason}",
        "tags": ["type:security", "priority:p0", "device:mac"],
        "data": {
            "reason": result.reason,
            "actions": result.actions,
            "errors": result.errors,
        },
    }
    try:
        _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_EVENTS_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as exc:
        log.error("Failed to write kill switch event: %s", exc)


def _stop_signal_logger(result: KillSwitchResult) -> None:
    """Kill the signal logger process (stops trading signal ingestion)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", "TCP:18081"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            for pid in out.splitlines():
                os.kill(int(pid), signal.SIGTERM)
            result.actions.append("Signal logger (:18081) stopped")
        else:
            result.actions.append("Signal logger not running (no PID on :18081)")
    except Exception as exc:
        result.errors.append(f"Stop signal logger: {exc}")


def _stop_inference_proxy(result: KillSwitchResult) -> None:
    """Kill the inference proxy (stops all LLM routing including Kimi Cloud)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", "TCP:11435"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            for pid in out.splitlines():
                os.kill(int(pid), signal.SIGTERM)
            result.actions.append("Inference proxy (:11435) stopped")
        else:
            result.actions.append("Inference proxy not running")
    except Exception as exc:
        result.errors.append(f"Stop inference proxy: {exc}")


def _block_cloud_routing(result: KillSwitchResult) -> None:
    """Write a kill flag file that inference proxy and agents check before cloud calls."""
    try:
        _KILL_FLAG.parent.mkdir(parents=True, exist_ok=True)
        _KILL_FLAG.write_text(
            json.dumps({"engaged_at": datetime.now(UTC).isoformat(), "reason": "security_kill_switch"})
            + "\n"
        )
        result.actions.append(f"Cloud routing kill flag written: {_KILL_FLAG}")
    except Exception as exc:
        result.errors.append(f"Write kill flag: {exc}")


def _disable_content_engine(result: KillSwitchResult) -> None:
    """Unload the content-engine LaunchAgent (stops autonomous outreach)."""
    plist = "com.sapphire.content-engine"
    try:
        subprocess.run(
            ["launchctl", "unload", f"{Path.home()}/Library/LaunchAgents/{plist}.plist"],
            check=False, capture_output=True, text=True,
        )
        result.actions.append(f"LaunchAgent {plist} unloaded")
    except Exception as exc:
        result.errors.append(f"Unload {plist}: {exc}")


def _send_telegram_alert(result: KillSwitchResult) -> None:
    """Send a P0 Telegram alert before revoking any tokens."""
    try:
        sys.path.insert(0, str(_SAPPHIRE / "plugins" / "claw-sapphire" / "tools"))
        from notify import send_telegram_message  # type: ignore[import]
        msg = (
            "🚨 *SECURITY KILL SWITCH ENGAGED* 🚨\n\n"
            f"Reason: {result.reason}\n"
            f"Time: {result.engaged_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            "Actions:\n" + "\n".join(f"• {a}" for a in result.actions)
            + "\n\n_All external connections stopped. Review accounts immediately._"
        )
        send_telegram_message(msg, priority="p0")
        result.actions.append("Telegram P0 alert sent")
    except Exception as exc:
        result.errors.append(f"Telegram alert: {exc}")


def engage(reason: str = "Manual security kill switch") -> KillSwitchResult:
    """Engage the security kill switch.

    Stops external connections in priority order:
    1. Signal logger (stops trading signal ingestion)
    2. Write cloud-routing kill flag (checked by inference proxy / agents)
    3. Disable content-engine LaunchAgent (stops autonomous outreach)
    4. Stop inference proxy (stops LLM routing to Kimi Cloud)
    5. Send Telegram P0 alert

    All steps are non-fatal — errors are collected but don't abort the sequence.
    """
    result = KillSwitchResult(reason=reason)
    log.critical("Security kill switch engaged: %s", reason)

    _stop_signal_logger(result)
    _block_cloud_routing(result)
    _disable_content_engine(result)
    _send_telegram_alert(result)
    _stop_inference_proxy(result)  # last — so Telegram alert can still go out
    _log_event(result)

    return result


def disengage(reason: str = "Manual security clearance") -> None:
    """Remove the kill flag to re-enable cloud routing."""
    if _KILL_FLAG.exists():
        _KILL_FLAG.unlink()
        log.info("Security kill flag removed: %s", reason)
    else:
        log.info("Security kill flag not present (already disengaged)")


def is_engaged() -> bool:
    """Return True if the kill flag is active."""
    return _KILL_FLAG.exists()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    reason = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Manual CLI invocation"
    result = engage(reason=reason)
    print(result.summary())
    sys.exit(1 if result.errors else 0)
