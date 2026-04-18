"""Performance analytics — shape backtest output for the /analytics dashboard.

Reads `data/backtests/latest.json` and returns:
  - equity_curve (per-symbol, WITH-regime)
  - benchmark_curve (buy-and-hold same-window)
  - rolling_sharpe (30-day)
  - signal_quality (confidence vs pnl_pct scatter)
  - regime_breakdown (win rate + avg pnl grouped by regime)
  - monthly_returns (year → 12-month pnl)
"""
from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_BACKTEST_FILE = Path("data/backtests/latest.json")


def _rolling_sharpe(curve: list[tuple[str, float]], window: int = 30) -> list[dict]:
    """Rolling Sharpe over a daily-equity curve (annualized)."""
    out: list[dict] = []
    if len(curve) < window + 1:
        return out
    # daily returns
    rets: list[float] = []
    for i in range(1, len(curve)):
        prev = curve[i - 1][1]
        if prev > 0:
            rets.append((curve[i][1] - prev) / prev)
        else:
            rets.append(0.0)
    for i in range(window, len(rets) + 1):
        w = rets[i - window:i]
        mean = sum(w) / len(w)
        var = sum((r - mean) ** 2 for r in w) / len(w)
        std = math.sqrt(var)
        sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
        # curve index is i (returns uses 1-offset against curve indices)
        out.append({"date": curve[i][0], "sharpe": round(sharpe, 3)})
    return out


def _regime_breakdown(trades: list[dict]) -> list[dict]:
    """Group trades by regime → win rate, avg pnl, count."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[t.get("regime", "UNKNOWN")].append(t)
    out: list[dict] = []
    for regime, ts in sorted(groups.items()):
        wins = sum(1 for t in ts if (t.get("pnl") or 0) > 0)
        total_pnl = sum(t.get("pnl", 0) for t in ts)
        avg_pnl_pct = (sum(t.get("pnl_pct", 0) for t in ts) / len(ts)) if ts else 0.0
        out.append({
            "regime":      regime,
            "trade_count": len(ts),
            "win_rate":    round(wins / len(ts), 3) if ts else 0.0,
            "total_pnl":   round(total_pnl, 2),
            "avg_pnl_pct": round(avg_pnl_pct, 3),
        })
    return out


def _monthly_returns(trades: list[dict]) -> dict[str, list[float]]:
    """{year: [pnl_pct_jan, feb, ..., dec]} from trade exit dates."""
    buckets: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    for t in trades:
        exit_date = t.get("exit_date") or ""
        if len(exit_date) < 7:
            continue
        try:
            year = exit_date[:4]
            month_idx = int(exit_date[5:7]) - 1
        except ValueError:
            continue
        if 0 <= month_idx < 12:
            buckets[year][month_idx] += float(t.get("pnl_pct", 0))
    return {y: [round(v, 2) for v in months] for y, months in sorted(buckets.items())}


def build_performance_report(
    backtest_path: Path | None = None,
    *,
    primary_symbol: str = "BTC-USD",
    rolling_window: int = 30,
) -> dict[str, Any]:
    """Build the full analytics-page payload from `latest.json`."""
    path = backtest_path or DEFAULT_BACKTEST_FILE
    if not path.exists():
        return {"error": f"no backtest at {path}"}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"backtest unreadable: {e}"}

    with_r = data.get("with_regime") or {}
    without_r = data.get("without_regime") or {}
    symbols = sorted(with_r.keys())

    # Equity and benchmark come from primary symbol; fall back to first available.
    primary = with_r.get(primary_symbol) or (with_r.get(symbols[0]) if symbols else None) or {}
    equity  = [(d, v) for d, v in (primary.get("equity_curve") or [])]
    bench   = [(d, v) for d, v in (primary.get("benchmark_curve") or [])]

    equity_off = []
    if primary_symbol in without_r:
        equity_off = [(d, v) for d, v in (without_r[primary_symbol].get("equity_curve") or [])]

    rolling = _rolling_sharpe(equity, window=rolling_window)

    # Signal-quality scatter: aggregate trades across every symbol (WITH-regime).
    all_trades: list[dict] = []
    for sym, res in with_r.items():
        if isinstance(res, dict):
            for t in res.get("trades") or []:
                t = dict(t)
                t.setdefault("symbol", sym)
                all_trades.append(t)

    scatter = [
        {
            "symbol":     t.get("symbol"),
            "confidence": round(float(t.get("confidence", 0)), 3),
            "pnl_pct":    round(float(t.get("pnl_pct", 0)), 3),
            "regime":     t.get("regime", "UNKNOWN"),
            "score":      t.get("score", 0),
        }
        for t in all_trades
    ]

    summary_rows = []
    for sym in symbols:
        on = with_r.get(sym, {})
        off = without_r.get(sym, {})
        if "error" in on:
            continue
        summary_rows.append({
            "symbol":        sym,
            "with_regime":   {k: on.get(k)  for k in ("total_return_pct", "sharpe", "sortino",
                                                     "max_drawdown_pct", "win_rate",
                                                     "profit_factor", "trade_count")},
            "without_regime":{k: off.get(k) for k in ("total_return_pct", "sharpe", "sortino",
                                                     "max_drawdown_pct", "win_rate",
                                                     "profit_factor", "trade_count")},
        })

    return {
        "generated_at":     data.get("timestamp"),
        "primary_symbol":   primary_symbol if primary_symbol in with_r else (symbols[0] if symbols else None),
        "equity_curve":     [{"date": d, "value": v} for d, v in equity],
        "equity_curve_off": [{"date": d, "value": v} for d, v in equity_off],
        "benchmark_curve":  [{"date": d, "value": v} for d, v in bench],
        "rolling_sharpe":   rolling,
        "signal_quality":   scatter,
        "regime_breakdown": _regime_breakdown(all_trades),
        "monthly_returns":  _monthly_returns(all_trades),
        "summary":          summary_rows,
    }
