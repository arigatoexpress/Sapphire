"""Pine static analysis utilities.

`static_analyzer.analyze_pine_source(text)` returns a dict of the form
`{"ok": bool, "errors": [...], "warnings": [...]}` covering syntax/contract
checks for `pine/standalone/*.pine` and committed `pine/generated/` exports.

The analyzer is pattern-based — it does NOT require the `tv` CLI / Pine
compiler to be available, so it can run in CI and pre-commit hooks.
"""

from __future__ import annotations

from .static_analyzer import analyze_pine_file, analyze_pine_source

__all__ = ["analyze_pine_source", "analyze_pine_file"]
