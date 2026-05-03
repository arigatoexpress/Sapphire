#!/usr/bin/env python3
"""CLI runner for `lib.pine.static_analyzer` — used by pre-commit + CI.

Usage::

    python3 scripts/lint_pine.py pine/standalone/*.pine

Exits 0 if every `.pine` file passes (no errors). Exits non-zero if any
file errors. Warnings are reported but do not affect the exit status,
matching the analyzer's `ok = not errors` semantics.

Non-`.pine` arguments are skipped with a stderr warning (the pre-commit
hook may pass mixed file types when filtering by `files:` regex).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path so `from lib.pine import ...` works whether this
# script is invoked from the project root or from a worktree.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.pine import analyze_pine_file  # noqa: E402


def _format_row(prefix: str, row: dict) -> str:
    line = row.get("line", "?")
    msg = row.get("msg", "")
    return f"    {prefix} L{line}: {msg}"


def lint_paths(paths: list[str]) -> int:
    """Lint every `.pine` path in `paths`. Return process exit code."""
    if not paths:
        print("usage: lint_pine.py <file.pine> [<file.pine> ...]", file=sys.stderr)
        return 2

    any_errors = False
    for raw in paths:
        path = Path(raw)
        if path.suffix != ".pine":
            print(f"warning: skipping non-.pine path: {path}", file=sys.stderr)
            continue
        if not path.exists():
            print(f"ERR {path}: file not found", file=sys.stderr)
            any_errors = True
            continue
        try:
            result = analyze_pine_file(path)
        except Exception as exc:  # noqa: BLE001 — surface any analyzer crash
            print(f"ERR {path}: analyzer crashed: {exc}", file=sys.stderr)
            any_errors = True
            continue

        errors = result.get("errors", [])
        warnings = result.get("warnings", [])
        if errors:
            any_errors = True
            print(f"ERR {path}: {len(errors)} errors, {len(warnings)} warnings")
        else:
            print(f"OK  {path}: 0 errors, {len(warnings)} warnings")
        for err in errors:
            print(_format_row("error", err))
        for warn in warnings:
            print(_format_row("warn ", warn))

    return 1 if any_errors else 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return lint_paths(args)


if __name__ == "__main__":
    raise SystemExit(main())
