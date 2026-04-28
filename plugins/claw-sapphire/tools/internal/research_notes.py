#!/usr/bin/env python3
"""stdin JSON tool for Sapphire research notes."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
repo_lib = REPO_ROOT / "lib"
plugin_lib = REPO_ROOT / "plugins" / "claw-sapphire" / "lib"
loaded_lib = sys.modules.get("lib")
loaded_paths = list(getattr(loaded_lib, "__path__", [])) if loaded_lib is not None else []
if str(repo_lib) not in loaded_paths:
    pkg = types.ModuleType("lib")
    pkg.__path__ = [str(repo_lib), *(p for p in loaded_paths if p != str(repo_lib)), str(plugin_lib)]
    sys.modules["lib"] = pkg

from lib.research_notes.pipeline import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    aggregate_summary,
    build_note,
    compose_note,
    latest_note,
    render_note,
)


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "latest")
    output_root = Path(payload.get("output_root") or DEFAULT_OUTPUT_ROOT)
    if action == "compose":
        note = compose_note(
            backtest_summary_data=payload.get("backtest_summary"),
            leaderboard_data=payload.get("leaderboard"),
            performance_data=payload.get("performance"),
            timeseries_data=payload.get("timeseries"),
            context=payload.get("context"),
            strategy_slug=payload.get("strategy_slug"),
            as_of_date=payload.get("as_of_date"),
            generated_at=payload.get("generated_at"),
        )
        return {"ok": True, "note": note.to_dict()}
    if action == "render":
        note = compose_note(
            backtest_summary_data=payload.get("backtest_summary"),
            leaderboard_data=payload.get("leaderboard"),
            performance_data=payload.get("performance"),
            timeseries_data=payload.get("timeseries"),
            context=payload.get("context"),
            strategy_slug=payload.get("strategy_slug"),
            as_of_date=payload.get("as_of_date"),
            generated_at=payload.get("generated_at"),
        )
        pdf = render_note(note, timeseries_data=payload.get("timeseries"), output_root=output_root)
        return {"ok": True, "note": note.to_dict(), "pdf_path": str(pdf)}
    if action == "build":
        return build_note(
            context=payload.get("context"),
            output_root=output_root,
            as_of_date=payload.get("as_of_date"),
            strategy_slug=payload.get("strategy_slug"),
            generated_at=payload.get("generated_at"),
        )
    if action == "latest":
        return latest_note(output_root=output_root)
    if action == "aggregate-summary":
        return aggregate_summary(output_root=output_root)
    return {
        "ok": False,
        "error": (
            "unknown action; use compose, render, build, latest, or aggregate-summary"
        ),
    }


def main() -> int:
    try:
        result = handle(_read_payload())
    except Exception as exc:  # noqa: BLE001 - tool boundary returns JSON errors.
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
