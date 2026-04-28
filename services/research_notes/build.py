#!/usr/bin/env python3
"""Build Sapphire research notes from completed local sweep artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.research_notes.pipeline import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    build_note,
    completed_sweeps,
)


def run_build(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of_date: str | None = None,
    strategy_slug: str | None = None,
    generated_at: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sweeps = completed_sweeps()
    result = build_note(
        context=context,
        output_root=output_root,
        as_of_date=as_of_date,
        strategy_slug=strategy_slug,
        generated_at=generated_at,
    )
    result["completed_sweeps"] = sweeps
    result["completed_sweep_count"] = len(sweeps)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of-date")
    parser.add_argument("--strategy-slug")
    parser.add_argument("--generated-at")
    parser.add_argument("--context-json", default="{}")
    args = parser.parse_args(argv)
    try:
        context = json.loads(args.context_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid context-json: {exc}"}))
        return 2
    result = run_build(
        output_root=args.output_root,
        as_of_date=args.as_of_date,
        strategy_slug=args.strategy_slug,
        generated_at=args.generated_at,
        context=context,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

