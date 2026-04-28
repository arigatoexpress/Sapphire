"""Backtesting engine — replays signals through the scoring pipeline on historical OHLCV.

Inputs: yfinance-fetched OHLCV (default 90d daily bars) + a signal-generator callback.
Pipeline: for each bar → generator yields raw signal dicts → SignalPipeline.process() scores
them → an OHLCV exit simulator closes at TP/SL/end-of-window → trades + equity curve.
Outputs: Sharpe, Sortino, max drawdown, win rate, profit factor, Calmar, CAGR, per-trade rows.

yfinance is used directly (not via OpenBB REST) so backtests run offline without the
OpenBB service. Falls back to a deterministic synthetic series if yfinance is unavailable.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Trade:
    symbol: str
    direction: str  # "long" | "short"
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    size_usd: float
    pnl_usd: float
    pnl_pct: float
    hold_bars: int
    exit_reason: str  # "take_profit" | "stop_loss" | "end_of_window" | "signal_flip"
    confidence: float = 0.0
    score: float = 0.0


@dataclass
class BacktestResult:
    symbol: str
    start: str
    end: str
    bars: int
    trades: list[Trade]
    initial_capital: float
    final_capital: float
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    calmar: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trades"] = [asdict(t) for t in self.trades]
        return d


def fetch_ohlcv(
    symbol: str,
    days: int = 90,
    interval: str = "1d",
) -> list[Bar]:
    """Fetch daily OHLCV bars via yfinance. Returns [] on failure."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        log.warning("yfinance not installed — returning synthetic series")
        return _synthetic_bars(symbol, days)

    end = datetime.now(UTC)
    start = end - timedelta(days=days + 5)  # small overshoot in case of missing bars
    try:
        df = yf.download(
            symbol,
            start=start.date(),
            end=end.date(),
            interval=interval,
            progress=False,
            auto_adjust=False,
        )
    except Exception as e:
        log.warning("yfinance fetch failed for %s: %s — using synthetic", symbol, e)
        return _synthetic_bars(symbol, days)

    if df is None or df.empty:
        log.warning("yfinance returned empty for %s — using synthetic", symbol)
        return _synthetic_bars(symbol, days)

    def _get(row, col: str) -> float:
        v = row[col]
        try:
            return float(v.iloc[0]) if hasattr(v, "iloc") else float(v)
        except (TypeError, ValueError):
            return 0.0

    bars: list[Bar] = []
    for idx, row in df.iterrows():
        ts = (
            idx.to_pydatetime()
            if hasattr(idx, "to_pydatetime")
            else datetime.fromisoformat(str(idx))
        )
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        bars.append(
            Bar(
                ts=ts,
                open=_get(row, "Open"),
                high=_get(row, "High"),
                low=_get(row, "Low"),
                close=_get(row, "Close"),
                volume=_get(row, "Volume"),
            )
        )
    return bars[-days:] if len(bars) > days else bars


def _synthetic_bars(symbol: str, days: int) -> list[Bar]:
    """Deterministic synthetic OHLCV for offline/CI runs. Seeded by symbol."""
    import random

    rng = random.Random(hash(symbol) & 0xFFFFFFFF)
    price = 100.0
    bars: list[Bar] = []
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days):
        ts = now - timedelta(days=days - i - 1)
        drift = 0.0004  # slight upward bias so backtests have something to grip
        shock = rng.gauss(0, 0.02)
        price_next = max(1.0, price * (1 + drift + shock))
        hi = max(price, price_next) * (1 + abs(rng.gauss(0, 0.004)))
        lo = min(price, price_next) * (1 - abs(rng.gauss(0, 0.004)))
        bars.append(
            Bar(
                ts=ts,
                open=price,
                high=hi,
                low=lo,
                close=price_next,
                volume=1_000_000 * (1 + rng.random()),
            )
        )
        price = price_next
    return bars


# ── Metrics ────────────────────────────────────────────────────────────────


def _returns_from_equity(equity: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev == 0:
            continue
        out.append((equity[i] - prev) / prev)
    return out


def sharpe_ratio(returns: list[float], periods_per_year: int = 252, rf: float = 0.0) -> float:
    """Annualized Sharpe. Zero-stdev → 0 (not divide-by-zero)."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns) - rf / periods_per_year
    stdev = statistics.pstdev(returns)
    if stdev == 0:
        return 0.0
    return (mean / stdev) * math.sqrt(periods_per_year)


def sortino_ratio(returns: list[float], periods_per_year: int = 252, rf: float = 0.0) -> float:
    """Annualized Sortino (downside deviation only)."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns) - rf / periods_per_year
    downside = [r for r in returns if r < 0]
    if not downside:
        return 0.0
    dd_stdev = math.sqrt(sum(r * r for r in downside) / len(returns))
    if dd_stdev == 0:
        return 0.0
    return (mean / dd_stdev) * math.sqrt(periods_per_year)


def max_drawdown_pct(equity: list[float]) -> float:
    """Maximum drawdown as a positive percent (0–100)."""
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd


# ── Backtester ─────────────────────────────────────────────────────────────

SignalFn = Callable[[str, list[Bar], int], dict | None]
"""(symbol, bars_so_far, current_index) -> raw signal dict or None.

Raw dict fields mirror SignalPipeline inputs: symbol, action (buy/sell/close),
price, confidence, strategy, optional take_profit/stop_loss.
"""


def default_rsi_signal(symbol: str, bars: list[Bar], i: int) -> dict | None:
    """Baseline strategy: oversold RSI → long; overbought → close. Pure stdlib."""
    if i < 15:
        return None
    closes = [b.close for b in bars[: i + 1]]
    deltas = [closes[j] - closes[j - 1] for j in range(1, len(closes))]
    window = deltas[-14:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    if not gains and not losses:
        return None
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    price = bars[i].close
    if rsi < 30:
        return {
            "symbol": symbol,
            "action": "buy",
            "price": price,
            "confidence": min(1.0, (30 - rsi) / 30 + 0.55),
            "strategy": "rsi_oversold",
            "take_profit": price * 1.05,
            "stop_loss": price * 0.97,
        }
    if rsi > 70:
        return {
            "symbol": symbol,
            "action": "close",
            "price": price,
            "confidence": 0.6,
            "strategy": "rsi_overbought",
        }
    return None


def run_backtest(
    symbol: str,
    bars: list[Bar] | None = None,
    days: int = 90,
    signal_fn: SignalFn = default_rsi_signal,
    initial_capital: float = 10_000.0,
    position_size_pct: float = 0.10,
    use_pipeline_scoring: bool = False,
    score_min: float = 0.0,
) -> BacktestResult:
    """Run a backtest on ``symbol`` over ``days`` of daily OHLCV.

    ``signal_fn`` is called for each bar with the history so far. Signals trigger
    entries (buy/sell) or exits (close). TP/SL are checked intrabar using high/low.
    """
    if bars is None:
        bars = fetch_ohlcv(symbol, days=days)
    if len(bars) < 20:
        return BacktestResult(
            symbol=symbol,
            start="",
            end="",
            bars=len(bars),
            trades=[],
            initial_capital=initial_capital,
            final_capital=initial_capital,
            total_return_pct=0.0,
            cagr_pct=0.0,
            sharpe=0.0,
            sortino=0.0,
            max_drawdown_pct=0.0,
            calmar=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_trade_pnl=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            expectancy=0.0,
            equity_curve=[],
            notes=[f"insufficient bars ({len(bars)})"],
        )

    score_fn = _build_score_fn() if use_pipeline_scoring else None

    capital = initial_capital
    open_pos: dict | None = None
    trades: list[Trade] = []
    equity_curve: list[tuple[str, float]] = []

    for i, bar in enumerate(bars):
        # Mark-to-market equity for the curve
        mark = capital
        if open_pos:
            pnl = _unrealized(open_pos, bar.close)
            mark = capital + pnl
        equity_curve.append((bar.ts.date().isoformat(), round(mark, 2)))

        # Intrabar TP/SL check first (if long, check SL on low then TP on high)
        if open_pos:
            closed = _check_exits(open_pos, bar)
            if closed:
                capital += closed.pnl_usd
                trades.append(closed)
                open_pos = None

        raw = signal_fn(symbol, bars, i)
        if raw is None:
            continue

        action = str(raw.get("action", "")).lower()
        price = float(raw.get("price", bar.close) or bar.close)

        # Pipeline scoring gate (optional)
        confidence = float(raw.get("confidence", 0.5))
        score = confidence * 100  # crude fallback
        if score_fn is not None:
            try:
                scored = score_fn(raw)
                confidence = float(scored.get("confidence", confidence))
                score = float(scored.get("score", score))
            except Exception as e:
                log.debug("pipeline score failed: %s", e)

        if score < score_min:
            continue

        if action in {"buy", "long", "entry_long"} and open_pos is None:
            open_pos = _open(
                symbol=symbol,
                direction="long",
                entry_ts=bar.ts,
                entry_price=price,
                size_usd=capital * position_size_pct,
                raw=raw,
                confidence=confidence,
                score=score,
            )
        elif action in {"sell", "short", "entry_short"} and open_pos is None:
            open_pos = _open(
                symbol=symbol,
                direction="short",
                entry_ts=bar.ts,
                entry_price=price,
                size_usd=capital * position_size_pct,
                raw=raw,
                confidence=confidence,
                score=score,
            )
        elif action in {"close", "flat", "exit"} and open_pos is not None:
            pnl = _unrealized(open_pos, price)
            trade = _close(open_pos, bar.ts, price, pnl, "signal_flip")
            capital += pnl
            trades.append(trade)
            open_pos = None

    # Force-close any open position at last close
    if open_pos and bars:
        last = bars[-1]
        pnl = _unrealized(open_pos, last.close)
        trades.append(_close(open_pos, last.ts, last.close, pnl, "end_of_window"))
        capital += pnl

    return _finalize(symbol, bars, trades, equity_curve, initial_capital, capital)


def _open(
    *,
    symbol: str,
    direction: str,
    entry_ts: datetime,
    entry_price: float,
    size_usd: float,
    raw: dict,
    confidence: float,
    score: float,
) -> dict:
    tp = float(raw.get("take_profit", 0) or 0)
    sl = float(raw.get("stop_loss", 0) or 0)
    return {
        "symbol": symbol,
        "direction": direction,
        "entry_ts": entry_ts,
        "entry_price": entry_price,
        "size_usd": size_usd,
        "qty": size_usd / max(entry_price, 1e-9),
        "take_profit": tp,
        "stop_loss": sl,
        "confidence": confidence,
        "score": score,
        "entry_bar_idx": 0,
    }


def _unrealized(pos: dict, price: float) -> float:
    direction_sign = 1.0 if pos["direction"] == "long" else -1.0
    return (price - pos["entry_price"]) * pos["qty"] * direction_sign


def _check_exits(pos: dict, bar: Bar) -> Trade | None:
    tp = pos.get("take_profit", 0) or 0
    sl = pos.get("stop_loss", 0) or 0
    is_long = pos["direction"] == "long"

    # Pessimistic ordering: if both hit in the same bar, assume SL filled first.
    if is_long:
        if sl > 0 and bar.low <= sl:
            pnl = (sl - pos["entry_price"]) * pos["qty"]
            return _close(pos, bar.ts, sl, pnl, "stop_loss")
        if tp > 0 and bar.high >= tp:
            pnl = (tp - pos["entry_price"]) * pos["qty"]
            return _close(pos, bar.ts, tp, pnl, "take_profit")
    else:
        if sl > 0 and bar.high >= sl:
            pnl = (pos["entry_price"] - sl) * pos["qty"]
            return _close(pos, bar.ts, sl, pnl, "stop_loss")
        if tp > 0 and bar.low <= tp:
            pnl = (pos["entry_price"] - tp) * pos["qty"]
            return _close(pos, bar.ts, tp, pnl, "take_profit")
    return None


def _close(pos: dict, exit_ts: datetime, exit_price: float, pnl_usd: float, reason: str) -> Trade:
    pnl_pct = (pnl_usd / pos["size_usd"] * 100) if pos["size_usd"] > 0 else 0.0
    return Trade(
        symbol=pos["symbol"],
        direction=pos["direction"],
        entry_ts=pos["entry_ts"].isoformat()
        if hasattr(pos["entry_ts"], "isoformat")
        else str(pos["entry_ts"]),
        entry_price=round(pos["entry_price"], 4),
        exit_ts=exit_ts.isoformat() if hasattr(exit_ts, "isoformat") else str(exit_ts),
        exit_price=round(exit_price, 4),
        size_usd=round(pos["size_usd"], 2),
        pnl_usd=round(pnl_usd, 2),
        pnl_pct=round(pnl_pct, 3),
        hold_bars=0,
        exit_reason=reason,
        confidence=pos.get("confidence", 0.0),
        score=pos.get("score", 0.0),
    )


def _finalize(
    symbol: str,
    bars: list[Bar],
    trades: list[Trade],
    equity_curve: list[tuple[str, float]],
    initial_capital: float,
    final_capital: float,
) -> BacktestResult:
    equity_vals = [v for _, v in equity_curve] or [initial_capital]
    returns = _returns_from_equity(equity_vals)

    total_return = (final_capital / initial_capital - 1) * 100 if initial_capital else 0.0
    days = len(bars)
    if days >= 2 and initial_capital > 0 and final_capital > 0:
        years = days / 252
        cagr = ((final_capital / initial_capital) ** (1 / max(years, 1e-9)) - 1) * 100
    else:
        cagr = 0.0

    sharpe = sharpe_ratio(returns)
    sortino = sortino_ratio(returns)
    max_dd = max_drawdown_pct(equity_vals)
    calmar = (cagr / max_dd) if max_dd > 0 else 0.0

    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd < 0]
    total_wins = sum(t.pnl_usd for t in wins)
    total_losses = abs(sum(t.pnl_usd for t in losses))
    profit_factor = (
        (total_wins / total_losses) if total_losses > 0 else float("inf") if total_wins > 0 else 0.0
    )
    win_rate = (len(wins) / len(trades)) if trades else 0.0
    avg_win = (total_wins / len(wins)) if wins else 0.0
    avg_loss = (-total_losses / len(losses)) if losses else 0.0
    avg_trade = sum(t.pnl_usd for t in trades) / len(trades) if trades else 0.0
    win_prob = len(wins) / len(trades) if trades else 0.0
    expectancy = win_prob * avg_win + (1 - win_prob) * avg_loss

    return BacktestResult(
        symbol=symbol,
        start=bars[0].ts.date().isoformat() if bars else "",
        end=bars[-1].ts.date().isoformat() if bars else "",
        bars=len(bars),
        trades=trades,
        initial_capital=initial_capital,
        final_capital=round(final_capital, 2),
        total_return_pct=round(total_return, 3),
        cagr_pct=round(cagr, 3),
        sharpe=round(sharpe, 3),
        sortino=round(sortino, 3),
        max_drawdown_pct=round(max_dd, 3),
        calmar=round(calmar, 3),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 3) if math.isfinite(profit_factor) else 999.0,
        avg_trade_pnl=round(avg_trade, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        expectancy=round(expectancy, 2),
        equity_curve=equity_curve,
    )


def _build_score_fn() -> Callable[[dict], dict] | None:
    """Optional SignalPipeline integration. Returns None if pipeline isn't importable."""
    try:
        import sys
        from pathlib import Path as _P

        alpha = _P.home() / "Code" / "Sapphire" / "services" / "alpha"
        if str(alpha) not in sys.path:
            sys.path.insert(0, str(alpha))
        from signal_pipeline import pipeline as _pipe  # type: ignore

        def _score(raw: dict) -> dict:
            s = _pipe._score(raw)  # internal scoring only — no audit write
            return {"confidence": s.confidence, "score": s.score, "routing": s.routing}

        return _score
    except Exception as e:
        log.debug("pipeline scoring unavailable: %s", e)
        return None


# ── Multi-symbol sweep & persistence ───────────────────────────────────────


def run_sweep(
    symbols: Iterable[str],
    days: int = 90,
    signal_fn: SignalFn = default_rsi_signal,
    **kw: Any,
) -> dict[str, BacktestResult]:
    out: dict[str, BacktestResult] = {}
    for sym in symbols:
        out[sym] = run_backtest(sym, days=days, signal_fn=signal_fn, **kw)
    return out


def save_result(result: BacktestResult, out_dir: Path | str | None = None) -> Path:
    """Append a result to data/backtests/<symbol>-<ts>.json. Returns file path."""
    out_dir = Path(out_dir) if out_dir else Path.home() / "Code" / "Sapphire" / "data" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{result.symbol}-{ts}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
    return path


__all__ = [
    "Bar",
    "Trade",
    "BacktestResult",
    "fetch_ohlcv",
    "default_rsi_signal",
    "run_backtest",
    "run_sweep",
    "save_result",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown_pct",
]
