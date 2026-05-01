"""Fire-and-forget hooks that wire 0G publishing into the trading critical path.

Design constraints:
- MUST NOT raise into the caller. The trading path is real money; a 0G
  outage cannot delay or block trade logging.
- MUST NOT block the caller. We spawn a detached subprocess and return.
- MUST be silent when SAPPHIRE_OG_ENABLED is unset. Zero side effects.

The subprocess writes its own log line to data/system_events.jsonl on completion
(success or failure), so the operator can audit 0G publish coverage without
plumbing return values up through the webhook.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from lib.og.config import ENV_FLAG, ENV_NETWORK, ENV_PRIVATE_KEY, is_enabled

ROOT = Path(__file__).resolve().parents[2]
PUBLISH_TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "og_publish.py"
EVENTS_PATH = ROOT / "data" / "system_events.jsonl"
LOG = logging.getLogger("lib.og.hooks")


def publish_signal_async(
    signal: dict,
    *,
    strategy: str | None = None,
    symbol: str | None = None,
    network: str | None = None,
) -> None:
    """Fire-and-forget: spawn `og_publish.py` with the signal as stdin JSON.

    Returns immediately. Never raises. If `SAPPHIRE_OG_ENABLED` is unset,
    this is a no-op.
    """
    if not is_enabled():
        return

    if not PUBLISH_TOOL.exists():
        LOG.warning("og_publish tool missing at %s", PUBLISH_TOOL)
        _record_event(
            "og.publish.skipped", {"reason": "tool_missing", "path": str(PUBLISH_TOOL)}
        )
        return

    if ENV_PRIVATE_KEY not in os.environ:
        _record_event("og.publish.skipped", {"reason": "no_private_key"})
        return

    payload = {
        "strategy": strategy or signal.get("strategy") or "unknown",
        "symbol": symbol or signal.get("symbol") or "UNKNOWN",
        "action": signal.get("action") or signal.get("direction"),
        "score": signal.get("score") or signal.get("confidence"),
        "signal": signal,
        "network": network or os.environ.get(ENV_NETWORK),
    }

    env = os.environ.copy()
    env[ENV_FLAG] = "1"

    try:
        subprocess.Popen(  # noqa: S603 — controlled args, not user input
            [sys.executable, str(PUBLISH_TOOL)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(ROOT),
            start_new_session=True,
            text=True,
        ).stdin.write(json.dumps(payload))  # type: ignore[union-attr]
    except Exception as exc:
        LOG.warning("og publish spawn failed: %s", exc)
        _record_event("og.publish.spawn_error", {"error": str(exc)})


def _record_event(event_type: str, data: dict) -> None:
    try:
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(EVENTS_PATH, "a") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "type": event_type,
                        "tags": ["service:og", "priority:p3"],
                        "data": data,
                    }
                )
                + "\n"
            )
    except Exception:
        pass
