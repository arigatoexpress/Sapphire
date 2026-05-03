#!/usr/bin/env python3
"""Stdin-JSON tool for Sapphire's multi-agent audit panel."""
# ruff: noqa: E402,I001

from __future__ import annotations

import json
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

from lib.audit_panel.heuristics import MergedPR, run_heuristics  # noqa: E402
from lib.audit_panel.scorer import score_pr  # noqa: E402
from services.audit_panel.run import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_REPO,
    MAX_LIVE_GH_API_CALLS_PER_HOUR,
    MAX_PRS_PER_RUN,
    MAX_REPORT_BYTES,
    histogram_from_payload,
    latest_report,
    run_panel,
)

for _entry in reversed(_removed_plugin_paths):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
for _name in list(sys.modules):
    if _name == "lib" or _name.startswith("lib."):
        del sys.modules[_name]
del _removed_plugin_paths

VALID_ACTIONS = ("run-once", "latest-report", "pr-score", "histogram")


def _normalize_action(value: Any) -> str:
    return str(value or "latest-report").strip().lower().replace("_", "-")


def _pr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("pr")
    if isinstance(candidate, dict):
        return candidate
    return payload


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle one stdin JSON payload. Defaults remain read-only."""
    action = _normalize_action(payload.get("action"))
    cache_dir = Path(str(payload.get("cache_dir") or DEFAULT_CACHE_DIR))
    if action == "run-once":
        result = run_panel(
            repo=str(payload.get("repo") or DEFAULT_REPO),
            since=payload.get("since"),
            limit=min(int(payload.get("limit") or MAX_PRS_PER_RUN), MAX_PRS_PER_RUN),
            cache_dir=cache_dir,
            open_issue=bool(payload.get("open_issue", False)),
        )
        return {
            **result.to_dict(),
            "read_only": True,
            "issue_publishing_default": "disabled_for_plugin",
            "caps": _caps(),
        }
    if action == "latest-report":
        return {**latest_report(cache_dir), "caps": _caps()}
    if action == "pr-score":
        pr = MergedPR.from_dict(_pr_payload(payload))
        findings = run_heuristics(pr)
        return {
            "score": score_pr(pr).to_dict(),
            "findings": [finding.to_dict() for finding in findings],
            "paste_safe": True,
        }
    if action == "histogram":
        prs = payload.get("prs", [])
        if not isinstance(prs, list):
            return {"error": "histogram requires prs: list[object]"}
        return {"histogram": histogram_from_payload(prs), "paste_safe": True}
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def _caps() -> dict[str, int]:
    return {
        "MAX_PRS_PER_RUN": MAX_PRS_PER_RUN,
        "MAX_REPORT_BYTES": MAX_REPORT_BYTES,
        "MAX_LIVE_GH_API_CALLS_PER_HOUR": MAX_LIVE_GH_API_CALLS_PER_HOUR,
    }


def run(action: str = "latest-report", **kwargs: Any) -> str:
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True)


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
    json.dump(response, stream_out, indent=2, sort_keys=True)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
