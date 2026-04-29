#!/usr/bin/env python3
"""Stdin-JSON tool for Sapphire source-quality measurement 0.1.0.

Read-only consumer of the daily report produced by
``services/source_quality/run.py``. The tool exposes four actions:

- ``status``         — daemon-version + report-on-disk metadata
- ``latest-report``  — full snapshot from the newest dated report
- ``snr``            — just the per-source SNR table
- ``near-duplicates`` — just the near-duplicate pairs at threshold
- ``decay``          — just the decay alerts
- ``recompute``      — run :func:`services.source_quality.run.run`
                       in-process with ``write=False`` (memory-only)

Live disk writes (``recompute`` with ``write=true``) are gated behind
``SAPPHIRE_SOURCE_QUALITY_LIVE=1`` to keep the plugin tool side-effect
free unless the operator opts in.
"""

# ruff: noqa: E402,I001

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = ROOT / "plugins" / "claw-sapphire"
_removed_plugin_paths: list[str] = []
for entry in list(sys.path):
    try:
        if Path(entry).resolve() == PLUGIN_ROOT:
            sys.path.remove(entry)
            _removed_plugin_paths.append(entry)
    except OSError:
        continue
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
for _name in list(sys.modules):
    if _name == "lib" or _name.startswith("lib."):
        del sys.modules[_name]

from services.source_quality.run import (  # noqa: E402
    DAEMON_VERSION,
    DEFAULT_REPORT_ROOT,
    build_report,
    gather_outcomes,
    gather_signals,
)


VALID_ACTIONS = (
    "status",
    "latest-report",
    "snr",
    "near-duplicates",
    "decay",
    "recompute",
)

# Cap the response payload so we never blow up an agent's context.
MAX_RESPONSE_BYTES = 256 * 1024


def _normalize_action(value: Any) -> str:
    if value is None:
        return "status"
    return str(value).strip().lower().replace("_", "-")


def _newest_report_path(root: Path | None = None) -> Path | None:
    base = Path(root) if root else DEFAULT_REPORT_ROOT
    if not base.exists() or not base.is_dir():
        return None
    candidates: list[Path] = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        report = child / "report.json"
        if report.is_file():
            candidates.append(report)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    return candidates[0]


def _read_report(root: Path | None = None) -> dict[str, Any] | None:
    path = _newest_report_path(root)
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _truncate(payload: dict[str, Any]) -> dict[str, Any]:
    serialised = json.dumps(payload, sort_keys=True, default=str)
    if len(serialised) <= MAX_RESPONSE_BYTES:
        return payload
    return {
        "truncated": True,
        "summary": payload.get("summary", {}),
        "size_limit_bytes": MAX_RESPONSE_BYTES,
        "actual_size_bytes": len(serialised),
    }


def _live_gate() -> bool:
    return str(os.environ.get("SAPPHIRE_SOURCE_QUALITY_LIVE", "")).strip() in {"1", "true", "yes"}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = _normalize_action(payload.get("action"))
    report_root = payload.get("report_root")
    root = Path(report_root) if report_root else None

    if action == "status":
        path = _newest_report_path(root)
        return {
            "daemon_version": DAEMON_VERSION,
            "report_root": str(root or DEFAULT_REPORT_ROOT),
            "latest_report": str(path) if path else None,
            "has_report": path is not None,
            "read_only": True,
            "live_writes_enabled": _live_gate(),
        }
    if action == "latest-report":
        report = _read_report(root)
        if report is None:
            return {"status": "no_data", "reason": "no report on disk", "report_root": str(root or DEFAULT_REPORT_ROOT)}
        return _truncate({"status": "ok", **report})
    if action == "snr":
        report = _read_report(root)
        if report is None:
            return {"status": "no_data", "snr": {}}
        return {
            "status": "ok",
            "report_date": report.get("report_date"),
            "snr": report.get("snr", {}),
        }
    if action == "near-duplicates":
        report = _read_report(root)
        if report is None:
            return {"status": "no_data", "near_duplicates": []}
        return {
            "status": "ok",
            "report_date": report.get("report_date"),
            "near_duplicates": report.get("near_duplicates", []),
        }
    if action == "decay":
        report = _read_report(root)
        if report is None:
            return {"status": "no_data", "decay": {"alerts": [], "decayed_sources": []}}
        return {
            "status": "ok",
            "report_date": report.get("report_date"),
            "decay": report.get("decay", {"alerts": []}),
        }
    if action == "recompute":
        # Always memory-only when invoked from the plugin tool. The
        # daemon does live writes; keep the tool side-effect free.
        write = bool(payload.get("write", False)) and _live_gate()
        if write:
            return {
                "error": "live writes from the plugin tool are intentionally disabled; use the daemon",
                "valid_actions": list(VALID_ACTIONS),
            }
        signals = gather_signals()
        outcomes = gather_outcomes()
        report = build_report(signals, outcomes)
        return _truncate({"status": "ok", "memory_only": True, **report})
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def run(action: str = "status", **kwargs: Any) -> str:
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True, default=str)


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
