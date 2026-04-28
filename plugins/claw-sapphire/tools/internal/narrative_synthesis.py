#!/usr/bin/env python3
"""Sapphire Narrative Synthesis plugin tool.

Stdin-JSON interface for the LLM Narrative Thesis Engine. Default actions are
offline and deterministic; live Gemini synthesis requires the library-level
``SAPPHIRE_NARRATIVE_LIVE=1`` gate, a Gemini key, and a sensitivity pass.

Actions:
- ``synthesize-once`` — generate a thesis from an inline correlated signal, or
  from the latest signal for ``symbol``/``timeframe``.
- ``latest`` — read ``data/narratives/<date>/theses.jsonl``.
- ``history`` — read narrative history, optionally filtered by symbol/timeframe.
- ``rubric-score`` — score an inline thesis against the deterministic rubric.
- ``status`` — read-only cache/cap/service status.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_lib_module(qualname: str, relpath: str) -> Any:
    """Load a repo-root module by path, avoiding plugin-local ``lib`` shadowing."""
    import types as _types

    if qualname in sys.modules:
        existing = sys.modules[qualname]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing

    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")

    parts = qualname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules or not hasattr(sys.modules[parent], "__path__"):
            mod = _types.ModuleType(parent)
            mod.__path__ = [str(REPO_ROOT / Path(*parts[:i]))]  # type: ignore[attr-defined]
            sys.modules[parent] = mod

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


_load_repo_lib_module("lib.core.provenance", "lib/core/provenance.py")
_load_repo_lib_module("lib.synthesis.prompts", "lib/synthesis/prompts.py")
_load_repo_lib_module("lib.synthesis.rubric", "lib/synthesis/rubric.py")
_engine = _load_repo_lib_module("lib.synthesis.narrative_engine", "lib/synthesis/narrative_engine.py")
_synthesis_pkg = _load_repo_lib_module("lib.synthesis", "lib/synthesis/__init__.py")
_service = _load_repo_lib_module("services.synthesis.run", "services/synthesis/run.py")

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "narratives"
DEFAULT_SIGNAL_ROOT = REPO_ROOT / "data" / "correlated_signals"
MAX_HISTORY_ROWS = 200

GENERATOR = "plugins.claw_sapphire.narrative_synthesis"
VERSION = "0.1.0"


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _read_jsonl(path: Path, *, limit: int = MAX_HISTORY_ROWS) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _narrative_path(date: str | None = None) -> Path:
    return DEFAULT_OUTPUT_ROOT / (date or _today()) / "theses.jsonl"


def _latest_signal(symbol: str | None, timeframe: str | None, *, date: str | None = None) -> dict[str, Any] | None:
    rows = _service.latest_signal_rows(input_root=DEFAULT_SIGNAL_ROOT, date=date)
    symbol_norm = str(symbol or "").upper()
    timeframe_norm = str(timeframe or "").lower()
    for row in reversed(rows):
        if symbol_norm and str(row.get("symbol") or "").upper() != symbol_norm:
            continue
        if timeframe_norm and str(row.get("timeframe") or "").lower() != timeframe_norm:
            continue
        return row
    return rows[-1] if rows else None


def synthesize_once_action(payload: dict[str, Any]) -> dict[str, Any]:
    signal = payload.get("signal")
    if not isinstance(signal, dict):
        signal = _latest_signal(payload.get("symbol"), payload.get("timeframe"), date=payload.get("date"))
    if not isinstance(signal, dict):
        return {
            "ok": False,
            "reason": "no signal provided and no latest correlated signal found",
            "hint": "pass an inline `signal` object or run the signal_correlator first",
        }
    return _engine.synthesize(
        signal,
        mode=payload.get("mode") or "dry-run",
        model=payload.get("model") or _engine.DEFAULT_MODEL,
        max_output_tokens=int(payload.get("max_output_tokens") or 2048),
        ttl_seconds=int(payload.get("ttl_seconds") or 86_400),
    )


def latest_action(*, date: str | None = None, limit: int = 20) -> dict[str, Any]:
    path = _narrative_path(date)
    rows = _read_jsonl(path, limit=max(1, min(limit, MAX_HISTORY_ROWS)))
    return {
        "ok": bool(rows),
        "date": date or _today(),
        "path": str(path),
        "count": len(rows),
        "rows": rows,
        "reason": "" if rows else "no narrative file",
    }


def history_action(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    date: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = _read_jsonl(_narrative_path(date), limit=MAX_HISTORY_ROWS)
    symbol_norm = str(symbol or "").upper()
    timeframe_norm = str(timeframe or "").lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if symbol_norm and str(row.get("symbol") or "").upper() != symbol_norm:
            continue
        if timeframe_norm and str(row.get("timeframe") or "").lower() != timeframe_norm:
            continue
        filtered.append(row)
    limit = max(1, min(limit, MAX_HISTORY_ROWS))
    filtered = filtered[-limit:]
    return {
        "ok": bool(filtered),
        "date": date or _today(),
        "count": len(filtered),
        "rows": filtered,
    }


def rubric_score_action(payload: dict[str, Any]) -> dict[str, Any]:
    thesis = payload.get("thesis")
    if not isinstance(thesis, dict):
        return {"ok": False, "error": "`thesis` object is required"}
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else None
    score = _synthesis_pkg.score_narrative(thesis, signal=signal)
    return {"ok": True, "rubric": score.to_dict()}


def status_action() -> dict[str, Any]:
    engine = _engine.status()
    service = _service.status()
    return {
        "ok": True,
        "generator": GENERATOR,
        "version": VERSION,
        "engine": engine,
        "service": service,
        "actions": ["synthesize-once", "latest", "history", "rubric-score", "status"],
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "synthesize-once").strip().lower()
    if action == "synthesize-once":
        return synthesize_once_action(payload)
    if action == "latest":
        return latest_action(date=payload.get("date"), limit=int(payload.get("limit") or 20))
    if action == "history":
        return history_action(
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
            date=payload.get("date"),
            limit=int(payload.get("limit") or 50),
        )
    if action == "rubric-score":
        return rubric_score_action(payload)
    if action == "status":
        return status_action()
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["synthesize-once", "latest", "history", "rubric-score", "status"],
    }


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
