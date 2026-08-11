"""Periodic Telegram heartbeat sender.

Runs from a LaunchAgent every 4h by default. Reads the shared settings
file; a heartbeat toggle written via the pm-bot's ``⚙️ Settings`` menu
takes effect on the next tick without needing a service restart.

Off by default. Enabling the toggle sets the state to ON, but the
message still goes through ``plugins/claw-sapphire/tools/notify.py``,
which honors the global ``SAPPHIRE_NOTIFY_TELEGRAM_LIVE`` gate — so
until that gate is also flipped, the heartbeat lands in the draft queue
rather than in Telegram. This is the same "double-safety" posture the
rest of the outbound stack uses.

Usage::

    python3 -m lib.telegram.heartbeat            # runs one tick
    python3 -m lib.telegram.heartbeat --dry-run  # prints without sending
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from lib.telegram import formatters, settings_store, system_snapshot

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_TOOL = REPO_ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"

# Track the last successful tick so operators (or the LaunchAgent
# monitor) can see whether heartbeats are firing.
STATE_FILE = Path.home() / ".cache" / "sapphire" / "telegram" / "heartbeat_state.json"


def _write_state(payload: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json

    STATE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _due(now_hour: int, interval_hours: int) -> bool:
    """Return True if the current hour is aligned to the configured interval.

    LaunchAgent fires hourly; this helper is what turns hourly firings
    into a 4h / 12h / 24h cadence without needing multiple plists.
    """
    if interval_hours <= 0:
        return False
    return (now_hour % interval_hours) == 0


def _run_notify(text: str, *, priority: str, dry_run: bool) -> int:
    if dry_run:
        print(text)
        return 0
    if not NOTIFY_TOOL.exists():
        logger.error("notify tool not found at %s", NOTIFY_TOOL)
        return 1
    completed = subprocess.run(
        [sys.executable, str(NOTIFY_TOOL), "--priority", priority, text],
        check=False,
    )
    return completed.returncode


def build_message() -> str:
    """Assemble the one-line heartbeat text (MarkdownV2)."""
    snap = system_snapshot.build_snapshot()
    return formatters.fmt_heartbeat_line(
        agents_ok=snap.agents_ok,
        agents_total=snap.agents_total,
        regime=snap.regime,
        fear_greed=snap.fear_greed,
        portfolio_usd=snap.portfolio_usd,
        kill_switch_armed=snap.kill_switch_armed,
    )


def run_once(*, dry_run: bool = False, now: datetime | None = None) -> int:
    """Fire one heartbeat tick if scheduling + settings agree.

    Returns 0 on success (or intentional skip), non-zero on send failure.
    """
    settings = settings_store.load()
    ts = now or datetime.now(UTC)
    payload = {
        "checked_at": ts.isoformat(),
        "enabled": settings.heartbeat_enabled,
        "interval_hours": settings.heartbeat_hours,
        "sent": False,
        "skipped_reason": None,
    }

    if not settings.heartbeat_enabled:
        payload["skipped_reason"] = "disabled"
        _write_state(payload)
        logger.info("heartbeat disabled")
        return 0

    if not _due(ts.hour, settings.heartbeat_hours):
        payload["skipped_reason"] = "not_scheduled"
        _write_state(payload)
        logger.info("heartbeat not due (hour=%s interval=%s)", ts.hour, settings.heartbeat_hours)
        return 0

    message = build_message()
    exit_code = _run_notify(message, priority="p3", dry_run=dry_run)
    payload["sent"] = exit_code == 0
    payload["last_message"] = message
    _write_state(payload)
    return exit_code


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print message; don't send")
    parser.add_argument("--force", action="store_true", help="Ignore the schedule alignment")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.force:
        message = build_message()
        return _run_notify(message, priority="p3", dry_run=args.dry_run)
    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli())
