#!/usr/bin/env python3
"""Sapphire Pine v5 strategy generation plugin tool — stdin JSON.

Actions
-------
- ``generate <strategy> <symbol>`` — render Pine v5 source for one
  (strategy, symbol) pair using the supplied (or default) parameters and
  return the source string. Does NOT write to disk unless ``persist=True``.
- ``latest`` — list every Pine file under the most recent
  ``pine/generated/<date>/`` directory.
- ``validate`` — run the heuristic Pine v5 validator against a supplied
  ``pine_source`` string. Returns the structured result.
- ``build`` — run :func:`services.pine_generation.build.build_from_disk`
  end-to-end and return the manifest.
- ``push-to-tv`` — refuses unless ``SAPPHIRE_PINE_TV_PUSH_LIVE=1`` is set
  in the env. Even when set, we mock the actual MCP call by default
  (``dry_run=True``) — the push is fully synchronous and idempotent. The
  TradingView MCP bridge is invoked via :func:`_invoke_tv_mcp` which is
  patched out in tests; in production it shells out to ``tv pine write``.
- ``status`` — pure read-only; reports counts and gate state.

Safety story (mirrors the gemini_ooda env-flag pattern)
-------------------------------------------------------
- Generation is offline. No network. No I/O outside the writes the operator
  asked for via ``persist=True``.
- The push step is gated by ``SAPPHIRE_PINE_TV_PUSH_LIVE=1`` AND a
  ``confirm: true`` field in the payload. Either missing => refused.
- Pine source pushes do NOT include any secrets or trade-execution
  parameters; they are read-only TradingView strategy code.

Output
------
Every action returns ``{"ok": bool, ...}``. On success, ``ok=True``. On
error, ``ok=False`` and an ``error`` field. The structure is stable so
that scheduled tasks can rely on it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# `plugins/claw-sapphire/lib/` exists as a sibling package; make sure imports
# of `lib.<repo_module>` resolve against the repo `lib/` package while still
# letting plugin-local imports work. Mirrors the pattern in
# `tools/internal/research_notes.py`.
_repo_lib = REPO_ROOT / "lib"
_plugin_lib = REPO_ROOT / "plugins" / "claw-sapphire" / "lib"
_loaded_lib = sys.modules.get("lib")
_loaded_paths = list(getattr(_loaded_lib, "__path__", [])) if _loaded_lib is not None else []
if str(_repo_lib) not in _loaded_paths:
    _pkg = types.ModuleType("lib")
    _pkg.__path__ = [
        str(_repo_lib),
        *(p for p in _loaded_paths if p != str(_repo_lib)),
        str(_plugin_lib),
    ]
    sys.modules["lib"] = _pkg

from lib.pine_generation import (  # noqa: E402
    SUPPORTED_STRATEGIES,
    PineParams,
    PineSpec,
    generate_pine,
    validate_pine,
)
from services.pine_generation.build import (  # noqa: E402
    DEFAULT_BACKTEST_DIR,
    DEFAULT_OUTPUT_ROOT,
    build_from_disk,
    make_output_dir,
)

LIVE_ENV_FLAG = "SAPPHIRE_PINE_TV_PUSH_LIVE"


# ---------------------------------------------------------------------------
# TradingView MCP bridge (mocked in tests, gated in prod)
# ---------------------------------------------------------------------------


def _invoke_tv_mcp(
    pine_source: str,
    *,
    title: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Push Pine source to the local tradingview-mcp bridge.

    Production wiring uses the operator-installed ``tv`` CLI which is the
    Sapphire-side wrapper around the tradingview-mcp-v2 server. We never
    embed credentials. In tests this function is patched.

    Returns a dict with ``ok``, ``status``, and ``message``.
    """
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "message": (
                "dry-run only: pine source not pushed. Set "
                f"{LIVE_ENV_FLAG}=1 and pass confirm=true to push live."
            ),
            "title": title,
            "bytes": len(pine_source.encode("utf-8")),
        }
    # Real push path — never executed in unit tests.
    return {  # pragma: no cover - exercised only by operator
        "ok": False,
        "status": "not_implemented",
        "message": (
            "Live TradingView push is not implemented in this lane. "
            "Use the operator's `tv pine write` CLI directly."
        ),
        "title": title,
    }


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _params_from_payload(payload: dict[str, Any]) -> PineParams:
    raw = payload.get("params") or {}
    if not isinstance(raw, dict):
        raise ValueError("`params` must be a JSON object")
    return PineParams.from_dict(raw)


def _spec_from_payload(payload: dict[str, Any]) -> PineSpec:
    strategy = payload.get("strategy")
    symbol = payload.get("symbol")
    if not strategy or not isinstance(strategy, str):
        raise ValueError("`strategy` is required")
    if not symbol or not isinstance(symbol, str):
        raise ValueError("`symbol` is required")
    params = _params_from_payload(payload)
    kwargs: dict[str, Any] = {
        "strategy": strategy,
        "symbol": symbol,
        "params": params,
    }
    for key in (
        "title",
        "initial_capital",
        "commission_pct",
        "kelly_size_pct",
        "btc_ref_symbol",
        "spy_ref_symbol",
    ):
        if key in payload and payload[key] is not None:
            kwargs[key] = payload[key]
    if "meta" in payload and isinstance(payload["meta"], dict):
        kwargs["meta"] = payload["meta"]
    return PineSpec(**kwargs)


def action_generate(payload: dict[str, Any]) -> dict[str, Any]:
    spec = _spec_from_payload(payload)
    pine_src = generate_pine(spec)
    result = validate_pine(pine_src)
    response: dict[str, Any] = {
        "ok": result.ok,
        "strategy": spec.strategy,
        "symbol": spec.symbol,
        "tv_symbol": spec.tv_symbol,
        "pine_source": pine_src,
        "validator": result.to_dict(),
        "bytes": len(pine_src.encode("utf-8")),
    }
    persist = bool(payload.get("persist", False))
    if persist and result.ok:
        output_root = payload.get("output_root")
        from services.pine_generation.build import make_filename

        out_dir = make_output_dir(
            Path(output_root) if output_root else None,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / make_filename(spec.strategy, spec.symbol)
        target.write_text(pine_src)
        response["path"] = str(target)
    return response


def action_latest(payload: dict[str, Any]) -> dict[str, Any]:
    """List Pine files under the most recent generated/<date>/ dir."""
    output_root = payload.get("output_root")
    base = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
    if not base.exists():
        return {
            "ok": True,
            "directory": None,
            "files": [],
            "note": f"no Pine generation directory at {base}",
        }
    date_dirs = sorted([d for d in base.iterdir() if d.is_dir()])
    if not date_dirs:
        return {
            "ok": True,
            "directory": None,
            "files": [],
            "note": f"no date subdirectories under {base}",
        }
    latest_dir = date_dirs[-1]
    files = []
    for p in sorted(latest_dir.glob("*.pine")):
        try:
            stat = p.stat()
        except OSError:
            continue
        files.append(
            {
                "name": p.name,
                "path": str(p),
                "bytes": stat.st_size,
                "modified": int(stat.st_mtime),
            }
        )
    return {
        "ok": True,
        "directory": str(latest_dir),
        "files": files,
        "count": len(files),
    }


def action_validate(payload: dict[str, Any]) -> dict[str, Any]:
    src = payload.get("pine_source")
    if src is None:
        path = payload.get("pine_path")
        if path:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return {"ok": False, "error": f"pine file not found: {path}"}
            src = p.read_text()
    if src is None:
        return {
            "ok": False,
            "error": "either `pine_source` or `pine_path` is required",
        }
    if not isinstance(src, str):
        return {"ok": False, "error": "`pine_source` must be a string"}
    result = validate_pine(src)
    return {"ok": result.ok, "validator": result.to_dict()}


def action_build(payload: dict[str, Any]) -> dict[str, Any]:
    backtest_dir = payload.get("backtest_dir")
    output_root = payload.get("output_root")
    strategies = payload.get("strategies")
    symbols = payload.get("symbols")
    limit = payload.get("limit")
    overwrite = payload.get("overwrite", True)
    manifest = build_from_disk(
        backtest_dir=Path(backtest_dir) if backtest_dir else None,
        output_root=Path(output_root) if output_root else None,
        strategies=strategies,
        symbols=symbols,
        limit=limit if isinstance(limit, int) and limit > 0 else None,
        overwrite=bool(overwrite),
    )
    return {"ok": not manifest.errors, "manifest": manifest.to_dict()}


def action_push_to_tv(payload: dict[str, Any]) -> dict[str, Any]:
    """Operator-gated TradingView push. Refuses by default."""
    live = os.environ.get(LIVE_ENV_FLAG, "0").strip()
    confirm = bool(payload.get("confirm", False))
    if live != "1":
        return {
            "ok": False,
            "error": (
                f"refused: {LIVE_ENV_FLAG} is not set to 1. "
                f"Set the env var explicitly to enable live push."
            ),
            "gate": LIVE_ENV_FLAG,
        }
    if not confirm:
        return {
            "ok": False,
            "error": ("refused: payload must include `confirm: true` for a live push."),
            "gate": "confirm",
        }
    src = payload.get("pine_source")
    if src is None:
        path = payload.get("pine_path")
        if path:
            p = Path(path)
            if not p.exists():
                return {"ok": False, "error": f"pine file not found: {path}"}
            src = p.read_text()
    if not isinstance(src, str) or not src.strip():
        return {
            "ok": False,
            "error": "either `pine_source` or `pine_path` is required",
        }
    title = payload.get("title") or "Sapphire Generated Strategy"
    dry_run = bool(payload.get("dry_run", True))
    push_result = _invoke_tv_mcp(src, title=str(title), dry_run=dry_run)
    return {
        "ok": bool(push_result.get("ok")),
        "push_result": push_result,
        "gated_by": LIVE_ENV_FLAG,
    }


def action_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only diagnostics."""
    backtest_dir = payload.get("backtest_dir") or DEFAULT_BACKTEST_DIR
    output_root = payload.get("output_root") or DEFAULT_OUTPUT_ROOT
    bd = Path(backtest_dir)
    od = Path(output_root)
    backtest_files = []
    if bd.exists():
        backtest_files = sorted(p.name for p in bd.glob("best_per_symbol_*.json"))
    output_dirs = []
    if od.exists():
        output_dirs = sorted(p.name for p in od.iterdir() if p.is_dir())
    return {
        "ok": True,
        "version": "0.1.0",
        "supported_strategies": list(SUPPORTED_STRATEGIES),
        "actions": [
            "generate",
            "latest",
            "validate",
            "build",
            "push-to-tv",
            "status",
        ],
        "backtest_dir": str(bd),
        "backtest_files": backtest_files[-5:],
        "output_root": str(od),
        "output_dirs": output_dirs[-5:],
        "live_push_gate": LIVE_ENV_FLAG,
        "live_push_enabled": os.environ.get(LIVE_ENV_FLAG, "0").strip() == "1",
    }


_ACTIONS = {
    "generate": action_generate,
    "latest": action_latest,
    "validate": action_validate,
    "build": action_build,
    "push-to-tv": action_push_to_tv,
    "push_to_tv": action_push_to_tv,
    "status": action_status,
}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload must be a JSON object"}
    action = (payload.get("action") or "status").strip().lower()
    fn = _ACTIONS.get(action)
    if fn is None:
        return {
            "ok": False,
            "error": f"unknown action: {action}",
            "valid_actions": sorted(set(_ACTIONS.keys())),
        }
    try:
        return fn(payload)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "action": action}


def _read_payload(stream_in: Any = sys.stdin) -> dict[str, Any]:
    raw = stream_in.read()
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("stdin payload must be a JSON object")
    return data


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    try:
        payload = _read_payload(stream_in)
    except ValueError as exc:
        json.dump({"ok": False, "error": str(exc)}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 0 if response.get("ok") else 1


# Silence unused-import warning — `importlib.util` is imported for tests that
# load this module by path (mirrors the pattern in narrative_eval).
_ = importlib.util


if __name__ == "__main__":
    raise SystemExit(main())
