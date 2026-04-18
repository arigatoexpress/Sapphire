"""Historical backtester — simulate signal strategies over 90d of OHLCV.

Loads price history from yfinance, walks the bar series forward one day at
a time, asks a strategy function for a signal on each close, and tracks the
resulting trades. Produces a `BacktestReport` with trade-by-trade PnL plus
aggregated Sharpe / Sortino / win-rate metrics.

Strategy contract — a callable `(bars: list[Bar]) -> Decision | None`:
  - `bars` is the list of Bar objects up to and including the current close
  - Return None to stay flat, or a Decision("long"|"short", size=0..1).

Built-in strategies:
  - `rsi_mean_reversion` — RSI<30 → long, RSI>70 → short (exits on cross back)
  - `ma_crossover`       — fast/slow SMA crossover
  - `buy_and_hold`       — long on bar 1, hold

Risk-adjusted metrics follow the same annualization convention as
`risk_engine.py` (365 trading days/year for crypto; RISK_FREE_RATE=0.045).

CLI:
    python -m lib.analytics.backtest BTC-USD --days 90 --strategy rsi
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

log = logging.getLogger(__name__)

# Annualization — match risk_engine.py (crypto trades 365 days/year)
TRADING_DAYS_PER_YEAR = 365
RISK_FREE_RATE = 0.045  # annual


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Bar:
    """One OHLCV bar."""

    date: str          # ISO date "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Decision:
    """Strategy output for a single bar."""

    direction: Literal["long", "short", "flat"]
    size: float = 1.0          # fraction of bankroll to deploy (0.0–1.0)
    stop_pct: float | None = None   # optional stop-loss as % of entry
    take_pct: float | None = None   # optional take-profit as % of entry


Strategy = Callable[[list[Bar]], Decision | None]


@dataclass
class BacktestTrade:
    entry_date: str
    exit_date: str
    direction: str
    entry_price: float
    exit_price: float
    size_usd: float
    pnl_usd: float
    pnl_pct: float
    outcome: str       # win | loss | break_even
    bars_held: int
    exit_reason: str   # signal_reverse | stop | take | end_of_data


@dataclass
class BacktestReport:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    bars: int
    bankroll: float

    # Counts
    total_trades: int
    wins: int
    losses: int
    breakevens: int

    # Profitability
    total_pnl_usd: float
    total_return_pct: float
    win_rate: float | None
    profit_factor: float | None
    avg_win_usd: float
    avg_loss_usd: float
    expectancy_usd: float

    # Risk-adjusted (annualized, per-trade-return basis)
    sharpe: float | None
    sortino: float | None
    calmar: float | None

    # Drawdown
    max_drawdown_pct: float
    max_drawdown_usd: float
    max_drawdown_duration_days: int

    # Raw series for charting/audit
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    computed_at: str = ""


# ---------------------------------------------------------------------------
# OHLCV loader
# ---------------------------------------------------------------------------


def load_yfinance_ohlcv(symbol: str, days: int = 90) -> list[Bar]:
    """Load daily OHLCV bars from yfinance.

    Returns an empty list if yfinance is unreachable; callers should check.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed — pip install yfinance")
        return []

    end = datetime.now(UTC)
    start = end - timedelta(days=days + 5)  # buffer for non-trading days
    try:
        df = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as e:
        log.warning("yfinance download failed for %s: %s", symbol, e)
        return []

    if df is None or df.empty:
        return []

    # yfinance returns MultiIndex columns for a single symbol since ~0.2.37.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    bars: list[Bar] = []
    for idx, row in df.iterrows():
        try:
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            bars.append(Bar(
                date=date_str,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0) or 0),
            ))
        except (KeyError, ValueError, TypeError) as e:
            log.debug("skipping malformed bar %s: %s", idx, e)
            continue

    # Trim to the requested window (most recent `days` bars)
    return bars[-days:] if len(bars) > days else bars


# ---------------------------------------------------------------------------
# Indicators — self-contained so the backtester has no soft dependencies
# ---------------------------------------------------------------------------


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0.0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------


def buy_and_hold(bars: list[Bar]) -> Decision | None:
    """Enter long on the first bar, stay long forever."""
    if len(bars) < 1:
        return None
    return Decision(direction="long", size=1.0)


def rsi_mean_reversion(bars: list[Bar], oversold: float = 30.0, overbought: float = 70.0) -> Decision | None:
    """Long when RSI<30, short when RSI>70, flat otherwise."""
    closes = [b.close for b in bars]
    rsi = _rsi(closes)
    if rsi is None:
        return None
    if rsi < oversold:
        return Decision(direction="long", size=1.0, stop_pct=0.03, take_pct=0.06)
    if rsi > overbought:
        return Decision(direction="short", size=1.0, stop_pct=0.03, take_pct=0.06)
    return Decision(direction="flat")


def ma_crossover(bars: list[Bar], fast: int = 10, slow: int = 30) -> Decision | None:
    """Long when fast SMA > slow SMA, short when below."""
    closes = [b.close for b in bars]
    fast_ma = _sma(closes, fast)
    slow_ma = _sma(closes, slow)
    if fast_ma is None or slow_ma is None:
        return None
    if fast_ma > slow_ma:
        return Decision(direction="long", size=1.0)
    if fast_ma < slow_ma:
        return Decision(direction="short", size=1.0)
    return Decision(direction="flat")


BUILT_IN_STRATEGIES: dict[str, Strategy] = {
    "buy_and_hold": buy_and_hold,
    "rsi": rsi_mean_reversion,
    "rsi_mean_reversion": rsi_mean_reversion,
    "ma_crossover": ma_crossover,
}


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------


class Backtester:
    """Walk-forward OHLCV simulator.

    On each bar the current close is passed to the strategy as the last
    element of `bars`. Signals fill at the *next* bar's open (standard
    backtest convention — no look-ahead bias on the signal bar). Stops and
    take-profits are checked intra-bar against high/low.
    """

    def __init__(self, bankroll: float = 10_000.0, fee_bps: float = 5.0):
        """
        Args:
            bankroll: starting equity in USD.
            fee_bps: per-side fee in basis points (5 = 0.05%).
        """
        self.bankroll = bankroll
        self.fee_bps = fee_bps

    # ------------------------------------------------------------------

    def run(
        self,
        bars: list[Bar],
        strategy: Strategy | str,
        symbol: str = "?",
    ) -> BacktestReport:
        if isinstance(strategy, str):
            strat_name = strategy
            if strategy not in BUILT_IN_STRATEGIES:
                raise ValueError(
                    f"unknown strategy {strategy!r}; "
                    f"choices: {sorted(BUILT_IN_STRATEGIES)}"
                )
            fn: Strategy = BUILT_IN_STRATEGIES[strategy]
        else:
            fn = strategy
            strat_name = getattr(strategy, "__name__", "custom")

        if len(bars) < 2:
            return self._empty_report(symbol, strat_name, bars)

        trades: list[BacktestTrade] = []
        position: _OpenPosition | None = None
        equity = self.bankroll
        equity_curve: list[dict] = [{
            "date": bars[0].date, "equity_usd": round(equity, 2), "pnl_usd": 0.0,
        }]

        # Walk forward: decision on close of bar i, fill at open of bar i+1.
        for i in range(len(bars) - 1):
            window = bars[: i + 1]
            next_bar = bars[i + 1]
            decision = fn(window)

            if position is not None:
                # Check intra-bar stop / take against next_bar's range before
                # any reversal fill (stops trigger first in a realistic fill).
                exit_price, exit_reason = position.check_stop_take(next_bar)
                if exit_price is not None:
                    trade = self._close_position(position, next_bar.date, exit_price, exit_reason)
                    equity += trade.pnl_usd
                    trades.append(trade)
                    equity_curve.append({
                        "date": next_bar.date,
                        "equity_usd": round(equity, 2),
                        "pnl_usd": round(trade.pnl_usd, 2),
                    })
                    position = None

            # New / reversing signal — fill at next bar's open
            if decision and decision.direction in ("long", "short"):
                if position is None:
                    position = _OpenPosition(
                        entry_date=next_bar.date,
                        entry_bar_idx=i + 1,
                        direction=decision.direction,
                        entry_price=next_bar.open,
                        size_usd=equity * max(0.0, min(1.0, decision.size)),
                        stop_pct=decision.stop_pct,
                        take_pct=decision.take_pct,
                        fee_bps=self.fee_bps,
                    )
                elif position.direction != decision.direction:
                    # Reverse: close existing, open opposite
                    trade = self._close_position(position, next_bar.date, next_bar.open, "signal_reverse")
                    equity += trade.pnl_usd
                    trades.append(trade)
                    equity_curve.append({
                        "date": next_bar.date,
                        "equity_usd": round(equity, 2),
                        "pnl_usd": round(trade.pnl_usd, 2),
                    })
                    position = _OpenPosition(
                        entry_date=next_bar.date,
                        entry_bar_idx=i + 1,
                        direction=decision.direction,
                        entry_price=next_bar.open,
                        size_usd=equity * max(0.0, min(1.0, decision.size)),
                        stop_pct=decision.stop_pct,
                        take_pct=decision.take_pct,
                        fee_bps=self.fee_bps,
                    )
            elif decision and decision.direction == "flat" and position is not None:
                trade = self._close_position(position, next_bar.date, next_bar.open, "signal_flat")
                equity += trade.pnl_usd
                trades.append(trade)
                equity_curve.append({
                    "date": next_bar.date,
                    "equity_usd": round(equity, 2),
                    "pnl_usd": round(trade.pnl_usd, 2),
                })
                position = None

        # Close any remaining position at the final close
        if position is not None:
            last = bars[-1]
            trade = self._close_position(position, last.date, last.close, "end_of_data")
            equity += trade.pnl_usd
            trades.append(trade)
            equity_curve.append({
                "date": last.date,
                "equity_usd": round(equity, 2),
                "pnl_usd": round(trade.pnl_usd, 2),
            })

        return self._build_report(symbol, strat_name, bars, trades, equity_curve)

    # ------------------------------------------------------------------

    def _close_position(
        self,
        pos: _OpenPosition,
        exit_date: str,
        exit_price: float,
        exit_reason: str,
    ) -> BacktestTrade:
        if pos.direction == "long":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price

        # Round-trip fees (entry + exit)
        fee_pct = (self.fee_bps / 10_000.0) * 2
        pnl_pct -= fee_pct

        pnl_usd = pos.size_usd * pnl_pct

        if pnl_usd > 0.01:
            outcome = "win"
        elif pnl_usd < -0.01:
            outcome = "loss"
        else:
            outcome = "break_even"

        # Best-effort bar count — when dates are ISO we can derive it; else 1.
        try:
            d1 = datetime.fromisoformat(pos.entry_date)
            d2 = datetime.fromisoformat(exit_date)
            bars_held = max(1, (d2 - d1).days)
        except ValueError:
            bars_held = 1

        return BacktestTrade(
            entry_date=pos.entry_date,
            exit_date=exit_date,
            direction=pos.direction,
            entry_price=round(pos.entry_price, 4),
            exit_price=round(exit_price, 4),
            size_usd=round(pos.size_usd, 2),
            pnl_usd=round(pnl_usd, 2),
            pnl_pct=round(pnl_pct, 4),
            outcome=outcome,
            bars_held=bars_held,
            exit_reason=exit_reason,
        )

    # ------------------------------------------------------------------

    def _empty_report(self, symbol: str, strat_name: str, bars: list[Bar]) -> BacktestReport:
        return BacktestReport(
            symbol=symbol,
            strategy=strat_name,
            start_date=bars[0].date if bars else "",
            end_date=bars[-1].date if bars else "",
            bars=len(bars),
            bankroll=self.bankroll,
            total_trades=0, wins=0, losses=0, breakevens=0,
            total_pnl_usd=0.0, total_return_pct=0.0,
            win_rate=None, profit_factor=None,
            avg_win_usd=0.0, avg_loss_usd=0.0, expectancy_usd=0.0,
            sharpe=None, sortino=None, calmar=None,
            max_drawdown_pct=0.0, max_drawdown_usd=0.0, max_drawdown_duration_days=0,
            trades=[], equity_curve=[],
            computed_at=datetime.now(UTC).isoformat(),
        )

    # ------------------------------------------------------------------

    def _build_report(
        self,
        symbol: str,
        strat_name: str,
        bars: list[Bar],
        trades: list[BacktestTrade],
        equity_curve: list[dict],
    ) -> BacktestReport:
        n = len(trades)
        wins = [t for t in trades if t.outcome == "win"]
        losses = [t for t in trades if t.outcome == "loss"]
        breakevens = [t for t in trades if t.outcome == "break_even"]

        total_pnl = round(sum(t.pnl_usd for t in trades), 2)
        total_return_pct = round(total_pnl / self.bankroll, 4) if self.bankroll > 0 else 0.0

        decisive = len(wins) + len(losses)
        win_rate = (len(wins) / decisive) if decisive > 0 else None

        avg_win = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(abs(t.pnl_usd) for t in losses) / len(losses) if losses else 0.0
        expectancy = (total_pnl / n) if n > 0 else 0.0

        pf: float | None = None
        total_win = sum(t.pnl_usd for t in wins)
        total_loss = sum(abs(t.pnl_usd) for t in losses)
        if total_loss > 0:
            pf = round(total_win / total_loss, 3)
        elif total_win > 0:
            pf = float("inf")

        # Equity-curve drawdown against the running peak. Duration is measured
        # in days between the peak date and the trough date.
        peak_equity = self.bankroll
        peak_date: str | None = equity_curve[0]["date"] if equity_curve else None
        max_dd_pct = 0.0
        max_dd_usd = 0.0
        max_dd_duration = 0
        for point in equity_curve:
            eq = point["equity_usd"]
            if eq > peak_equity:
                peak_equity = eq
                peak_date = point["date"]
            dd_usd = peak_equity - eq
            dd_pct = dd_usd / peak_equity if peak_equity > 0 else 0.0
            duration = 0
            if peak_date and point.get("date"):
                try:
                    d1 = datetime.fromisoformat(peak_date)
                    d2 = datetime.fromisoformat(point["date"])
                    duration = max(0, (d2 - d1).days)
                except (ValueError, TypeError):
                    pass
            point["drawdown_pct"] = round(dd_pct, 4)
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_usd = dd_usd
                max_dd_duration = duration

        # Sharpe / Sortino on per-trade % returns of bankroll, annualized
        # using trades-per-day × 365 (matching risk_engine convention).
        sharpe = sortino = calmar = None
        if n >= 2:
            pct_rets = [t.pnl_usd / self.bankroll for t in trades]
            mean_r = sum(pct_rets) / n
            var = sum((r - mean_r) ** 2 for r in pct_rets) / (n - 1)
            std = math.sqrt(var)
            # Sortino: deviation of negative returns against full sample (MAR=0).
            downside_sq = [(max(0.0, -r)) ** 2 for r in pct_rets]
            dvar = sum(downside_sq) / n
            dstd = math.sqrt(dvar)

            tpd = self._trades_per_day(trades, bars)
            annualize = tpd * TRADING_DAYS_PER_YEAR
            rf_per_trade = RISK_FREE_RATE / (TRADING_DAYS_PER_YEAR * max(1, tpd))

            if std > 0:
                sharpe = round(((mean_r - rf_per_trade) / std) * math.sqrt(annualize), 3)
            if dstd > 0:
                sortino = round(((mean_r - rf_per_trade) / dstd) * math.sqrt(annualize), 3)
            annual_return = mean_r * annualize
            if max_dd_pct > 0:
                calmar = round(annual_return / max_dd_pct, 3)

        return BacktestReport(
            symbol=symbol,
            strategy=strat_name,
            start_date=bars[0].date,
            end_date=bars[-1].date,
            bars=len(bars),
            bankroll=self.bankroll,
            total_trades=n,
            wins=len(wins),
            losses=len(losses),
            breakevens=len(breakevens),
            total_pnl_usd=total_pnl,
            total_return_pct=total_return_pct,
            win_rate=round(win_rate, 3) if win_rate is not None else None,
            profit_factor=pf,
            avg_win_usd=round(avg_win, 2),
            avg_loss_usd=round(avg_loss, 2),
            expectancy_usd=round(expectancy, 2),
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_duration_days=max_dd_duration,
            trades=[asdict(t) for t in trades],
            equity_curve=equity_curve,
            computed_at=datetime.now(UTC).isoformat(),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _trades_per_day(trades: list[BacktestTrade], bars: list[Bar]) -> int:
        """Estimate trading frequency from the backtest window."""
        if not trades or not bars:
            return 1
        try:
            first = datetime.fromisoformat(bars[0].date)
            last = datetime.fromisoformat(bars[-1].date)
            days = max(1, (last - first).days)
            return max(1, round(len(trades) / days))
        except ValueError:
            return 1


# ---------------------------------------------------------------------------
# Open-position helper
# ---------------------------------------------------------------------------


@dataclass
class _OpenPosition:
    entry_date: str
    entry_bar_idx: int
    direction: str          # long | short
    entry_price: float
    size_usd: float
    stop_pct: float | None
    take_pct: float | None
    fee_bps: float

    def check_stop_take(self, bar: Bar) -> tuple[float | None, str]:
        """Return (exit_price, reason) if the bar's range triggers stop/take, else (None, '').

        For longs: stop below entry·(1-stop_pct), take above entry·(1+take_pct).
        For shorts: stop above entry·(1+stop_pct), take below entry·(1-take_pct).
        If both levels are touched intra-bar, assume stop fills first (conservative).
        """
        if self.direction == "long":
            stop_level = self.entry_price * (1 - self.stop_pct) if self.stop_pct else None
            take_level = self.entry_price * (1 + self.take_pct) if self.take_pct else None
            if stop_level is not None and bar.low <= stop_level:
                return stop_level, "stop"
            if take_level is not None and bar.high >= take_level:
                return take_level, "take"
        else:  # short
            stop_level = self.entry_price * (1 + self.stop_pct) if self.stop_pct else None
            take_level = self.entry_price * (1 - self.take_pct) if self.take_pct else None
            if stop_level is not None and bar.high >= stop_level:
                return stop_level, "stop"
            if take_level is not None and bar.low <= take_level:
                return take_level, "take"
        return None, ""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


def backtest_symbol(
    symbol: str,
    strategy: Strategy | str = "rsi",
    days: int = 90,
    bankroll: float = 10_000.0,
    fee_bps: float = 5.0,
) -> BacktestReport:
    """One-shot helper: fetch yfinance → run backtest → return report."""
    bars = load_yfinance_ohlcv(symbol, days=days)
    if not bars:
        return Backtester(bankroll=bankroll, fee_bps=fee_bps)._empty_report(
            symbol,
            strategy if isinstance(strategy, str) else getattr(strategy, "__name__", "custom"),
            [],
        )
    return Backtester(bankroll=bankroll, fee_bps=fee_bps).run(bars, strategy, symbol=symbol)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Sapphire backtester")
    p.add_argument("symbol", help="yfinance symbol, e.g. BTC-USD, ETH-USD, SPY")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--strategy", default="rsi", choices=sorted(BUILT_IN_STRATEGIES))
    p.add_argument("--bankroll", type=float, default=10_000.0)
    p.add_argument("--fees", type=float, default=5.0, help="per-side fee in bps")
    args = p.parse_args()

    r = backtest_symbol(
        args.symbol,
        strategy=args.strategy,
        days=args.days,
        bankroll=args.bankroll,
        fee_bps=args.fees,
    )
    print(f"=== {r.symbol} · {r.strategy} · {r.start_date} → {r.end_date} ({r.bars} bars) ===")
    print(f"Trades:       {r.total_trades} ({r.wins}W / {r.losses}L / {r.breakevens}BE)")
    print(f"Win rate:     {r.win_rate}")
    print(f"Total PnL:    ${r.total_pnl_usd:+,.2f}  ({r.total_return_pct:+.2%})")
    print(f"Profit factor:{r.profit_factor}")
    print(f"Expectancy:   ${r.expectancy_usd:+.2f}/trade")
    print(f"Sharpe:       {r.sharpe}")
    print(f"Sortino:      {r.sortino}")
    print(f"Calmar:       {r.calmar}")
    print(f"Max DD:       {r.max_drawdown_pct:.2%} (-${r.max_drawdown_usd:,.2f}, {r.max_drawdown_duration_days}d)")
