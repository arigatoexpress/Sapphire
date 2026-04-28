"""Performance analytics — closed-trade + signal metrics for /analytics page.

Loads real data from:
  - data/paper_portfolio.json        (closed trade history)
  - data/signals/YYYY-MM-DD.jsonl    (scored signals + outcomes)
  - data/trading_signals.jsonl       (legacy raw signal log)

Produces a single JSON-serializable report used by the Flask route and the
self-optimization loop:

  {
    "equity_curve":   [{t, equity}, ...],
    "btc_benchmark":  [{t, equity}, ...],
    "rolling_sharpe": [{t, sharpe}, ...],   # 30-day rolling
    "scatter":        [{confidence, pnl_pct, outcome, symbol}, ...],
    "regime_perf":    {RISK_ON: {trades, win_rate, pnl}, ...},
    "best_trades":    [...],
    "worst_trades":   [...],
    "monthly_returns": [{year, month, pct, pnl, trades}, ...],
    "summary":        {total_trades, total_pnl, win_rate, sharpe, ...},
  }

Everything is computed from on-disk data — no external calls. If a data
source is missing, the corresponding block is empty but the shape stays
stable so the template can render "no data" panels gracefully.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

SAPPHIRE_ROOT = Path(__file__).resolve().parents[2]

PORTFOLIO_FILE = SAPPHIRE_ROOT / "data" / "paper_portfolio.json"
SIGNALS_DIR = SAPPHIRE_ROOT / "data" / "signals"
LEGACY_SIGNALS = SAPPHIRE_ROOT / "data" / "trading_signals.jsonl"

INITIAL_CAPITAL = 100_000.0
ROLLING_WINDOW_DAYS = 30
TRADING_DAYS_PER_YEAR = 365


@dataclass
class Trade:
    """Unified closed-trade record."""

    opened_at: str
    closed_at: str
    symbol: str
    side: str  # BUY | SELL
    entry_price: float
    exit_price: float
    qty: float
    size_usd: float
    pnl: float
    confidence: float
    exit_reason: str
    regime: str = "UNKNOWN"
    source: str = "paper"
    enhancer_flags: list[str] = field(default_factory=list)

    @property
    def pnl_pct(self) -> float:
        if self.entry_price > 0 and self.qty > 0:
            if self.side.upper() == "BUY":
                return (self.exit_price - self.entry_price) / self.entry_price
            return (self.entry_price - self.exit_price) / self.entry_price
        return 0.0

    @property
    def closed_dt(self) -> datetime | None:
        return _parse_ts(self.closed_at)


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _load_closed_trades() -> list[Trade]:
    """Unify closed trades from paper_portfolio.json history + signal outcomes."""
    trades: list[Trade] = []

    # Paper portfolio history (authoritative for paper_trader exits)
    if PORTFOLIO_FILE.exists():
        try:
            pf = json.loads(PORTFOLIO_FILE.read_text())
            for t in pf.get("history") or []:
                entry = float(t.get("entry_price") or 0.0)
                exit_p = float(t.get("exit_price") or 0.0)
                qty = float(t.get("qty") or 0.0)
                trades.append(
                    Trade(
                        opened_at=str(t.get("opened_at") or ""),
                        closed_at=str(t.get("closed_at") or ""),
                        symbol=str(t.get("symbol") or "?"),
                        side=str(t.get("side") or "BUY").upper(),
                        entry_price=entry,
                        exit_price=exit_p,
                        qty=qty,
                        size_usd=float(t.get("size_usd") or entry * qty),
                        pnl=float(t.get("pnl") or 0.0),
                        confidence=float(t.get("confidence") or 0.0),
                        exit_reason=str(t.get("exit_reason") or "?"),
                        source="paper",
                    )
                )
        except (OSError, json.JSONDecodeError):
            pass

    # Signal audit outcomes — closed signals from the pipeline JSONL
    if SIGNALS_DIR.exists():
        for f in sorted(SIGNALS_DIR.glob("*.jsonl")):
            try:
                for line in f.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get("outcome") not in {"win", "loss", "break_even"}:
                        continue
                    entry = float(r.get("price") or 0.0)
                    exit_p = float(r.get("close_price") or 0.0)
                    pnl = float(r.get("pnl_usd") or 0.0)
                    trades.append(
                        Trade(
                            opened_at=str(r.get("timestamp") or ""),
                            closed_at=str(r.get("closed_at") or ""),
                            symbol=str(r.get("symbol") or "?"),
                            side=(
                                "BUY" if str(r.get("direction") or "").lower() == "long" else "SELL"
                            ),
                            entry_price=entry,
                            exit_price=exit_p,
                            qty=(float(r.get("position_usd") or 0.0) / entry) if entry > 0 else 0.0,
                            size_usd=float(r.get("position_usd") or 0.0),
                            pnl=pnl,
                            confidence=float(
                                r.get("confidence") or r.get("original_confidence") or 0.0
                            ),
                            exit_reason=str(r.get("exit_reason") or "signal_close"),
                            regime=str(r.get("regime") or "UNKNOWN"),
                            source="signals",
                            enhancer_flags=list(r.get("enhancer_flags") or []),
                        )
                    )
            except OSError:
                continue

    # Sort chronologically by close timestamp (fallback to open)
    def _sort_key(t: Trade) -> datetime:
        return t.closed_dt or _parse_ts(t.opened_at) or datetime.min.replace(tzinfo=UTC)

    trades.sort(key=_sort_key)
    return trades


def _collect_btc_prices() -> list[tuple[datetime, float]]:
    """Collect (timestamp, BTC_price) pairs from all available signal/trade records.

    These are used as sparse sample points to render the BTC buy-and-hold
    benchmark — no network calls needed. If two points share the same
    timestamp we keep the later price seen.
    """
    prices: dict[datetime, float] = {}

    # From trading_signals.jsonl
    if LEGACY_SIGNALS.exists():
        try:
            for line in LEGACY_SIGNALS.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "BTC" not in str(r.get("symbol") or "").upper():
                    continue
                price = float(r.get("price") or 0.0)
                ts = _parse_ts(r.get("timestamp") or "")
                if ts and price > 0:
                    prices[ts] = price
        except OSError:
            pass

    # From signals/ audit (entry + close)
    if SIGNALS_DIR.exists():
        for f in sorted(SIGNALS_DIR.glob("*.jsonl")):
            try:
                for line in f.read_text().splitlines():
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "BTC" not in str(r.get("symbol") or "").upper():
                        continue
                    ts = _parse_ts(r.get("timestamp") or "")
                    price = float(r.get("price") or 0.0)
                    if ts and price > 0:
                        prices[ts] = price
                    # Also capture close price
                    close_ts = _parse_ts(r.get("closed_at") or "")
                    close_p = float(r.get("close_price") or 0.0)
                    if close_ts and close_p > 0:
                        prices[close_ts] = close_p
            except OSError:
                continue

    # From portfolio history (exits for BTC)
    if PORTFOLIO_FILE.exists():
        try:
            pf = json.loads(PORTFOLIO_FILE.read_text())
            for t in pf.get("history") or []:
                if "BTC" not in str(t.get("symbol") or "").upper():
                    continue
                open_ts = _parse_ts(t.get("opened_at") or "")
                close_ts = _parse_ts(t.get("closed_at") or "")
                entry = float(t.get("entry_price") or 0.0)
                exit_p = float(t.get("exit_price") or 0.0)
                if open_ts and entry > 0:
                    prices[open_ts] = entry
                if close_ts and exit_p > 0:
                    prices[close_ts] = exit_p
            # Open BTC positions — use entry at opened_at
            for p in pf.get("positions") or []:
                if "BTC" not in str(p.get("symbol") or "").upper():
                    continue
                ts = _parse_ts(p.get("opened_at") or "")
                entry = float(p.get("entry_price") or 0.0)
                if ts and entry > 0:
                    prices[ts] = entry
        except (OSError, json.JSONDecodeError):
            pass

    return sorted(prices.items())


def _btc_price_at(samples: list[tuple[datetime, float]], t: datetime) -> float | None:
    """Nearest-neighbour lookup against sparse BTC samples."""
    if not samples:
        return None
    # Use the most recent sample at or before t; fall back to earliest future.
    prior = None
    for ts, price in samples:
        if ts <= t:
            prior = price
        else:
            break
    if prior is not None:
        return prior
    return samples[0][1]


def _equity_curve(trades: list[Trade]) -> list[dict]:
    equity = INITIAL_CAPITAL
    curve = [{"t": None, "equity": round(equity, 2)}]
    for tr in trades:
        equity += tr.pnl
        curve.append(
            {
                "t": tr.closed_at or tr.opened_at,
                "equity": round(equity, 2),
                "pnl": round(tr.pnl, 2),
                "symbol": tr.symbol,
            }
        )
    return curve


def _btc_benchmark(trades: list[Trade]) -> list[dict]:
    """BTC buy-and-hold with INITIAL_CAPITAL invested at the first trade's timestamp."""
    samples = _collect_btc_prices()
    if not samples or not trades:
        return []

    # Anchor at the earliest trade timestamp (or first BTC sample, whichever is earlier)
    first_trade_ts = _parse_ts(trades[0].opened_at) or _parse_ts(trades[0].closed_at)
    if first_trade_ts is None:
        first_trade_ts = samples[0][0]

    entry_btc = _btc_price_at(samples, first_trade_ts)
    if not entry_btc:
        return []
    btc_qty = INITIAL_CAPITAL / entry_btc

    out = [{"t": first_trade_ts.isoformat(), "equity": round(INITIAL_CAPITAL, 2)}]
    for tr in trades:
        ts = tr.closed_dt or _parse_ts(tr.opened_at)
        if ts is None:
            continue
        price = _btc_price_at(samples, ts)
        if price is None:
            continue
        out.append(
            {
                "t": tr.closed_at or tr.opened_at,
                "equity": round(btc_qty * price, 2),
                "btc_price": round(price, 2),
            }
        )
    return out


def _rolling_sharpe(trades: list[Trade], window_days: int = ROLLING_WINDOW_DAYS) -> list[dict]:
    """30-day rolling Sharpe ratio on daily PnL %.

    Uses per-trade pnl normalised to bankroll (INITIAL_CAPITAL) aggregated by
    UTC calendar day. Sharpe is annualised with sqrt(365). Points are only
    emitted once ``window_days`` of data is available so the series doesn't
    visually jump at the start.
    """
    if len(trades) < 2:
        return []

    # Aggregate daily returns
    daily: dict[str, float] = defaultdict(float)
    for tr in trades:
        dt = tr.closed_dt or _parse_ts(tr.opened_at)
        if not dt:
            continue
        day = dt.astimezone(UTC).date().isoformat()
        daily[day] += tr.pnl

    # Fill every day in the span so the window slides at a constant rate
    days_sorted = sorted(daily.keys())
    if not days_sorted:
        return []
    first = datetime.fromisoformat(days_sorted[0]).replace(tzinfo=UTC).date()
    last = datetime.fromisoformat(days_sorted[-1]).replace(tzinfo=UTC).date()
    all_days: list[tuple[str, float]] = []
    cur = first
    while cur <= last:
        k = cur.isoformat()
        all_days.append((k, daily.get(k, 0.0)))
        cur += timedelta(days=1)

    returns = [pnl / INITIAL_CAPITAL for _, pnl in all_days]
    annualise = math.sqrt(TRADING_DAYS_PER_YEAR)

    out: list[dict] = []
    for i in range(window_days - 1, len(returns)):
        window = returns[i - window_days + 1 : i + 1]
        n = len(window)
        mean = sum(window) / n
        var = sum((r - mean) ** 2 for r in window) / (n - 1) if n > 1 else 0.0
        std = math.sqrt(var)
        sharpe = (mean / std) * annualise if std > 0 else 0.0
        out.append(
            {
                "t": all_days[i][0],
                "sharpe": round(sharpe, 3),
            }
        )
    return out


def _signal_scatter(trades: list[Trade]) -> list[dict]:
    """Confidence at entry vs realised PnL% — coloured by outcome."""
    out: list[dict] = []
    for tr in trades:
        if tr.confidence <= 0:
            continue
        outcome = "win" if tr.pnl > 0 else ("loss" if tr.pnl < 0 else "break_even")
        out.append(
            {
                "confidence": round(tr.confidence, 3),
                "pnl_pct": round(tr.pnl_pct * 100, 3),
                "pnl_usd": round(tr.pnl, 2),
                "outcome": outcome,
                "symbol": tr.symbol,
                "t": tr.closed_at,
            }
        )
    return out


def _regime_perf(trades: list[Trade]) -> dict[str, dict]:
    """Aggregate PnL + win rate by market regime at signal time."""
    groups: dict[str, list[Trade]] = defaultdict(list)
    for tr in trades:
        regime = (tr.regime or "UNKNOWN").upper()
        if regime not in {"RISK_ON", "RISK_OFF", "TRANSITION", "UNKNOWN"}:
            regime = "UNKNOWN"
        groups[regime].append(tr)

    out: dict[str, dict] = {}
    for regime in ("RISK_ON", "RISK_OFF", "TRANSITION", "UNKNOWN"):
        bucket = groups.get(regime, [])
        wins = sum(1 for t in bucket if t.pnl > 0)
        losses = sum(1 for t in bucket if t.pnl < 0)
        decisive = wins + losses
        pnl = round(sum(t.pnl for t in bucket), 2)
        out[regime] = {
            "trades": len(bucket),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / decisive, 3) if decisive else None,
            "pnl_usd": pnl,
            "avg_pnl": round(pnl / len(bucket), 2) if bucket else 0.0,
        }
    return out


def _best_worst(trades: list[Trade], k: int = 5) -> tuple[list[dict], list[dict]]:
    def _row(t: Trade) -> dict:
        return {
            "symbol": t.symbol,
            "side": t.side,
            "entry_price": round(t.entry_price, 4),
            "exit_price": round(t.exit_price, 4),
            "pnl_usd": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct * 100, 3),
            "confidence": round(t.confidence, 3),
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "exit_reason": t.exit_reason,
            "regime": t.regime,
        }

    decisive = [t for t in trades if t.pnl != 0]
    best = sorted(decisive, key=lambda t: t.pnl, reverse=True)[:k]
    worst = sorted(decisive, key=lambda t: t.pnl)[:k]
    return [_row(t) for t in best], [_row(t) for t in worst]


def _monthly_returns(trades: list[Trade]) -> list[dict]:
    """Monthly PnL aggregated for the calendar heatmap."""
    buckets: dict[tuple[int, int], dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for tr in trades:
        dt = tr.closed_dt or _parse_ts(tr.opened_at)
        if not dt:
            continue
        dt = dt.astimezone(UTC)
        key = (dt.year, dt.month)
        b = buckets[key]
        b["pnl"] += tr.pnl
        b["trades"] += 1
        if tr.pnl > 0:
            b["wins"] += 1

    out = []
    for (yr, mo), b in sorted(buckets.items()):
        out.append(
            {
                "year": yr,
                "month": mo,
                "pnl": round(b["pnl"], 2),
                "pct": round(b["pnl"] / INITIAL_CAPITAL * 100, 3),
                "trades": b["trades"],
                "wins": b["wins"],
            }
        )
    return out


def _summary(trades: list[Trade], equity: list[dict], btc: list[dict]) -> dict:
    """Headline KPIs for the page hero row."""
    n = len(trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    losses = sum(1 for t in trades if t.pnl < 0)
    decisive = wins + losses
    total_pnl = round(sum(t.pnl for t in trades), 2)
    final_equity = equity[-1]["equity"] if equity else INITIAL_CAPITAL

    return_pct = (
        ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100) if INITIAL_CAPITAL else 0.0
    )

    btc_final = btc[-1]["equity"] if btc else None
    btc_return_pct = None
    if btc_final is not None:
        btc_return_pct = round((btc_final - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 3)

    return {
        "total_trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / decisive, 3) if decisive else None,
        "total_pnl_usd": total_pnl,
        "return_pct": round(return_pct, 3),
        "final_equity_usd": round(final_equity, 2),
        "btc_return_pct": btc_return_pct,
        "alpha_pct": round(return_pct - btc_return_pct, 3) if btc_return_pct is not None else None,
    }


def build_report() -> dict:
    """Assemble the full analytics payload."""
    trades = _load_closed_trades()
    equity = _equity_curve(trades)
    btc = _btc_benchmark(trades)
    best, worst = _best_worst(trades)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "equity_curve": equity,
        "btc_benchmark": btc,
        "rolling_sharpe": _rolling_sharpe(trades),
        "scatter": _signal_scatter(trades),
        "regime_perf": _regime_perf(trades),
        "best_trades": best,
        "worst_trades": worst,
        "monthly_returns": _monthly_returns(trades),
        "summary": _summary(trades, equity, btc),
        "trade_count": len(trades),
    }


if __name__ == "__main__":
    report = build_report()
    print(json.dumps(report, indent=2, default=str))
