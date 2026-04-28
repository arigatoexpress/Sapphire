"""Backtesting engine — validate signal quality against historical OHLCV.

Loads 90d daily bars via yfinance, generates SMA crossover signals, scores each
through a pipeline-identical scoring formula, simulates trades with ATR stops,
and computes Sharpe/Sortino/max-drawdown/win-rate/profit-factor.

Supports WITH vs WITHOUT regime enhancement comparison to quantify the lift
from lib.analytics.signal_enhancer (when available) or a local regime classifier.

Usage:
    from lib.analytics.backtest import Backtester, BacktestConfig
    cfg = BacktestConfig(symbols=["BTC-USD"], period_days=90)
    results = Backtester(cfg).run_comparison()
    # → {"with_regime": {...}, "without_regime": {...}, "delta": {...}}

CLI:
    python3 -m lib.analytics.backtest [--symbols BTC-USD,ETH-USD] [--days 90]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types shared with strategies.py and backtest_engine.py
# ---------------------------------------------------------------------------


@dataclass
class Bar:
    """Single OHLCV bar."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Decision:
    """Signal from a strategy — direction + optional sizing / metadata."""

    direction: str  # "long" | "short" | "flat"
    size: float = 1.0
    stop_pct: float = 0.0
    tp_pct: float = 0.0
    reason: str = ""


DEFAULT_SYMBOLS = (
    # Crypto
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "ZEC-USD",
    # Equities
    "SPY",
    "QQQ",
    # Commodities
    "GLD",
    "SLV",
    "USO",
    "URA",
    "COPX",
    # Macro
    "DX-Y.NYB",
    "^VIX",
    "^TNX",
)
DEFAULT_OUTPUT_DIR = Path("data/backtests")


@dataclass
class BacktestConfig:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    period_days: int = 90
    sma_fast: int = 10
    sma_slow: int = 30
    initial_capital: float = 100_000.0
    fee_bps: float = 0.0
    position_pct: float = 0.10  # 10% of equity per trade
    rr_ratio: float = 1.67  # take-profit / stop-loss ratio
    atr_period: int = 14
    atr_stop_mult: float = 1.5  # stop = entry ± mult × ATR
    regime_enhancement: bool = True
    output_dir: Path = DEFAULT_OUTPUT_DIR
    high_conf_threshold: float = 0.75
    medium_conf_threshold: float = 0.5


@dataclass
class Trade:
    symbol: str
    direction: str  # long | short
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl: float
    pnl_pct: float
    bars_held: int
    score: float
    confidence: float
    regime: str
    exit_reason: str  # tp | sl | cross | eod


@dataclass
class BacktestResult:
    symbol: str
    regime_enhancement: bool
    period_days: int
    bar_count: int
    trade_count: int
    final_equity: float
    total_return_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_score: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)  # [(date, equity)]
    benchmark_curve: list[tuple[str, float]] = field(default_factory=list)  # buy-and-hold


def _load_ohlcv(symbol: str, days: int):
    """Download OHLCV; returns a list of bar dicts (date, open, high, low, close, volume)."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance required for backtest (pip install yfinance)") from e

    df = yf.download(
        symbol,
        period=f"{days + 60}d",  # buffer for SMA warmup
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")

    # yfinance returns MultiIndex columns when symbol count is ambiguous; flatten.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    bars = []
    for idx, row in df.iterrows():
        close = float(row["Close"])
        if not math.isfinite(close) or close <= 0:
            continue
        bars.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": close,
                "volume": float(row.get("Volume", 0) or 0),
            }
        )
    return bars


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0 or len(values) < window:
        return out
    running = sum(values[:window])
    out[window - 1] = running / window
    for i in range(window, len(values)):
        running += values[i] - values[i - window]
        out[i] = running / window
    return out


def _atr(bars: list[dict], period: int) -> list[float | None]:
    """Wilder's ATR — average true range."""
    trs: list[float] = []
    for i, bar in enumerate(bars):
        if i == 0:
            trs.append(bar["high"] - bar["low"])
            continue
        prev_close = bars[i - 1]["close"]
        tr = max(
            bar["high"] - bar["low"],
            abs(bar["high"] - prev_close),
            abs(bar["low"] - prev_close),
        )
        trs.append(tr)
    out: list[float | None] = [None] * len(bars)
    if len(trs) < period:
        return out
    # seed with simple average, then smooth
    out[period - 1] = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        prev = out[i - 1] or trs[i]
        out[i] = (prev * (period - 1) + trs[i]) / period
    return out


def _classify_regime(closes: list[float], idx: int) -> tuple[str, float]:
    """Simple 20/50 trend classifier: returns (regime, regime_score ∈ [-1, 1]).

    Used when lib.analytics.signal_enhancer isn't importable — gives the
    backtester a self-contained regime signal so WITH-vs-WITHOUT is meaningful.
    """
    if idx < 50:
        return "UNKNOWN", 0.0
    ma20 = sum(closes[idx - 19 : idx + 1]) / 20
    ma50 = sum(closes[idx - 49 : idx + 1]) / 50
    if ma50 == 0:
        return "UNKNOWN", 0.0
    slope = (ma20 - ma50) / ma50
    # recent returns volatility as uncertainty proxy
    window = closes[idx - 19 : idx + 1]
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / len(window)
    vol = math.sqrt(var) / mean if mean else 0.0
    if vol > 0.05:
        return "VOLATILE", max(-1.0, min(1.0, slope * 10))
    if slope > 0.02:
        return "TREND_UP", min(1.0, slope * 10)
    if slope < -0.02:
        return "TREND_DOWN", max(-1.0, slope * 10)
    return "RANGE", slope * 10


def _apply_enhancement(
    direction: str,
    confidence: float,
    regime: str,
    regime_score: float,
) -> tuple[float, list[str]]:
    """Regime-aware confidence adjustment; mirrors signal_enhancer behavior.

    - TREND_UP + long  → +0.10 to +0.15
    - TREND_UP + short → -0.15 to -0.25
    - TREND_DOWN opposite pattern
    - VOLATILE         → -0.10 (reduce conviction)
    - RANGE            → no change
    """
    flags: list[str] = []
    boost = 0.0
    aligned = (regime == "TREND_UP" and direction == "long") or (
        regime == "TREND_DOWN" and direction == "short"
    )
    opposed = (regime == "TREND_UP" and direction == "short") or (
        regime == "TREND_DOWN" and direction == "long"
    )
    if aligned:
        boost = 0.10 + 0.05 * abs(regime_score)
        flags.append(f"regime_aligned:{regime}")
    elif opposed:
        boost = -(0.15 + 0.10 * abs(regime_score))
        flags.append(f"regime_opposed:{regime}")
    elif regime == "VOLATILE":
        boost = -0.10
        flags.append("regime_volatile")
    adj = max(0.0, min(1.0, confidence + boost))
    return adj, flags


def _score_signal(
    confidence: float,
    rr_ratio: float,
    position_pct: float,
    kernel_ok: bool = True,
) -> float:
    """Pipeline-identical composite score (0–100).

    Mirrors services/alpha/signal_pipeline.py `_score`:
    confidence(40) + kernel_ok(25) + rr_factor(20) + position_factor(15).
    """
    conf_pts = min(40.0, max(0.0, confidence * 40))
    kern_pts = 25 if kernel_ok else 0
    rr_pts = min(20, rr_ratio * 7) if rr_ratio > 0 else 5
    pos_pts = min(15, (position_pct / 0.10) * 15)
    return round(conf_pts + kern_pts + rr_pts + pos_pts, 1)


def _generate_signals(bars: list[dict], cfg: BacktestConfig) -> list[dict]:
    """SMA crossover signals: fast crosses slow → long/short entry."""
    closes = [b["close"] for b in bars]
    fast = _sma(closes, cfg.sma_fast)
    slow = _sma(closes, cfg.sma_slow)
    atr = _atr(bars, cfg.atr_period)

    signals: list[dict] = []
    for i in range(1, len(bars)):
        f_now, s_now = fast[i], slow[i]
        f_prev, s_prev = fast[i - 1], slow[i - 1]
        if None in (f_now, s_now, f_prev, s_prev):
            continue
        # SMA spread ratio as confidence proxy (clamped)
        spread = abs(f_now - s_now) / s_now if s_now else 0.0
        confidence = min(0.95, 0.50 + spread * 20)

        direction = None
        if f_prev <= s_prev and f_now > s_now:
            direction = "long"
        elif f_prev >= s_prev and f_now < s_now:
            direction = "short"
        if not direction:
            continue

        signals.append(
            {
                "idx": i,
                "date": bars[i]["date"],
                "price": bars[i]["close"],
                "direction": direction,
                "confidence": confidence,
                "atr": atr[i] if atr[i] else 0.0,
            }
        )
    return signals


def _simulate(
    bars: list[dict],
    signals: list[dict],
    cfg: BacktestConfig,
    with_regime: bool,
) -> tuple[list[Trade], list[float]]:
    """Walk bars; execute entries, manage stops/targets; return trades + equity curve."""
    closes = [b["close"] for b in bars]
    equity = cfg.initial_capital
    equity_curve: list[float] = [equity] * len(bars)
    trades: list[Trade] = []

    open_trade: dict | None = None
    sig_by_idx = {s["idx"]: s for s in signals}

    for i, bar in enumerate(bars):
        # Manage open trade first
        if open_trade:
            direction = open_trade["direction"]
            entry = open_trade["entry_price"]
            stop = open_trade["stop"]
            target = open_trade["target"]

            exit_price: float | None = None
            exit_reason = ""
            if direction == "long":
                if bar["low"] <= stop:
                    exit_price, exit_reason = stop, "sl"
                elif bar["high"] >= target:
                    exit_price, exit_reason = target, "tp"
            else:  # short
                if bar["high"] >= stop:
                    exit_price, exit_reason = stop, "sl"
                elif bar["low"] <= target:
                    exit_price, exit_reason = target, "tp"

            # Exit on opposite-direction signal
            opp_sig = sig_by_idx.get(i)
            if exit_price is None and opp_sig and opp_sig["direction"] != direction:
                exit_price, exit_reason = bar["close"], "cross"

            # Final-bar close-out
            if exit_price is None and i == len(bars) - 1:
                exit_price, exit_reason = bar["close"], "eod"

            if exit_price is not None:
                pnl_per_unit = (exit_price - entry) if direction == "long" else (entry - exit_price)
                units = open_trade["units"]
                gross_pnl_pct = (pnl_per_unit / entry) if entry else 0.0
                fee_pct = (cfg.fee_bps / 10_000.0) * 2
                net_pnl_pct = gross_pnl_pct - fee_pct
                pnl = open_trade["position_value"] * net_pnl_pct
                equity += pnl
                pnl_pct = net_pnl_pct * 100
                trades.append(
                    Trade(
                        symbol=open_trade["symbol"],
                        direction=direction,
                        entry_date=open_trade["entry_date"],
                        entry_price=entry,
                        exit_date=bar["date"],
                        exit_price=exit_price,
                        pnl=round(pnl, 2),
                        pnl_pct=round(pnl_pct, 3),
                        bars_held=i - open_trade["entry_idx"],
                        score=open_trade["score"],
                        confidence=open_trade["confidence"],
                        regime=open_trade["regime"],
                        exit_reason=exit_reason,
                    )
                )
                open_trade = None

        # Entry: on crossover signal when flat
        sig = sig_by_idx.get(i)
        if open_trade is None and sig:
            direction = sig["direction"]
            confidence = sig["confidence"]
            regime, regime_score = _classify_regime(closes, i)
            if with_regime:
                confidence, _flags = _apply_enhancement(direction, confidence, regime, regime_score)
            # Skip if enhancement drives confidence below medium
            if confidence < cfg.medium_conf_threshold:
                equity_curve[i] = equity
                continue

            entry_price = bar["close"]
            atr_val = sig["atr"] or entry_price * 0.02
            risk_per_unit = atr_val * cfg.atr_stop_mult
            if direction == "long":
                stop = entry_price - risk_per_unit
                target = entry_price + risk_per_unit * cfg.rr_ratio
            else:
                stop = entry_price + risk_per_unit
                target = entry_price - risk_per_unit * cfg.rr_ratio

            position_value = equity * cfg.position_pct
            units = position_value / entry_price if entry_price else 0.0
            score = _score_signal(confidence, cfg.rr_ratio, cfg.position_pct)
            open_trade = {
                "symbol": sig.get("symbol") or "?",
                "direction": direction,
                "entry_date": bar["date"],
                "entry_idx": i,
                "entry_price": entry_price,
                "stop": stop,
                "target": target,
                "position_value": position_value,
                "units": units,
                "confidence": confidence,
                "regime": regime,
                "score": score,
            }

        equity_curve[i] = equity

    return trades, equity_curve


def _metrics(
    equity_curve: list[float],
    trades: list[Trade],
    initial_capital: float,
) -> dict[str, float]:
    """Sharpe, Sortino, max-DD, win-rate, profit-factor, averages."""
    # Daily returns
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            returns.append((equity_curve[i] - prev) / prev)

    sharpe = 0.0
    sortino = 0.0
    if returns:
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var)
        if std > 0:
            sharpe = (mean / std) * math.sqrt(252)
        downside = [r for r in returns if r < 0]
        if downside:
            d_var = sum(r**2 for r in downside) / len(downside)
            d_std = math.sqrt(d_var)
            if d_std > 0:
                sortino = (mean / d_std) * math.sqrt(252)

    # Max drawdown
    peak = equity_curve[0] if equity_curve else initial_capital
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)

    # Trade-level
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (
        (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    )
    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (-gross_loss / len(losses)) if losses else 0.0
    avg_score = sum(t.score for t in trades) / len(trades) if trades else 0.0

    return {
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(win_rate, 3),
        "profit_factor": round(profit_factor, 3) if math.isfinite(profit_factor) else 999.0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_score": round(avg_score, 1),
    }


class Backtester:
    """Runs a backtest — one-shot or WITH-vs-WITHOUT comparison."""

    def __init__(
        self,
        cfg: BacktestConfig | float | int | None = None,
        fee_bps: float | None = None,
        bankroll: float | None = None,
    ):
        if isinstance(cfg, BacktestConfig):
            base_cfg = cfg
        elif isinstance(cfg, (int, float)):
            if bankroll is not None:
                raise TypeError("bankroll cannot be provided twice")
            base_cfg = BacktestConfig(initial_capital=float(cfg))
        elif cfg is None:
            base_cfg = BacktestConfig()
        else:
            raise TypeError(f"unsupported Backtester config type: {type(cfg).__name__}")

        if bankroll is not None or fee_bps is not None:
            base_cfg = replace(
                base_cfg,
                initial_capital=float(bankroll)
                if bankroll is not None
                else base_cfg.initial_capital,
                fee_bps=float(fee_bps) if fee_bps is not None else base_cfg.fee_bps,
            )

        self.cfg = base_cfg

    def run_symbol(self, symbol: str, *, with_regime: bool) -> BacktestResult:
        bars = _load_ohlcv(symbol, self.cfg.period_days)
        signals = _generate_signals(bars, self.cfg)
        for s in signals:
            s["symbol"] = symbol
        trades, curve = _simulate(bars, signals, self.cfg, with_regime=with_regime)
        m = _metrics(curve, trades, self.cfg.initial_capital)
        final = curve[-1] if curve else self.cfg.initial_capital
        total_ret = ((final - self.cfg.initial_capital) / self.cfg.initial_capital) * 100

        # Buy-and-hold benchmark for the same window, scaled to initial capital.
        benchmark_curve: list[tuple[str, float]] = []
        if bars:
            start_px = bars[0]["close"] or 1.0
            for b in bars:
                benchmark_curve.append(
                    (b["date"], self.cfg.initial_capital * (b["close"] / start_px))
                )
        equity_pairs = [(b["date"], v) for b, v in zip(bars, curve, strict=False)]
        return BacktestResult(
            symbol=symbol,
            regime_enhancement=with_regime,
            period_days=self.cfg.period_days,
            bar_count=len(bars),
            trade_count=len(trades),
            final_equity=round(final, 2),
            total_return_pct=round(total_ret, 2),
            sharpe=m["sharpe"],
            sortino=m["sortino"],
            max_drawdown_pct=round(m["max_drawdown"] * 100, 2),
            win_rate=m["win_rate"],
            profit_factor=m["profit_factor"],
            avg_win=m["avg_win"],
            avg_loss=m["avg_loss"],
            avg_score=m["avg_score"],
            trades=trades,
            equity_curve=equity_pairs,
            benchmark_curve=benchmark_curve,
        )

    def run_comparison(self, symbols: list[str] | None = None) -> dict[str, Any]:
        """Run WITH-regime vs WITHOUT-regime across symbols and report delta."""
        syms = symbols or list(self.cfg.symbols)
        out: dict[str, Any] = {
            "config": asdict(self.cfg) | {"output_dir": str(self.cfg.output_dir)},
            "timestamp": datetime.now(UTC).isoformat(),
            "with_regime": {},
            "without_regime": {},
            "delta": {},
        }
        for sym in syms:
            try:
                r_on = self.run_symbol(sym, with_regime=True)
                r_off = self.run_symbol(sym, with_regime=False)
            except Exception as e:
                out["with_regime"][sym] = {"error": str(e)}
                out["without_regime"][sym] = {"error": str(e)}
                continue
            out["with_regime"][sym] = _result_to_dict(r_on)
            out["without_regime"][sym] = _result_to_dict(r_off)
            out["delta"][sym] = {
                "total_return_pct": round(r_on.total_return_pct - r_off.total_return_pct, 2),
                "sharpe": round(r_on.sharpe - r_off.sharpe, 3),
                "sortino": round(r_on.sortino - r_off.sortino, 3),
                "max_drawdown_pct": round(r_on.max_drawdown_pct - r_off.max_drawdown_pct, 2),
                "win_rate": round(r_on.win_rate - r_off.win_rate, 3),
                "profit_factor": round(r_on.profit_factor - r_off.profit_factor, 3)
                if math.isfinite(r_on.profit_factor) and math.isfinite(r_off.profit_factor)
                else 0.0,
                "trade_count": r_on.trade_count - r_off.trade_count,
            }
        return out

    def save(self, results: dict[str, Any]) -> Path:
        self.cfg.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = self.cfg.output_dir / f"backtest_{stamp}.json"
        path.write_text(json.dumps(results, indent=2, default=str))
        latest = self.cfg.output_dir / "latest.json"
        latest.write_text(json.dumps(results, indent=2, default=str))
        return path


def _result_to_dict(r: BacktestResult) -> dict[str, Any]:
    d = asdict(r)
    d["trades"] = [asdict(t) for t in r.trades]
    # profit_factor may be inf when no losses
    if not math.isfinite(d["profit_factor"]):
        d["profit_factor"] = 999.0
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sapphire backtesting engine")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--no-save", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = BacktestConfig(
        symbols=tuple(s.strip() for s in args.symbols.split(",") if s.strip()),
        period_days=args.days,
        output_dir=Path(args.out),
    )
    bt = Backtester(cfg)
    results = bt.run_comparison()
    if not args.no_save:
        path = bt.save(results)
        log.info("backtest results saved → %s", path)
    # Print compact summary
    for sym in cfg.symbols:
        d = results["delta"].get(sym, {})
        on = results["with_regime"].get(sym, {})
        off = results["without_regime"].get(sym, {})
        if "error" in on:
            print(f"{sym}: ERROR {on['error']}")
            continue
        print(
            f"{sym}: return {off.get('total_return_pct', 0):+.2f}% → {on.get('total_return_pct', 0):+.2f}% "
            f"(Δ{d.get('total_return_pct', 0):+.2f}pp) · "
            f"Sharpe {off.get('sharpe', 0):.2f}→{on.get('sharpe', 0):.2f} · "
            f"trades {off.get('trade_count', 0)}→{on.get('trade_count', 0)}"
        )
    return 0


# ---------------------------------------------------------------------------
# Public aliases expected by strategies.py and run_strategies.py
# ---------------------------------------------------------------------------

BacktestReport = BacktestResult
load_yfinance_ohlcv = _load_ohlcv


if __name__ == "__main__":
    raise SystemExit(main())
