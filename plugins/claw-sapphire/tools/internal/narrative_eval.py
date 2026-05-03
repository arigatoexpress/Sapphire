#!/usr/bin/env python3
"""Sapphire Narrative Evaluation plugin tool.

Stdin JSON actions:
- ``score-thesis`` — pure score of one thesis against one actual outcome.
- ``aggregates`` — rolling aggregate stats by symbol/timeframe/edge/source/regime.
- ``diagnostics`` — false-positive and calibration-miss diagnostics.
- ``calibration`` — confidence bucket calibration.
- ``status`` — read-only service status.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_module(name: str, relpath: str) -> Any:
    import types as _types

    if name in sys.modules:
        existing = sys.modules[name]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing

    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {target}")

    parts = name.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        parent_path = REPO_ROOT / Path(*parts[:i])
        if parent not in sys.modules or not hasattr(sys.modules[parent], "__path__"):
            module = _types.ModuleType(parent)
            module.__path__ = [str(parent_path)]  # type: ignore[attr-defined]
            sys.modules[parent] = module

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


_load_repo_module("lib.core.provenance", "lib/core/provenance.py")
_scoring = _load_repo_module(
    "lib.narrative_evaluation.scoring", "lib/narrative_evaluation/scoring.py"
)
_aggregates = _load_repo_module(
    "lib.narrative_evaluation.aggregates", "lib/narrative_evaluation/aggregates.py"
)
_load_repo_module("lib.narrative_evaluation", "lib/narrative_evaluation/__init__.py")
_service = _load_repo_module(
    "services.narrative_evaluation.run", "services/narrative_evaluation/run.py"
)

GENERATOR = "plugins.claw_sapphire.narrative_eval"
VERSION = "0.1.0"
VALID_ACTIONS = ["score-thesis", "aggregates", "diagnostics", "calibration", "status"]


def score_thesis_action(payload: dict[str, Any]) -> dict[str, Any]:
    thesis = payload.get("thesis")
    if not isinstance(thesis, dict):
        return {"ok": False, "error": "`thesis` object is required"}
    horizon = int(payload.get("horizon_hours") or 24)
    outcome = payload.get("outcome") if isinstance(payload.get("outcome"), dict) else None
    score = _scoring.score_thesis(thesis, outcome, horizon_hours=horizon)
    return {"ok": True, "score": score.to_dict()}


def _scores_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    inline = payload.get("scores")
    if isinstance(inline, list):
        return [row for row in inline if isinstance(row, dict)]
    date = payload.get("date")
    limit = int(payload.get("limit") or 1000)
    return _service.load_scores(date=date, limit=limit)


def aggregates_action(payload: dict[str, Any]) -> dict[str, Any]:
    group_by = str(payload.get("group_by") or "symbol")
    return {
        "ok": True,
        **_aggregates.aggregate_scores(_scores_from_payload(payload), group_by=group_by),
    }


def diagnostics_action(payload: dict[str, Any]) -> dict[str, Any]:
    return _aggregates.diagnostics_report(
        _scores_from_payload(payload), limit=int(payload.get("limit") or 20)
    )


def calibration_action(payload: dict[str, Any]) -> dict[str, Any]:
    return _aggregates.calibration_report(_scores_from_payload(payload))


def status_action() -> dict[str, Any]:
    return {
        "ok": True,
        "generator": GENERATOR,
        "version": VERSION,
        "service": _service.status(),
        "actions": VALID_ACTIONS,
        "dry_run": True,
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower()
    if action == "score-thesis":
        return score_thesis_action(payload)
    if action == "aggregates":
        return aggregates_action(payload)
    if action == "diagnostics":
        return diagnostics_action(payload)
    if action == "calibration":
        return calibration_action(payload)
    if action == "status":
        return status_action()
    return {"error": f"unknown action '{action}'", "valid_actions": VALID_ACTIONS}


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
