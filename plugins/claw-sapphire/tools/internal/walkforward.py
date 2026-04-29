#!/usr/bin/env python3
"""Sapphire walk-forward plugin tool.

Read-only CLI over ``lib.analytics.walkforward`` and the
``services.walkforward.build`` artifact directory. Stdin-JSON actions:

- ``run``:     Run a walk-forward backtest in-process for a single strategy
               class against synthetic bars. Returns the full
               ``WalkforwardResult.to_dict()``.
- ``decompose``: Run walk-forward + regime decomposition. Includes per-regime
               buckets and the empirical regime distribution.
- ``deflated``: Run walk-forward and compute the walk-forward DSR.
- ``latest``:  Read the most recent manifest.json under
               ``data/backtests/walkforward/``. No computation.
- ``status``:  Caps + version + valid actions. No I/O.

This tool never calls live data. ``run`` / ``decompose`` / ``deflated`` use
the deterministic synthetic OHLCV from ``services.walkforward.build``. To
build against real bars, run ``python3 -m services.walkforward.build
--bars-source yfinance`` directly and then ``--action latest``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _evict_plugin_lib_shadow() -> None:
    """Match the cross_asset_intel pattern: ensure ``lib`` resolves to the repo
    root, not the plugins/claw-sapphire/lib namespace package.
    """
    import types

    repo_lib = REPO_ROOT / "lib"
    lib_mod = sys.modules.get("lib")
    lib_file = str(getattr(lib_mod, "__file__", "") or "")
    if "plugins/claw-sapphire/lib" in lib_file:
        for name in list(sys.modules):
            if name == "lib" or name.startswith("lib."):
                sys.modules.pop(name, None)
        lib_mod = None
    if lib_mod is None or not hasattr(lib_mod, "__path__"):
        mod = types.ModuleType("lib")
        mod.__path__ = [str(repo_lib)]  # type: ignore[attr-defined]
        sys.modules["lib"] = mod
        return
    paths = [path for path in list(lib_mod.__path__) if path != str(repo_lib)]  # type: ignore[attr-defined]
    lib_mod.__path__ = [str(repo_lib), *paths]  # type: ignore[attr-defined]


_evict_plugin_lib_shadow()

from lib.analytics.walkforward import (  # noqa: E402
    WalkforwardConfig,
    decompose_by_regime,
    deflated_sharpe_for_walkforward,
    load_regime_labels,
    run_walkforward,
)
from services.walkforward.build import (  # noqa: E402
    DEFAULT_HORIZONS,
    DEFAULT_OUTPUT_ROOT,
    STRATEGY_REGISTRY,
    VERSION,
    _aux_for,
    _resolve_strategy,
    synthetic_bars,
)

VALID_ACTIONS = ("run", "decompose", "deflated", "latest", "status")
DEFAULT_TRAIN = 90
DEFAULT_TEST = 30
MAX_BARS = 1500


def _coerce_int(raw: Any, default: int, *, lo: int = 1, hi: int = 1_000_000) -> int:
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected int, got {raw!r}") from exc
    if v < lo or v > hi:
        raise ValueError(f"value {v} outside [{lo}, {hi}]")
    return v


def _coerce_int_or_none(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


def _coerce_strategy(raw: Any) -> str:
    name = str(raw or "RegimeAwareRSI").strip()
    _resolve_strategy(name)  # raises if unknown
    return name


def _build_config(payload: dict[str, Any]) -> WalkforwardConfig:
    return WalkforwardConfig(
        train_bars=_coerce_int(payload.get("train"), DEFAULT_TRAIN, lo=60, hi=2000),
        test_bars=_coerce_int(payload.get("test"), DEFAULT_TEST, lo=20, hi=500),
        advance_bars=_coerce_int_or_none(payload.get("advance")),
        purge_bars=_coerce_int(payload.get("purge"), 0, lo=0, hi=200),
        embargo_bars=_coerce_int(payload.get("embargo"), 0, lo=0, hi=200),
        selection_metric=str(payload.get("metric") or "sortino"),
        bankroll=float(payload.get("bankroll") or 10_000.0),
        symbol=str(payload.get("symbol") or "SYNTH"),
        min_train_trades=_coerce_int(payload.get("min_train_trades"), 1, lo=0, hi=1000),
    )


def _build_bars(payload: dict[str, Any]) -> tuple[list[Any], dict[str, list[Any]]]:
    n_bars = _coerce_int(payload.get("n_bars"), 365, lo=80, hi=MAX_BARS)
    symbol = str(payload.get("symbol") or "SYNTH")
    bars = synthetic_bars(symbol, n_bars)
    aux = _aux_for(symbol, n_bars)
    return bars, aux


def run_action(payload: dict[str, Any]) -> dict[str, Any]:
    strategy = _coerce_strategy(payload.get("strategy"))
    cfg = _build_config(payload)
    bars, aux = _build_bars(payload)
    cls = _resolve_strategy(strategy)
    result = run_walkforward(cls, bars, aux=aux, config=cfg)
    return {
        "ok": True,
        "action": "run",
        "version": VERSION,
        "strategy": strategy,
        "result": result.to_dict(),
    }


def decompose_action(payload: dict[str, Any]) -> dict[str, Any]:
    strategy = _coerce_strategy(payload.get("strategy"))
    cfg = _build_config(payload)
    bars, aux = _build_bars(payload)
    cls = _resolve_strategy(strategy)
    result = run_walkforward(cls, bars, aux=aux, config=cfg)
    inline_labels = payload.get("labels")
    if inline_labels is not None and not isinstance(inline_labels, dict):
        return {"error": "labels must be a JSON object mapping date → label"}
    if inline_labels:
        labels = {str(k): str(v) for k, v in inline_labels.items()}
    else:
        labels = load_regime_labels()
    decomp = decompose_by_regime(
        result.concatenated_test_returns,
        result.concatenated_test_timestamps,
        labels=labels,
        strategy_cls=result.strategy_cls,
        symbol=result.symbol,
        semantics=str(payload.get("semantics") or "forward_fill"),
        default_label=str(payload.get("default_label") or "regime_uncertain"),
    )
    return {
        "ok": True,
        "action": "decompose",
        "version": VERSION,
        "strategy": strategy,
        "result_summary": {
            "n_windows": result.n_windows,
            "n_active_windows": result.n_active_windows,
            "mean_test_sortino": result.mean_test_sortino,
            "mean_test_sharpe": result.mean_test_sharpe,
            "n_observations": len(result.concatenated_test_returns),
        },
        "decomposition": decomp.to_dict(),
    }


def deflated_action(payload: dict[str, Any]) -> dict[str, Any]:
    strategy = _coerce_strategy(payload.get("strategy"))
    cfg = _build_config(payload)
    bars, aux = _build_bars(payload)
    cls = _resolve_strategy(strategy)
    result = run_walkforward(cls, bars, aux=aux, config=cfg)
    threshold = float(payload.get("threshold") or 0.95)
    dsr = deflated_sharpe_for_walkforward(result, threshold=threshold)
    return {
        "ok": True,
        "action": "deflated",
        "version": VERSION,
        "strategy": strategy,
        "result_summary": {
            "n_windows": result.n_windows,
            "n_active_windows": result.n_active_windows,
            "mean_test_sortino": result.mean_test_sortino,
            "mean_test_sharpe": result.mean_test_sharpe,
        },
        "deflated_sharpe": dsr.to_dict(),
    }


def latest_action(payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(payload.get("output_root") or DEFAULT_OUTPUT_ROOT)
    if not root.is_dir():
        return {
            "ok": False,
            "action": "latest",
            "error": f"no walk-forward artifacts at {root}",
        }
    days = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
    for d in days:
        manifest = d / "manifest.json"
        if manifest.is_file():
            return {
                "ok": True,
                "action": "latest",
                "version": VERSION,
                "date": d.name,
                "path": str(manifest),
                "manifest": json.loads(manifest.read_text(encoding="utf-8")),
            }
    return {"ok": False, "action": "latest", "error": "no manifest.json under any date dir"}


def status_action() -> dict[str, Any]:
    return {
        "ok": True,
        "action": "status",
        "version": VERSION,
        "valid_actions": list(VALID_ACTIONS),
        "default_strategy": "RegimeAwareRSI",
        "known_strategies": sorted(STRATEGY_REGISTRY),
        "default_horizons_days": list(DEFAULT_HORIZONS),
        "caps": {
            "max_bars": MAX_BARS,
            "min_train_bars": 60,
            "min_test_bars": 20,
        },
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower().replace("_", "-")
    try:
        if action == "run":
            return run_action(payload)
        if action == "decompose":
            return decompose_action(payload)
        if action in {"deflated", "deflated-sharpe", "dsr"}:
            return deflated_action(payload)
        if action == "latest":
            return latest_action(payload)
        if action == "status":
            return status_action()
        return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "valid_actions": list(VALID_ACTIONS)}


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
