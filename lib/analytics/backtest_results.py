"""Backtest result reader.

Reads the JSON artifacts produced by lib.analytics.strategies.save_results
(strategy_sweep_*.json and best_per_symbol_*.json under
data/backtests/strategies/), sanitizes them for dashboard consumption, and
returns leaderboards ranked by configurable metric.

Sanitization: Python's json.dump emits `Infinity` for infinite floats,
which is valid Python but rejected by strict JSON parsers (browsers).
All infinities are converted to the sentinel string "inf".
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BACKTESTS_DIR = ROOT / "data" / "backtests" / "strategies"


def _clean(v: Any) -> Any:
    """Recursively replace inf/nan with JSON-safe values."""
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if math.isnan(v):
            return None
        return v
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _parse_lax(raw: str) -> Any:
    """Parse JSON leniently — Python's Infinity/NaN extension is accepted."""
    return json.loads(raw)


def _latest_file(prefix: str) -> Path | None:
    if not BACKTESTS_DIR.exists():
        return None
    candidates = sorted(BACKTESTS_DIR.glob(f"{prefix}_*.json"))
    return candidates[-1] if candidates else None


def _file_stamp(p: Path) -> str | None:
    """Extract the ISO-ish stamp from a strategy_sweep_20260418T171613Z.json filename."""
    stem = p.stem  # strategy_sweep_20260418T171613Z
    for prefix in ("strategy_sweep_", "best_per_symbol_"):
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    return None


def load_latest_sweep() -> dict[str, Any] | None:
    """Load the newest full strategy sweep, sanitized."""
    f = _latest_file("strategy_sweep")
    if f is None:
        return None
    try:
        raw = f.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = _parse_lax(raw)
    except json.JSONDecodeError as e:
        log.warning("failed to parse sweep %s: %s", f.name, e)
        return None
    data = _clean(data)
    data["source_file"] = f.name
    return data


def load_latest_best() -> dict[str, Any] | None:
    """Load the newest best-per-symbol result, sanitized."""
    f = _latest_file("best_per_symbol")
    if f is None:
        return None
    try:
        raw = f.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = _parse_lax(raw)
    except json.JSONDecodeError as e:
        log.warning("failed to parse best %s: %s", f.name, e)
        return None
    data = _clean(data)
    data["source_file"] = f.name
    return data


_LEADERBOARD_METRICS = {
    "sortino",
    "sharpe",
    "calmar",
    "total_return_pct",
    "win_rate",
    "profit_factor",
}


def _metric_key(metric: str):
    """Sort key — used with reverse=True. Non-None rows rank above None.

    Returns (1, value) for real numbers and "inf" sentinels so they sort above
    (0, 0.0) which we return for missing / NaN entries.
    """

    def key(r):
        v = r.get(metric)
        if v is None:
            return (0, 0.0)
        if isinstance(v, str):
            return (1, float("inf") if v == "inf" else 0.0)
        return (1, float(v))

    return key


def leaderboard(
    metric: str = "sortino",
    limit: int = 10,
    include_minimal_trades: bool = False,
) -> dict[str, Any]:
    """Rank strategies across the latest sweep.

    Args:
        metric: one of sortino / sharpe / calmar / total_return_pct / win_rate / profit_factor.
        limit: top-N rows to return.
        include_minimal_trades: if False, drop rows with <5 total_trades (too
            little data to trust).
    """
    if metric not in _LEADERBOARD_METRICS:
        raise ValueError(f"metric must be one of {sorted(_LEADERBOARD_METRICS)}")

    sweep = load_latest_sweep()
    if not sweep or not sweep.get("results"):
        return {
            "metric": metric,
            "limit": limit,
            "rows": [],
            "total_rows": 0,
            "source_file": None,
            "computed_at": None,
            "note": "No backtest results found — run `python3 -m lib.analytics.strategies` to generate.",
        }

    results = sweep["results"]
    if not include_minimal_trades:
        results = [r for r in results if (r.get("total_trades") or 0) >= 5]

    results_sorted = sorted(results, key=_metric_key(metric), reverse=True)[:limit]

    return {
        "metric": metric,
        "limit": limit,
        "rows": results_sorted,
        "total_rows": len(sweep["results"]),
        "filtered_rows": len(results),
        "source_file": sweep.get("source_file"),
        "computed_at": sweep.get("computed_at"),
    }


def summary() -> dict[str, Any]:
    """Dashboard-ready summary: best strategy per symbol + sweep metadata."""
    best = load_latest_best()
    sweep = load_latest_sweep()
    if best is None and sweep is None:
        return {
            "have_results": False,
            "best_per_symbol": [],
            "total_backtests": 0,
            "computed_at": None,
            "source_file": None,
            "note": "No backtest artifacts under data/backtests/strategies/.",
        }

    stamp = None
    source_file = None
    if best:
        stamp = best.get("computed_at")
        source_file = best.get("source_file")
    elif sweep:
        stamp = sweep.get("computed_at")
        source_file = sweep.get("source_file")

    best_rows = []
    if best and isinstance(best.get("results"), list):
        for r in best["results"]:
            best_rows.append(
                {
                    "strategy_cls": r.get("strategy_cls"),
                    "strategy_name": r.get("strategy_name"),
                    "symbol": r.get("symbol"),
                    "params": r.get("params"),
                    "sortino": r.get("sortino"),
                    "sharpe": r.get("sharpe"),
                    "calmar": r.get("calmar"),
                    "total_return_pct": r.get("total_return_pct"),
                    "win_rate": r.get("win_rate"),
                    "profit_factor": r.get("profit_factor"),
                    "max_drawdown_pct": r.get("max_drawdown_pct"),
                    "total_trades": r.get("total_trades"),
                }
            )

    total_backtests = (sweep or {}).get("total_backtests") or len((sweep or {}).get("results", []))
    age_hours = None
    if stamp:
        try:
            dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            age_hours = round((datetime.now(dt.tzinfo) - dt).total_seconds() / 3600, 1)
        except (ValueError, AttributeError):
            pass

    return {
        "have_results": True,
        "best_per_symbol": best_rows,
        "total_backtests": total_backtests,
        "computed_at": stamp,
        "age_hours": age_hours,
        "source_file": source_file,
    }


if __name__ == "__main__":
    import sys

    sub = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if sub == "summary":
        out = summary()
    elif sub == "leaderboard":
        metric = sys.argv[2] if len(sys.argv) > 2 else "sortino"
        out = leaderboard(metric=metric, limit=int(sys.argv[3]) if len(sys.argv) > 3 else 10)
    else:
        out = {"error": f"unknown sub-command {sub!r}; use summary|leaderboard"}
    json.dump(out, sys.stdout, indent=2, default=str)
    print()
