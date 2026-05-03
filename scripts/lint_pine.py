#!/usr/bin/env python3
"""CLI runner for `lib.pine.static_analyzer` — used by pre-commit + CI.

Usage::

    python3 scripts/lint_pine.py pine/standalone/*.pine
    python3 scripts/lint_pine.py --strict pine/standalone/*.pine

Default: exits 0 if every `.pine` file passes (no errors). Exits non-zero
if any file errors. Warnings are reported but do not affect the exit
status, matching the analyzer's `ok = not errors` semantics.

`--strict`: promotes ALL warnings to errors. Any warning in any file
makes the run exit non-zero. Useful for screener promotion where
unpaired strategy.entry/close or partial tuple bindings matter.

Non-`.pine` arguments are skipped with a stderr warning (the pre-commit
hook may pass mixed file types when filtering by `files:` regex).
"""

from __future__ import annotations

import argparse
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


def lint_paths(paths: list[str], *, strict: bool = False) -> int:
    """Lint every `.pine` path in `paths`. Return process exit code.

    `strict=True` promotes warnings to errors for exit-code purposes only;
    output formatting is unchanged so operators still see the
    error/warning split.
    """
    if not paths:
        print(
            "usage: lint_pine.py [--strict] <file.pine> [<file.pine> ...]",
            file=sys.stderr,
        )
        return 2

    any_errors = False
    any_warnings = False
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
        if warnings:
            any_warnings = True
        for err in errors:
            print(_format_row("error", err))
        for warn in warnings:
            print(_format_row("warn ", warn))

    if any_errors:
        return 1
    if strict and any_warnings:
        print("strict: warnings present, failing run", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Static analyzer for Pine v5 sources. "
            "Default exit: 0 unless errors. With --strict, warnings also fail."
        )
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Promote all warnings to errors for exit-code purposes",
    )
    parser.add_argument("paths", nargs="*", help="Pine source files to lint")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    return lint_paths(ns.paths, strict=ns.strict)


if __name__ == "__main__":
    raise SystemExit(main())
