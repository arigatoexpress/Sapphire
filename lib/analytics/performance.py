"""Performance analytics — numbers behind the /analytics dashboard.

Aggregates closed trades from data/signals/*.jsonl and data/paper_trading.jsonl
and computes:

  - equity_curve       vs BTC buy-and-hold benchmark
  - rolling_sharpe     30-trade window
  - signal_quality     (confidence_at_entry, pnl_usd) pairs for scatter
  - regime_breakdown   win rate + avg PnL per regime
  - best_trades        top 5 / bottom 5 by absolute PnL
  - monthly_returns    by-month % return on starting bankroll
  - kelly_over_time    rolling quarter-Kelly fraction (30-trade window)

All views are computed from the same closed-trade stream so numbers
tie out with /risk.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SIGNALS_DIR = ROOT / "data" / "signals"
PAPER_LOG = ROOT / "data" / "paper_trading.jsonl"

ROLLING_WINDOW = 30
TRADING_DAYS = 365


# ---------------------------------------------------------------------------
# Loader (mirrors RiskEngine._load_trades so metrics stay consistent)
# ---------------------------------------------------------------------------


def _load_trades() -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []

    if PAPER_LOG.exists():
        for line in PAPER_LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            outcome = r.get("paper_outcome")
            if outcome in {"win", "loss", "break_even"}:
                trades.append({
                    "timestamp": r.get("closed_at") or r.get("timestamp", ""),
                    "symbol": r.get("symbol", "?"),
                    "direction": r.get("direction", "?"),
                    "outcome": outcome,
                    "pnl_usd": float(r.get("paper_pnl_usd") or 0.0),
                    "confidence": float(r.get("confidence") or 0.0),
                    "regime": r.get("regime") or "UNKNOWN",
                    "position_usd": float(r.get("position_usd") or 0.0),
                })

    files = sorted(SIGNALS_DIR.glob("*.jsonl")) if SIGNALS_DIR.exists() else []
    for f in files:
        try:
            content = f.read_text()
        except OSError:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            outcome = r.get("outcome")
            if outcome in {"win", "loss", "break_even"}:
                trades.append({
                    "timestamp": r.get("closed_at") or r.get("timestamp", ""),
                    "symbol": r.get("symbol", "?"),
                    "direction": r.get("direction", "?"),
                    "outcome": outcome,
                    "pnl_usd": float(r.get("pnl_usd") or 0.0),
                    "confidence": float(r.get("confidence") or 0.0),
                    "regime": r.get("regime") or "UNKNOWN",
                    "position_usd": float(r.get("position_usd") or 0.0),
                })

    def _ts_key(t: dict) -> datetime:
        raw = t.get("timestamp") or ""
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    trades.sort(key=_ts_key)
    return trades


# ---------------------------------------------------------------------------
# BTC benchmark (buy-and-hold return over the trade history span)
# ---------------------------------------------------------------------------


def _btc_benchmark_curve(trades: list[dict], bankroll: float) -> list[dict]:
    """Build a BTC hodl equity curve aligned to trade timestamps.

    Tries yfinance; on failure returns an empty list so the UI can fall back
    to showing the strategy curve alone.
    """
    if not trades:
        return []
    try:
        import yfinance as yf  # type: ignore
        first = trades[0]["timestamp"]
        last = trades[-1]["timestamp"]
        if not first or not last:
            return []
        start = datetime.fromisoformat(first.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        end = datetime.fromisoformat(last.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        # Need at least 2 days of data
        hist = yf.Ticker("BTC-USD").history(start=start, end=end, interval="1d")
        if hist.empty or len(hist) < 2:
            return []
        first_price = float(hist.iloc[0]["Close"])
        curve = []
        for idx, row in hist.iterrows():
            price = float(row["Close"])
            equity = bankroll * (price / first_price)
            curve.append({
                "timestamp": idx.strftime("%Y-%m-%d"),
                "equity_usd": round(equity, 2),
            })
        return curve
    except Exception as e:
        log.debug("btc benchmark fetch failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Rolling Sharpe
# ---------------------------------------------------------------------------


def _rolling_sharpe(trades: list[dict], bankroll: float, window: int = ROLLING_WINDOW) -> list[dict]:
    if len(trades) < window:
        return []
    out = []
    for i in range(window - 1, len(trades)):
        w = trades[i - window + 1 : i + 1]
        rets = [t["pnl_usd"] / bankroll for t in w]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std <= 0:
            continue
        sharpe = (mean / std) * math.sqrt(TRADING_DAYS)
        out.append({
            "timestamp": w[-1]["timestamp"],
            "sharpe": round(sharpe, 3),
        })
    return out


# ---------------------------------------------------------------------------
# Kelly over time
# ---------------------------------------------------------------------------


def _rolling_kelly(trades: list[dict], window: int = ROLLING_WINDOW) -> list[dict]:
    if len(trades) < window:
        return []
    out = []
    for i in range(window - 1, len(trades)):
        w = trades[i - window + 1 : i + 1]
        wins = [t for t in w if t["outcome"] == "win"]
        losses = [t for t in w if t["outcome"] == "loss"]
        decisive = len(wins) + len(losses)
        if decisive < 5:
            continue
        wr = len(wins) / decisive
        avg_win = sum(t["pnl_usd"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(abs(t["pnl_usd"]) for t in losses) / len(losses) if losses else 0.0
        if avg_loss <= 0:
            continue
        rr = avg_win / avg_loss
        if rr <= 0:
            continue
        kelly = wr - (1.0 - wr) / rr
        quarter = max(0.0, min(0.25, kelly * 0.25))
        out.append({
            "timestamp": w[-1]["timestamp"],
            "kelly_quarter": round(quarter, 4),
            "kelly_raw": round(max(0.0, kelly), 4),
        })
    return out


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------


def _regime_breakdown(trades: list[dict]) -> dict[str, dict[str, Any]]:
    bucket: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        bucket[t.get("regime") or "UNKNOWN"].append(t)
    out: dict[str, dict[str, Any]] = {}
    for regime, ts in bucket.items():
        wins = sum(1 for t in ts if t["outcome"] == "win")
        losses = sum(1 for t in ts if t["outcome"] == "loss")
        decisive = wins + losses
        out[regime] = {
            "trades": len(ts),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / decisive, 3) if decisive > 0 else None,
            "total_pnl_usd": round(sum(t["pnl_usd"] for t in ts), 2),
            "avg_pnl_usd": round(sum(t["pnl_usd"] for t in ts) / len(ts), 2) if ts else 0.0,
        }
    return out


# ---------------------------------------------------------------------------
# Monthly heatmap
# ---------------------------------------------------------------------------


def _monthly_returns(trades: list[dict], bankroll: float) -> list[dict]:
    by_month: dict[str, float] = defaultdict(float)
    for t in trades:
        ts = t.get("timestamp") or ""
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        key = dt.strftime("%Y-%m")
        by_month[key] += t["pnl_usd"]
    return [
        {
            "month": m,
            "pnl_usd": round(v, 2),
            "pct": round(v / bankroll, 4),
        }
        for m, v in sorted(by_month.items())
    ]


# ---------------------------------------------------------------------------
# Best / worst trades
# ---------------------------------------------------------------------------


def _extreme_trades(trades: list[dict], n: int = 5) -> dict[str, list[dict]]:
    sorted_trades = sorted(trades, key=lambda t: t["pnl_usd"])
    return {
        "worst": sorted_trades[:n],
        "best": list(reversed(sorted_trades[-n:])),
    }


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def compute_performance(bankroll: float = 10_000.0) -> dict[str, Any]:
    trades = _load_trades()
    equity = bankroll
    equity_curve = []
    for t in trades:
        equity = round(equity + t["pnl_usd"], 2)
        equity_curve.append({
            "timestamp": t["timestamp"],
            "equity_usd": equity,
        })

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "trades": len(trades),
        "bankroll": bankroll,
        "final_equity": equity,
        "equity_curve": equity_curve,
        "btc_benchmark": _btc_benchmark_curve(trades, bankroll),
        "rolling_sharpe": _rolling_sharpe(trades, bankroll),
        "kelly_over_time": _rolling_kelly(trades),
        "regime_breakdown": _regime_breakdown(trades),
        "monthly_returns": _monthly_returns(trades, bankroll),
        "signal_quality": [
            {
                "confidence": round(t["confidence"], 3),
                "pnl_usd": round(t["pnl_usd"], 2),
                "outcome": t["outcome"],
                "symbol": t["symbol"],
                "timestamp": t["timestamp"],
            }
            for t in trades if t.get("confidence")
        ],
        "extremes": _extreme_trades(trades),
    }


DEFAULT_BACKTEST_FILE = Path("data/backtests/latest.json")


def build_performance_report(
    backtest_path: "Path | None" = None,
    *,
    primary_symbol: str = "BTC-USD",
    rolling_window: int = 30,
) -> "dict[str, Any]":
    """Build the /analytics-page payload from a backtest latest.json.

    Falls back to live paper-trading data via compute_performance if no
    backtest file is available.
    """
    path = backtest_path or DEFAULT_BACKTEST_FILE
    if not path.exists():
        return compute_performance()

    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"backtest unreadable: {e}"}

    with_r = data.get("with_regime") or {}
    without_r = data.get("without_regime") or {}
    symbols = sorted(with_r.keys())

    primary = with_r.get(primary_symbol) or (with_r.get(symbols[0]) if symbols else None) or {}
    equity = [(d, v) for d, v in (primary.get("equity_curve") or [])]
    bench = [(d, v) for d, v in (primary.get("benchmark_curve") or [])]

    equity_off: list = []
    if primary_symbol in without_r:
        equity_off = [(d, v) for d, v in (without_r[primary_symbol].get("equity_curve") or [])]

    all_trades: list[dict] = []
    for sym, res in with_r.items():
        if isinstance(res, dict):
            for t in res.get("trades") or []:
                t = dict(t)
                t.setdefault("symbol", sym)
                all_trades.append(t)

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "primary_symbol": primary_symbol,
        "equity_curve": [{"timestamp": d, "equity_usd": v} for d, v in equity],
        "benchmark_curve": [{"timestamp": d, "equity_usd": v} for d, v in bench],
        "equity_curve_off": [{"timestamp": d, "equity_usd": v} for d, v in equity_off],
        "summary_rows": [
            {
                "symbol": sym,
                "with_regime": {k: with_r.get(sym, {}).get(k) for k in (
                    "total_return_pct", "sharpe", "sortino", "max_drawdown_pct", "win_rate",
                )},
                "without_regime": {k: without_r.get(sym, {}).get(k) for k in (
                    "total_return_pct", "sharpe", "sortino", "max_drawdown_pct", "win_rate",
                )},
            }
            for sym in symbols if "error" not in with_r.get(sym, {})
        ],
        "signal_quality": [
            {
                "symbol": t.get("symbol"),
                "confidence": round(float(t.get("confidence", 0)), 3),
                "pnl_pct": round(float(t.get("pnl_pct", 0)), 3),
                "regime": t.get("regime", "UNKNOWN"),
            }
            for t in all_trades
        ],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = compute_performance()
    print(json.dumps({k: v if k in {"trades", "bankroll", "final_equity", "run_at"} else f"<len={len(v)}>"
                      for k, v in out.items()}, indent=2, default=str))
