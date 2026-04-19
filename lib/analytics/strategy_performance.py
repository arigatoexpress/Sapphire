"""Strategy performance aggregator.

Reads every closed-trade source, normalizes to a single record shape, then
groups by strategy, timeframe bucket, and the cross-product of both. Feeds
the dashboard `/api/strategy-performance` endpoint and a CLI report.

Timeframe buckets are chosen by hold duration (closed_at - opened_at):
  1h  — held under 1 hour
  4h  — under 4 hours
  1d  — under 24 hours
  7d  — under 7 days
  30d — under 30 days
  all — longer than 30 days

Sources:
  data/signals/*.jsonl           scored-signal daily files (pipeline output)
  data/performance/signals.jsonl PerformanceTracker writes
  data/paper_portfolio.json      paper_trader closed trade history

Per-group metrics: trades, wins, losses, win_rate, total_pnl_usd,
avg_pnl_usd, best, worst, profit_factor, sortino, avg_roi_pct.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from statistics import stdev
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SIGNALS_DIR = ROOT / "data" / "signals"
PERF_SIGNALS = ROOT / "data" / "performance" / "signals.jsonl"
PAPER_PORTFOLIO = ROOT / "data" / "paper_portfolio.json"

_TIMEFRAME_BUCKETS: list[tuple[str, timedelta]] = [
    ("1h", timedelta(hours=1)),
    ("4h", timedelta(hours=4)),
    ("1d", timedelta(days=1)),
    ("7d", timedelta(days=7)),
    ("30d", timedelta(days=30)),
]
TIMEFRAME_ORDER = [name for name, _ in _TIMEFRAME_BUCKETS] + ["all"]


def _bucket_for(duration: timedelta | None) -> str:
    if duration is None:
        return "all"
    for name, limit in _TIMEFRAME_BUCKETS:
        if duration <= limit:
            return name
    return "all"


def _parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _normalize(
    strategy: str,
    symbol: str,
    direction: str | None,
    outcome: str,
    pnl_usd: float,
    entry: float,
    exit_: float,
    position_usd: float,
    confidence: float,
    regime: str,
    opened: str | None,
    closed: str | None,
    source: str,
) -> dict[str, Any]:
    o = _parse_iso(opened)
    c = _parse_iso(closed)
    duration = (c - o) if (o and c) else None
    roi_pct = (pnl_usd / position_usd * 100.0) if position_usd else 0.0
    return {
        "strategy": strategy or "unknown",
        "symbol": symbol or "?",
        "direction": direction,
        "outcome": outcome,
        "pnl_usd": float(pnl_usd),
        "entry_price": float(entry),
        "exit_price": float(exit_),
        "position_usd": float(position_usd),
        "confidence": float(confidence),
        "regime": regime or "UNKNOWN",
        "opened_at": opened,
        "closed_at": closed,
        "duration_h": duration.total_seconds() / 3600 if duration else None,
        "timeframe": _bucket_for(duration),
        "roi_pct": roi_pct,
        "source": source,
    }


def _iter_signals_dir() -> Iterable[dict[str, Any]]:
    if not SIGNALS_DIR.exists():
        return
    for f in sorted(SIGNALS_DIR.glob("*.jsonl")):
        try:
            raw = f.read_text()
        except OSError:
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            outcome = r.get("outcome")
            if outcome not in {"win", "loss", "break_even", "timeout"}:
                continue
            yield _normalize(
                strategy=r.get("strategy") or "unknown",
                symbol=r.get("symbol", "?"),
                direction=r.get("direction"),
                outcome=outcome,
                pnl_usd=float(r.get("pnl_usd") or 0.0),
                entry=float(r.get("price") or 0.0),
                exit_=float(r.get("close_price") or 0.0),
                position_usd=float(r.get("position_usd") or 0.0),
                confidence=float(r.get("confidence") or 0.0),
                regime=r.get("regime", "UNKNOWN"),
                opened=r.get("timestamp"),
                closed=r.get("closed_at"),
                source="signals_dir",
            )


def _iter_perf_signals() -> Iterable[dict[str, Any]]:
    if not PERF_SIGNALS.exists():
        return
    try:
        raw = PERF_SIGNALS.read_text()
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        outcome = r.get("outcome")
        if outcome not in {"win", "loss", "break_even", "timeout"}:
            continue
        entry = float(r.get("entry_price") or 0.0)
        pnl_pct = r.get("pnl_pct")
        position_usd = float(r.get("position_usd") or 0.0) or 1000.0
        pnl_usd = float(pnl_pct) * position_usd if pnl_pct is not None else 0.0
        yield _normalize(
            strategy=r.get("strategy") or r.get("source") or "unknown",
            symbol=r.get("symbol", "?"),
            direction=r.get("direction"),
            outcome=outcome,
            pnl_usd=pnl_usd,
            entry=entry,
            exit_=float(r.get("exit_price") or 0.0),
            position_usd=position_usd,
            confidence=float(r.get("confidence") or 0.0),
            regime=r.get("regime", "UNKNOWN"),
            opened=r.get("recorded_at"),
            closed=r.get("closed_at"),
            source="perf_signals",
        )


def _iter_paper_portfolio() -> Iterable[dict[str, Any]]:
    if not PAPER_PORTFOLIO.exists():
        return
    try:
        d = json.loads(PAPER_PORTFOLIO.read_text())
    except (OSError, json.JSONDecodeError):
        return
    for h in d.get("history", []):
        pnl = float(h.get("pnl") or 0.0)
        outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "break_even"
        side = (h.get("side") or "").upper()
        direction = "long" if side == "BUY" else "short" if side == "SELL" else None
        yield _normalize(
            strategy=h.get("strategy") or "paper_trader",
            symbol=h.get("symbol", "?"),
            direction=direction,
            outcome=outcome,
            pnl_usd=pnl,
            entry=float(h.get("entry_price") or 0.0),
            exit_=float(h.get("exit_price") or 0.0),
            position_usd=float(h.get("original_size_usd") or h.get("size_usd") or 0.0),
            confidence=float(h.get("confidence") or 0.0),
            regime="UNKNOWN",
            opened=h.get("opened_at"),
            closed=h.get("closed_at"),
            source="paper_portfolio",
        )


def load_all_trades() -> list[dict[str, Any]]:
    """Return every closed trade from every source, deduplicated by (strategy, symbol, opened_at, closed_at)."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()
    for iterator in (_iter_signals_dir(), _iter_perf_signals(), _iter_paper_portfolio()):
        for t in iterator:
            key = (t["strategy"], t["symbol"], t["opened_at"], t["closed_at"])
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def _sortino(pnls: list[float]) -> float | None:
    if len(pnls) < 2:
        return None
    downside = [p for p in pnls if p < 0]
    if len(downside) < 2:
        return None
    dn_std = stdev(downside)
    if dn_std == 0:
        return None
    mean_r = sum(pnls) / len(pnls)
    return mean_r / dn_std


def _sharpe(values: list[float]) -> float | None:
    """Sharpe-like ratio on a series of per-trade returns (not annualized
    — trade durations vary, so we report the dimensionless mean/stdev ratio).
    """
    if len(values) < 2:
        return None
    sd = stdev(values)
    if sd == 0:
        return None
    return (sum(values) / len(values)) / sd


def _avg_hold_hours(trades: list[dict[str, Any]]) -> float | None:
    durations = [t["duration_h"] for t in trades if t.get("duration_h") is not None]
    if not durations:
        return None
    return sum(durations) / len(durations)


def _stats_for(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": None,
            "total_pnl_usd": 0.0, "avg_pnl_usd": None,
            "best": None, "worst": None,
            "profit_factor": None, "sortino": None, "sharpe": None,
            "avg_roi_pct": None, "total_position_usd": 0.0,
            "portfolio_roi_pct": None, "avg_hold_hours": None,
            "expectancy_usd": None,
        }
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    scored = wins + losses
    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_position = sum(t["position_usd"] for t in trades)
    win_pnl = sum(t["pnl_usd"] for t in wins)
    loss_pnl = sum(t["pnl_usd"] for t in losses)
    win_rate = (len(wins) / len(scored)) if scored else None
    if loss_pnl < 0:
        pf_val: float | str | None = win_pnl / abs(loss_pnl)
    elif win_pnl > 0:
        pf_val = "inf"
    else:
        pf_val = None
    pnls = [t["pnl_usd"] for t in trades]
    rois = [t["roi_pct"] for t in trades if t["position_usd"]]
    avg_win = (win_pnl / len(wins)) if wins else 0.0
    avg_loss = (loss_pnl / len(losses)) if losses else 0.0  # loss_pnl is negative already
    # Expectancy: E[trade PnL] under observed win rate
    expectancy = (
        win_rate * avg_win + (1 - win_rate) * avg_loss
        if win_rate is not None else None
    )
    hold_avg = _avg_hold_hours(trades)
    sortino = _sortino(pnls)
    sharpe = _sharpe(rois) if rois else None
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "total_pnl_usd": round(total_pnl, 2),
        "avg_pnl_usd": round(total_pnl / len(trades), 2),
        "best": round(max(pnls), 2),
        "worst": round(min(pnls), 2),
        "profit_factor": (round(pf_val, 2) if isinstance(pf_val, float) else pf_val),
        "sortino": round(sortino, 3) if sortino is not None else None,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "avg_roi_pct": round(sum(rois) / len(rois), 3) if rois else None,
        "total_position_usd": round(total_position, 2),
        "portfolio_roi_pct": round(total_pnl / total_position * 100, 3) if total_position else None,
        "avg_hold_hours": round(hold_avg, 2) if hold_avg is not None else None,
        "expectancy_usd": round(expectancy, 2) if expectancy is not None else None,
    }


def report(trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Full strategy performance report.

    Returns:
      {
        overall: {...},
        by_strategy: {name: {...}},
        by_timeframe: {bucket: {...}},
        by_strategy_timeframe: {strategy: {bucket: {...}}},
        by_symbol: {symbol: {...}},
        trade_count: int,
        strategies: [names],
        timeframes: [bucket names],
        generated_at: iso8601,
      }
    """
    if trades is None:
        trades = load_all_trades()
    try:
        from datetime import UTC
    except ImportError:
        from datetime import timezone
        UTC = timezone.utc

    now_iso = datetime.now(UTC).isoformat()

    if not trades:
        return {
            "overall": _stats_for([]),
            "by_strategy": {},
            "by_timeframe": {},
            "by_strategy_timeframe": {},
            "by_symbol": {},
            "trade_count": 0,
            "strategies": [],
            "timeframes": TIMEFRAME_ORDER,
            "generated_at": now_iso,
            "note": "No closed trades recorded yet. Tracking starts on first signal close.",
        }

    overall = _stats_for(trades)

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "strategy": defaultdict(list),
        "timeframe": defaultdict(list),
        "symbol": defaultdict(list),
    }
    strat_tf: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for t in trades:
        grouped["strategy"][t["strategy"]].append(t)
        grouped["timeframe"][t["timeframe"]].append(t)
        grouped["symbol"][t["symbol"]].append(t)
        strat_tf[(t["strategy"], t["timeframe"])].append(t)

    by_strategy = {k: _stats_for(v) for k, v in grouped["strategy"].items()}
    by_tf = {k: _stats_for(v) for k, v in grouped["timeframe"].items()}
    by_symbol = {k: _stats_for(v) for k, v in grouped["symbol"].items()}

    by_strategy_timeframe: dict[str, dict[str, dict[str, Any]]] = {}
    for (strat, tf), ts in strat_tf.items():
        by_strategy_timeframe.setdefault(strat, {})[tf] = _stats_for(ts)

    return {
        "overall": overall,
        "by_strategy": by_strategy,
        "by_timeframe": by_tf,
        "by_strategy_timeframe": by_strategy_timeframe,
        "by_symbol": by_symbol,
        "trade_count": len(trades),
        "strategies": sorted(by_strategy.keys()),
        "timeframes": TIMEFRAME_ORDER,
        "generated_at": now_iso,
    }


_DEFAULT_INITIAL_CAPITAL = 100_000.0


def _initial_capital() -> float:
    """Read initial_capital from paper_portfolio.json if available."""
    if not PAPER_PORTFOLIO.exists():
        return _DEFAULT_INITIAL_CAPITAL
    try:
        d = json.loads(PAPER_PORTFOLIO.read_text())
    except (OSError, json.JSONDecodeError):
        return _DEFAULT_INITIAL_CAPITAL
    return float(d.get("initial_capital") or _DEFAULT_INITIAL_CAPITAL)


def timeseries(
    trades: list[dict[str, Any]] | None = None,
    initial_capital: float | None = None,
) -> dict[str, Any]:
    """Compute equity curve, drawdown series, and monthly returns from closed trades.

    Returns:
      {
        initial_capital, final_equity, total_pnl_usd, total_return_pct,
        equity_curve: [{ts, equity_usd, pnl_usd}],
        drawdown_series: [{ts, dd_pct, equity_usd}],
        max_drawdown: {pct, ts, equity_usd},
        monthly_returns: [{year, month, pnl_usd, return_pct, trades}],
        trade_count: int,
      }

    All series are sorted by closed_at ASC. Trades missing closed_at are skipped.
    """
    if trades is None:
        trades = load_all_trades()
    capital = initial_capital if initial_capital is not None else _initial_capital()

    closed = []
    for t in trades:
        ts = _parse_iso(t.get("closed_at"))
        if ts is None:
            continue
        closed.append((ts, t))
    closed.sort(key=lambda x: x[0])

    if not closed:
        return {
            "initial_capital": capital,
            "final_equity": capital,
            "total_pnl_usd": 0.0,
            "total_return_pct": 0.0,
            "equity_curve": [],
            "drawdown_series": [],
            "max_drawdown": {"pct": 0.0, "ts": None, "equity_usd": capital},
            "monthly_returns": [],
            "trade_count": 0,
        }

    equity_curve: list[dict[str, Any]] = []
    drawdown_series: list[dict[str, Any]] = []
    running = capital
    peak = capital
    max_dd = {"pct": 0.0, "ts": None, "equity_usd": capital}

    for ts, t in closed:
        running += t["pnl_usd"]
        if running > peak:
            peak = running
        dd_pct = (running - peak) / peak if peak > 0 else 0.0
        ts_iso = ts.isoformat()
        equity_curve.append({
            "ts": ts_iso,
            "equity_usd": round(running, 2),
            "pnl_usd": round(t["pnl_usd"], 2),
        })
        drawdown_series.append({
            "ts": ts_iso,
            "dd_pct": round(dd_pct, 6),
            "equity_usd": round(running, 2),
        })
        if dd_pct < max_dd["pct"]:
            max_dd = {"pct": round(dd_pct, 6), "ts": ts_iso, "equity_usd": round(running, 2)}

    monthly_bucket: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"pnl_usd": 0.0, "trades": 0, "equity_at_start": capital}
    )
    # Track equity at the start of each month (for return %)
    running_before = capital
    current_key: tuple[int, int] | None = None
    for ts, t in closed:
        key = (ts.year, ts.month)
        if key != current_key:
            monthly_bucket[key]["equity_at_start"] = running_before
            current_key = key
        monthly_bucket[key]["pnl_usd"] += t["pnl_usd"]
        monthly_bucket[key]["trades"] += 1
        running_before += t["pnl_usd"]

    monthly_returns = []
    for (year, month), v in sorted(monthly_bucket.items()):
        start_eq = v["equity_at_start"]
        ret_pct = (v["pnl_usd"] / start_eq * 100) if start_eq > 0 else 0.0
        monthly_returns.append({
            "year": year,
            "month": month,
            "pnl_usd": round(v["pnl_usd"], 2),
            "return_pct": round(ret_pct, 3),
            "trades": v["trades"],
        })

    total_pnl = running - capital
    return {
        "initial_capital": capital,
        "final_equity": round(running, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "total_return_pct": round(total_pnl / capital * 100, 3) if capital else 0.0,
        "equity_curve": equity_curve,
        "drawdown_series": drawdown_series,
        "max_drawdown": max_dd,
        "monthly_returns": monthly_returns,
        "trade_count": len(closed),
    }


if __name__ == "__main__":
    import sys
    json.dump(report(), sys.stdout, indent=2, default=str)
    print()
