#!/usr/bin/env python3
"""Sapphire Telegram Intel Reader plugin tool.

Actions:
  status       - report live gate, config posture, counters, and recent sink size
  pull-once    - run one gated pull; refuses by default unless live gate passes
  recent       - return recent provenance-stamped records from the local sink
  quality-test - evaluate one text blob with the pure quality heuristics
  models       - list the optional local classifier model and fallback
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.telegram_intel.classifier import available_models  # noqa: E402
from services.telegram_intel.quality_filter import quality_filter  # noqa: E402
from services.telegram_intel.run import pull_once, status  # noqa: E402
from services.telegram_intel.sink import TelegramIntelSink  # noqa: E402


def _path(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value)).expanduser()


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower()
    config_path = _path(payload.get("config_path") or payload.get("config"))
    data_dir = _path(payload.get("data_dir"))
    counter_path = _path(payload.get("counter_path"))

    if action == "status":
        kwargs: dict[str, Any] = {"config_path": config_path, "data_dir": data_dir}
        if counter_path:
            kwargs["counter_path"] = counter_path
        return status(**kwargs)

    if action == "models":
        return {"ok": True, "models": available_models()}

    if action == "quality-test":
        decision = quality_filter(
            str(payload.get("text") or ""),
            channel_id=str(payload.get("channel_id") or "manual-test"),
            min_score=float(payload.get("min_quality", 0.45)),
        )
        return {
            "ok": True,
            "quality": decision.to_dict(),
            "sanitized_text": decision.sanitized_text,
        }

    if action == "recent":
        limit = max(1, min(int(payload.get("limit", 20)), 200))
        return {"ok": True, "records": TelegramIntelSink(data_dir).recent(limit=limit)}

    if action == "pull-once":
        kwargs = {"config_path": config_path, "data_dir": data_dir}
        if counter_path:
            kwargs["counter_path"] = counter_path
        if payload.get("allow_dry_run_backend") is True:
            kwargs["require_live_gate"] = False
        return pull_once(**kwargs)

    return {
        "ok": False,
        "error": f"unknown action: {action}",
        "known_actions": ["status", "pull-once", "recent", "quality-test", "models"],
    }


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    raw = stdin.read().strip() or '{"action":"status"}'
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        stdout.write(json.dumps({"ok": False, "error": "invalid JSON input"}) + "\n")
        return 2
    if not isinstance(payload, dict):
        stdout.write(json.dumps({"ok": False, "error": "input must be a JSON object"}) + "\n")
        return 2
    result = handle(payload)
    stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0 if result.get("ok", False) else 2


if __name__ == "__main__":
    sys.exit(main())
