"""Multi-strategy backtesting framework for Sapphire.

Strategy hierarchy (all derive from Strategy ABC):
  RegimeAwareRSI        — RSI only in RISK_ON / TRANSITION regimes
  FundingRateContrarian — contrarian on 3-day momentum as funding proxy
  CorrelationBreakout   — long when BTC↔SPY correlation drops below threshold
  MultiTFMomentum       — short / medium / long TF proxies must all agree
  SapphireComposite     — 0–100 score from all components; Kelly position sizing

Core classes:
  StrategyParams  — shared dataclass swept across the grid
  Strategy        — ABC; subclasses implement on_bar(window, aux)
  BacktestEngine  — wraps Backtester, aligns aux data, drives Strategy instances
  SweepResult     — single param-combo × symbol result
  sweep_params()  — 27-combo grid × symbols
  best_per_symbol() — pick best Sortino per (cls, symbol)
  compare()       — sort results by Sortino
  format_table()  — fixed-width ASCII comparison table
  save_results()  — JSON → data/backtests/strategies/
"""

from __future__ import annotations

import abc
import itertools
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import (
    BacktestReport,
    Bar,
    Decision,
)

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "data" / "backtests" / "strategies"


# ---------------------------------------------------------------------------
# Standalone indicators (no soft deps)
# ---------------------------------------------------------------------------


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas[-period:]]
    losses = [max(-d, 0.0) for d in deltas[-period:]]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _daily_returns(bars: list[Bar]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(bars)):
        prev = bars[i - 1].close
        if prev > 0:
            out.append((bars[i].close - prev) / prev)
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    var_a = sum((x - ma) ** 2 for x in a)
    var_b = sum((x - mb) ** 2 for x in b)
    denom = math.sqrt(var_a * var_b)
    return cov / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# StrategyParams — shared across all strategies; grid keys are the 3 swept dims
# ---------------------------------------------------------------------------


@dataclass
class StrategyParams:
    # ── swept dimensions ──────────────────────────────────────────────────
    rsi_period: int = 14
    sl_pct: float = 0.05
    tp_pct: float = 0.10

    # ── regime (RegimeAwareRSI, SapphireComposite) ────────────────────────
    regime_period: int = 20
    regime_on_threshold: float = 0.05  # BTC 20d return > +5% → RISK_ON
    regime_off_threshold: float = -0.05  # BTC 20d return < -5% → RISK_OFF

    # ── funding proxy (FundingRateContrarian, SapphireComposite) ─────────
    funding_high: float = 0.020  # 3d momentum > +2% → high funding → short
    funding_low: float = -0.015  # 3d momentum < -1.5% → neg funding → long

    # ── correlation (CorrelationBreakout, SapphireComposite) ──────────────
    corr_period: int = 20
    corr_threshold: float = 0.30  # corr below this = crypto decoupled from SPY

    # ── multi-TF (MultiTFMomentum, SapphireComposite) ─────────────────────
    tf_fast: int = 7  # short RSI period (4H proxy)
    tf_slow: int = 5  # weekly bar count

    # ── composite gate ────────────────────────────────────────────────────
    # 55 is viable in RISK_OFF + correlated market (regime=0, no corr pts, need
    # RSI+funding+multiTF ≥55). 70 is only reachable in RISK_ON bull regimes.
    composite_threshold: float = 55.0


PARAM_GRID: dict[str, list] = {
    "rsi_period": [7, 14, 21],
    "sl_pct": [0.02, 0.05, 0.08],
    "tp_pct": [0.05, 0.10, 0.15],
}

# Additional dim for SapphireComposite (not in PARAM_GRID to avoid 4D explosion;
# swept separately in run_strategies via composite_threshold_range)
COMPOSITE_THRESHOLDS = [45.0, 55.0, 65.0]


# ---------------------------------------------------------------------------
# Strategy ABC
# ---------------------------------------------------------------------------


class Strategy(abc.ABC):
    """Abstract base for all Sapphire backtesting strategies.

    on_bar() receives the price history up to and including the current bar,
    plus a dict of aligned auxiliary series:
      aux["btc"]  — BTC-USD bars (for regime detection in non-BTC strategies)
      aux["spy"]  — SPY bars (for BTC↔SPY correlation)

    Return a Decision or None to stay flat.
    """

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    def on_bar(
        self,
        window: list[Bar],
        aux: dict[str, list[Bar]],
    ) -> Decision | None: ...

    def params_summary(self) -> str:
        p = self.params
        return f"rsi={p.rsi_period} sl={p.sl_pct:.0%} tp={p.tp_pct:.0%}"


# ---------------------------------------------------------------------------
# Strategy 1: Regime-Aware RSI
# ---------------------------------------------------------------------------


class RegimeAwareRSI(Strategy):
    """RSI mean-reversion gated by simulated BTC market regime.

    Regime is derived from the 20-day return of BTC (aux["btc"]) or the
    symbol's own price series if BTC bars are unavailable.

    RISK_ON  → enter on RSI < 30 (standard oversold)
    TRANSITION → stricter, RSI < 25
    RISK_OFF → no new entries (flat signal)
    """

    @property
    def name(self) -> str:
        p = self.params
        return f"RegimeAwareRSI(p={p.rsi_period},sl={p.sl_pct:.0%},tp={p.tp_pct:.0%})"

    def _detect_regime(self, bars: list[Bar]) -> str:
        rp = self.params.regime_period
        if len(bars) < rp + 1:
            return "TRANSITION"
        old = bars[-(rp + 1)].close
        new = bars[-1].close
        mom = (new - old) / old if old > 0 else 0.0
        if mom >= self.params.regime_on_threshold:
            return "RISK_ON"
        if mom <= self.params.regime_off_threshold:
            return "RISK_OFF"
        return "TRANSITION"

    def on_bar(self, window: list[Bar], aux: dict[str, list[Bar]]) -> Decision | None:
        p = self.params
        min_bars = p.rsi_period + p.regime_period + 2
        if len(window) < min_bars:
            return None

        regime = self._detect_regime(aux.get("btc") or window)
        if regime == "RISK_OFF":
            return Decision(direction="flat")

        closes = [b.close for b in window]
        rsi = _rsi(closes, p.rsi_period)
        if rsi is None:
            return None

        # Stricter entry threshold during uncertain regime
        threshold = 30.0 if regime == "RISK_ON" else 25.0

        if rsi < threshold:
            return Decision(direction="long", size=0.5, stop_pct=p.sl_pct, tp_pct=p.tp_pct)
        if rsi > 70.0:
            return Decision(direction="flat")
        return None


# ---------------------------------------------------------------------------
# Strategy 2: Funding Rate Contrarian
# ---------------------------------------------------------------------------


class FundingRateContrarian(Strategy):
    """Contrarian entries using 3-day price momentum as a funding-rate proxy.

    Crypto perpetuals charge positive funding when longs crowd in (positive
    momentum). A proxy: if 3-day return exceeds funding_high → crowded long
    → fade with a short. If below funding_low → crowded short → fade long.

    Signals exit when momentum mean-reverts (RSI crosses back through 50).
    """

    @property
    def name(self) -> str:
        p = self.params
        return f"FundingContrarian(sl={p.sl_pct:.0%},tp={p.tp_pct:.0%})"

    def on_bar(self, window: list[Bar], aux: dict[str, list[Bar]]) -> Decision | None:
        if len(window) < 5:
            return None

        closes = [b.close for b in window]
        c0 = closes[-4]
        mom_3d = (closes[-1] - c0) / c0 if c0 > 0 else 0.0
        p = self.params

        if mom_3d > p.funding_high:
            # High simulated funding → crowded long → contrarian short
            return Decision(direction="short", size=0.4, stop_pct=p.sl_pct, tp_pct=p.tp_pct)
        if mom_3d < p.funding_low:
            # Negative funding → crowded short → contrarian long
            return Decision(direction="long", size=0.4, stop_pct=p.sl_pct, tp_pct=p.tp_pct)
        return None


# ---------------------------------------------------------------------------
# Strategy 3: Correlation Breakout
# ---------------------------------------------------------------------------


class CorrelationBreakout(Strategy):
    """Long when BTC↔SPY rolling correlation drops below corr_threshold.

    When crypto decouples from equities (corr < 0.3), it often signals
    idiosyncratic price discovery — combine with RSI oversold for high-quality
    entries. Uses aux["spy"] for SPY bars.
    """

    @property
    def name(self) -> str:
        p = self.params
        return f"CorrBreakout(sl={p.sl_pct:.0%},tp={p.tp_pct:.0%})"

    def on_bar(self, window: list[Bar], aux: dict[str, list[Bar]]) -> Decision | None:
        p = self.params
        n = p.corr_period
        if len(window) < n + 2:
            return None

        spy_bars = aux.get("spy") or []
        if len(spy_bars) < n + 1:
            return None

        sym_rets = _daily_returns(window[-(n + 1) :])[-n:]
        spy_rets = _daily_returns(spy_bars[-(n + 1) :])[-n:]
        if len(sym_rets) < n or len(spy_rets) < n:
            return None

        corr = _pearson(sym_rets, spy_rets)
        closes = [b.close for b in window]
        rsi = _rsi(closes, p.rsi_period)
        if rsi is None:
            return None

        if corr < p.corr_threshold:
            if rsi < 45.0:
                # Decoupled + oversold → high-quality long setup
                return Decision(direction="long", size=0.6, stop_pct=p.sl_pct, tp_pct=p.tp_pct)
            if rsi > 65.0:
                return Decision(direction="flat")
        return None


# ---------------------------------------------------------------------------
# Strategy 4: Multi-TF Momentum
# ---------------------------------------------------------------------------


class MultiTFMomentum(Strategy):
    """All three timeframe proxies must agree before entering.

    With daily bars we approximate three timeframes:
      4H proxy    — RSI(7): more responsive oscillator signals short-term stress
      Daily MA    — 20-day SMA: trend context; price below MA = bearish trend
      Weekly mom  — 5-day return: negative = potential weekly reversal

    Bullish entry: fast RSI < 40 AND price < 20-SMA AND 5d return < 0
    (All three: short-term oversold, below daily MA, weekly pullback)
    """

    @property
    def name(self) -> str:
        p = self.params
        return f"MultiTFMomentum(p={p.rsi_period},sl={p.sl_pct:.0%},tp={p.tp_pct:.0%})"

    def on_bar(self, window: list[Bar], aux: dict[str, list[Bar]]) -> Decision | None:
        p = self.params
        if len(window) < 22:
            return None

        closes = [b.close for b in window]

        rsi_fast = _rsi(closes, p.tf_fast)
        sma20 = _sma(closes, 20)
        if rsi_fast is None or sma20 is None:
            return None

        weekly_ret = 0.0
        if len(closes) >= p.tf_slow + 1:
            prev_w = closes[-(p.tf_slow + 1)]
            weekly_ret = (closes[-1] - prev_w) / prev_w if prev_w > 0 else 0.0

        bull = rsi_fast < 40.0 and closes[-1] < sma20 and weekly_ret < 0.0
        bear = rsi_fast > 65.0 and closes[-1] > sma20 * 1.02 and weekly_ret > 0.02

        if bull:
            return Decision(direction="long", size=0.5, stop_pct=p.sl_pct, tp_pct=p.tp_pct)
        if bear:
            return Decision(direction="flat")
        return None


# ---------------------------------------------------------------------------
# Strategy 5: Sapphire Composite
# ---------------------------------------------------------------------------


class SapphireComposite(Strategy):
    """Composite signal scored 0–100. Only trade when score > composite_threshold.

    Score components:
      Regime          0–25   RISK_ON=25, TRANSITION=15, RISK_OFF=0
      RSI depth       0–25   linear: RSI=30→0 pts, RSI=10→25 pts
      Funding proxy   0–20   negative funding → bullish
      Correlation     0–15   lower BTC↔SPY corr → more pts
      Multi-TF align  0–15   fraction of TF signals agreeing × 15

    Position size: quarter-Kelly using tp/sl ratio and 55% default win rate.
    """

    @property
    def name(self) -> str:
        p = self.params
        return f"SapphireComposite(p={p.rsi_period},sl={p.sl_pct:.0%},tp={p.tp_pct:.0%})"

    def _kelly_size(self) -> float:
        """Quarter-Kelly fraction using tp/sl as reward:risk proxy."""
        p = self.params
        win_prob = 0.55
        b = p.tp_pct / p.sl_pct if p.sl_pct > 0 else 2.0
        f = win_prob - (1.0 - win_prob) / b
        return max(0.05, min(0.50, round(f * 0.25, 3)))

    def on_bar(self, window: list[Bar], aux: dict[str, list[Bar]]) -> Decision | None:
        p = self.params
        min_bars = max(p.rsi_period + 1, p.regime_period + 1, p.corr_period + 2, 22)
        if len(window) < min_bars:
            return None

        score = 0.0

        # ── Component 1: Regime (0–25) ────────────────────────────────────
        regime_bars = aux.get("btc") or window
        rp = p.regime_period
        if len(regime_bars) >= rp + 1:
            old = regime_bars[-(rp + 1)].close
            new = regime_bars[-1].close
            mom = (new - old) / old if old > 0 else 0.0
            if mom >= p.regime_on_threshold:
                score += 25.0
            elif mom > p.regime_off_threshold:
                score += 15.0

        # ── Component 2: RSI depth (0–25) ────────────────────────────────
        closes = [b.close for b in window]
        rsi = _rsi(closes, p.rsi_period)
        if rsi is not None:
            if rsi < 30.0:
                score += min(25.0, (30.0 - rsi) * 25.0 / 20.0)
            elif rsi > 70.0:
                score -= 5.0

        # ── Component 3: Funding proxy (0–20) ────────────────────────────
        if len(closes) >= 5:
            c0 = closes[-4]
            mom_3d = (closes[-1] - c0) / c0 if c0 > 0 else 0.0
            if mom_3d < p.funding_low:
                score += min(20.0, abs(mom_3d) * 300.0)
            elif mom_3d > p.funding_high:
                score -= 5.0

        # ── Component 4: Correlation decoupling (0–15) ───────────────────
        spy_bars = aux.get("spy") or []
        n = p.corr_period
        if len(spy_bars) >= n + 1 and len(window) >= n + 2:
            sym_rets = _daily_returns(window[-(n + 1) :])[-n:]
            spy_rets = _daily_returns(spy_bars[-(n + 1) :])[-n:]
            if len(sym_rets) >= n and len(spy_rets) >= n:
                corr = _pearson(sym_rets, spy_rets)
                if corr < p.corr_threshold:
                    score += min(15.0, (p.corr_threshold - corr) * 50.0)

        # ── Component 5: Multi-TF alignment (0–15) ───────────────────────
        rsi_fast = _rsi(closes, p.tf_fast) if len(closes) >= p.tf_fast + 1 else None
        sma20 = _sma(closes, 20) if len(closes) >= 20 else None
        tf_sig, tf_tot = 0, 0

        if rsi_fast is not None:
            tf_tot += 1
            if rsi_fast < 40.0:
                tf_sig += 1
        if sma20 is not None:
            tf_tot += 1
            if closes[-1] < sma20:
                tf_sig += 1
        if len(closes) >= p.tf_slow + 1:
            tf_tot += 1
            prev_w = closes[-(p.tf_slow + 1)]
            if prev_w > 0 and (closes[-1] - prev_w) / prev_w < 0.0:
                tf_sig += 1

        if tf_tot > 0:
            score += 15.0 * tf_sig / tf_tot

        if score < p.composite_threshold:
            return None

        return Decision(
            direction="long",
            size=self._kelly_size(),
            stop_pct=p.sl_pct,
            tp_pct=p.tp_pct,
        )


# ---------------------------------------------------------------------------
# All strategy classes in one list for sweep runners
# ---------------------------------------------------------------------------

ALL_STRATEGIES: list[type[Strategy]] = [
    RegimeAwareRSI,
    FundingRateContrarian,
    CorrelationBreakout,
    MultiTFMomentum,
    SapphireComposite,
]


# ---------------------------------------------------------------------------
# BacktestEngine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Drives Strategy instances through the backtest_engine runner.

    Handles date-aligned aux data so strategies can reference BTC / SPY
    bars at the correct historical window index.

    Adapts Strategy.on_bar (returning Decision) to backtest_engine.run_backtest
    (expecting a signal_fn that returns a raw dict). The old backtest.py
    Backtester API was replaced with a regime-comparison runner that doesn't
    accept arbitrary strategy functions, so we wrap run_backtest here.
    """

    def __init__(self, bankroll: float = 10_000.0, fee_bps: float = 5.0) -> None:
        from lib.analytics.backtest import BacktestConfig

        self.backtest_config = BacktestConfig(
            initial_capital=float(bankroll),
            fee_bps=float(fee_bps),
        )
        self.bankroll = self.backtest_config.initial_capital
        self.fee_bps = (
            self.backtest_config.fee_bps
        )  # kept for API compat; run_backtest applies no fees

    def run(
        self,
        bars,
        strategy: Strategy,
        symbol: str = "?",
        aux_data: dict | None = None,
    ):
        """Run strategy against bars. Returns an object exposing the same
        fields as the old BacktestReport (sortino, sharpe, win_rate,
        profit_factor, max_drawdown_pct, calmar, total_return_pct,
        total_trades).
        """
        from lib.analytics.backtest_engine import run_backtest

        aligned = self._align_aux(bars, aux_data or {})

        def sig_fn(sym, window, i):
            # window is backtest_engine's bars list up to index i
            slice_window = window[: i + 1]
            aux_at_i = {k: v[: i + 1] for k, v in aligned.items()}
            # Strategy.on_bar was written against backtest.py's Bar (same
            # shape: .ts / .open / .close / etc.) — backtest_engine.Bar is
            # structurally compatible.
            decision = strategy.on_bar(slice_window, aux_at_i)
            if decision is None or getattr(decision, "direction", "flat") == "flat":
                return None
            price = window[i].close
            direction = decision.direction
            action = "buy" if direction == "long" else "sell" if direction == "short" else "close"
            out = {
                "symbol": sym,
                "action": action,
                "price": price,
                "confidence": 0.5,
                "strategy": strategy.name,
            }
            # Translate Decision stop/tp percents into absolute levels
            if getattr(decision, "stop_pct", 0.0):
                out["stop_loss"] = (
                    price * (1 - decision.stop_pct)
                    if direction == "long"
                    else price * (1 + decision.stop_pct)
                )
            if getattr(decision, "tp_pct", 0.0):
                out["take_profit"] = (
                    price * (1 + decision.tp_pct)
                    if direction == "long"
                    else price * (1 - decision.tp_pct)
                )
            return out

        result = run_backtest(
            symbol=symbol,
            bars=bars,
            signal_fn=sig_fn,
            initial_capital=self.bankroll,
        )

        # Project BacktestResult onto the fields strategies.py downstream code reads.
        # SweepResult / format_table / dashboard all expect fractions (0–1) for
        # win_rate / total_return_pct / max_drawdown_pct.
        #
        # Unit map (origin/main, post-#102):
        #   - win_rate:         already a fraction (PR #102 dropped the *100 in
        #                       backtest_engine._finalize) — pass through verbatim.
        #   - total_return_pct: still percent (0–100) — divide by 100.
        #   - max_drawdown_pct: still percent (0–100) — divide by 100.
        #
        # Previous version of this projection divided win_rate by 100 too, which
        # double-divided after #102 landed (50% → 0.005 instead of 0.5).
        from types import SimpleNamespace

        return SimpleNamespace(
            sortino=result.sortino,
            sharpe=result.sharpe,
            total_return_pct=result.total_return_pct / 100.0,
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            max_drawdown_pct=result.max_drawdown_pct / 100.0,
            calmar=result.calmar,
            total_trades=len(result.trades),
            report=result.to_dict(),
        )

    @staticmethod
    def _align_aux(
        main_bars,
        aux: dict,
    ) -> dict:
        """Forward-fill each aux series to match main_bars.

        _load_ohlcv in backtest.py returns list[dict] with 'date' string keys,
        not Bar instances. This helper handles both cases so strategies work
        whether the caller passes Bar dataclasses or raw yfinance dicts.
        """

        def _key(bar):
            if isinstance(bar, dict):
                return bar.get("date") or bar.get("ts")
            return getattr(bar, "ts", None) or getattr(bar, "date", None)

        result: dict = {}
        for key, aux_bars in aux.items():
            if not aux_bars:
                result[key] = []
                continue
            by_key = {_key(b): b for b in aux_bars}
            aligned = []
            last = aux_bars[0]
            for mb in main_bars:
                k = _key(mb)
                if k in by_key:
                    last = by_key[k]
                aligned.append(last)
            result[key] = aligned
        return result


# ---------------------------------------------------------------------------
# Sweep & compare
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    strategy_cls: str
    strategy_name: str
    symbol: str
    rsi_period: int
    sl_pct: float
    tp_pct: float
    sortino: float | None
    sharpe: float | None
    total_return_pct: float
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float
    calmar: float | None
    total_trades: int
    report: BacktestReport = field(repr=False)

    def to_dict(self, include_report: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "strategy_cls": self.strategy_cls,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "params": {
                "rsi_period": self.rsi_period,
                "sl_pct": self.sl_pct,
                "tp_pct": self.tp_pct,
            },
            "sortino": self.sortino,
            "sharpe": self.sharpe,
            "total_return_pct": self.total_return_pct,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "calmar": self.calmar,
            "total_trades": self.total_trades,
        }
        if include_report and self.report is not None:
            # .report may be a dataclass (old BacktestReport), a dict
            # (BacktestResult.to_dict()), or a SimpleNamespace wrapper from
            # BacktestEngine.run exposing .report as the dict payload.
            r = self.report
            if isinstance(r, dict):
                d["report"] = r
            elif hasattr(r, "report") and isinstance(r.report, dict):
                d["report"] = r.report
            else:
                try:
                    d["report"] = asdict(r)
                except TypeError:
                    d["report"] = vars(r) if hasattr(r, "__dict__") else {}
        return d


def sweep_params(
    strategy_cls: type[Strategy],
    symbols: list[str],
    bars_map: dict[str, list[Bar]],
    aux_map: dict[str, dict[str, list[Bar]]],
    bankroll: float = 10_000.0,
) -> list[SweepResult]:
    """Run 27-combo param grid across all symbols for one strategy class.

    Returns len(PARAM_GRID combos) × len(symbols) SweepResult objects.
    """
    engine = BacktestEngine(bankroll=bankroll)
    results: list[SweepResult] = []
    keys = list(PARAM_GRID.keys())

    for combo in itertools.product(*PARAM_GRID.values()):
        params = StrategyParams(**dict(zip(keys, combo, strict=False)))
        strat = strategy_cls(params)

        for sym in symbols:
            bars = bars_map.get(sym, [])
            if not bars:
                continue
            report = engine.run(bars, strat, sym, aux_map.get(sym, {}))
            results.append(
                SweepResult(
                    strategy_cls=strategy_cls.__name__,
                    strategy_name=strat.name,
                    symbol=sym,
                    rsi_period=params.rsi_period,
                    sl_pct=params.sl_pct,
                    tp_pct=params.tp_pct,
                    sortino=report.sortino,
                    sharpe=report.sharpe,
                    total_return_pct=report.total_return_pct,
                    win_rate=report.win_rate,
                    profit_factor=report.profit_factor,
                    max_drawdown_pct=report.max_drawdown_pct,
                    calmar=report.calmar,
                    total_trades=report.total_trades,
                    report=report,
                )
            )

    return results


def best_per_symbol(results: list[SweepResult]) -> list[SweepResult]:
    """Return the best-Sortino result for each (strategy_cls, symbol) pair."""
    grouped: dict[tuple[str, str], list[SweepResult]] = {}
    for r in results:
        grouped.setdefault((r.strategy_cls, r.symbol), []).append(r)

    return [
        max(candidates, key=lambda r: r.sortino if r.sortino is not None else -1e9)
        for candidates in grouped.values()
    ]


def compare(results: list[SweepResult]) -> list[SweepResult]:
    """Sort results by Sortino descending."""
    return sorted(results, key=lambda r: r.sortino if r.sortino is not None else -1e9, reverse=True)


def format_table(results: list[SweepResult], title: str = "", top_n: int = 60) -> str:
    hdr = (
        f"{'Strategy':<28} {'Symbol':<8} "
        f"{'Sortino':>7} {'Sharpe':>7} {'Return':>8} "
        f"{'WinR':>6} {'PF':>5} {'MaxDD':>6} "
        f"{'N':>4}  Params"
    )
    sep = "─" * len(hdr)
    lines: list[str] = []
    if title:
        lines += [title, "═" * len(title)]
    lines += [hdr, sep]

    for r in results[:top_n]:
        srt = f"{r.sortino:>7.2f}" if r.sortino is not None else "    n/a"
        shr = f"{r.sharpe:>7.2f}" if r.sharpe is not None else "    n/a"
        ret = f"{r.total_return_pct:>+8.2%}"
        wr = f"{r.win_rate:>5.1%}" if r.win_rate is not None else "  n/a"
        pf = f"{r.profit_factor:>5.2f}" if r.profit_factor is not None else "  n/a"
        dd = f"{r.max_drawdown_pct:>6.2%}"
        par = f"rsi={r.rsi_period} sl={r.sl_pct:.0%} tp={r.tp_pct:.0%}"
        lines.append(
            f"{r.strategy_cls[:28]:<28} {r.symbol:<8} "
            f"{srt} {shr} {ret} "
            f"{wr} {pf} {dd} "
            f"{r.total_trades:>4}  {par}"
        )

    return "\n".join(lines)


def save_results(
    results: list[SweepResult],
    tag: str = "",
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Persist all SweepResults to data/backtests/strategies/ as JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{tag}" if tag else ""
    path = RESULTS_DIR / f"strategy_sweep_{ts}{suffix}.json"
    payload = {
        "computed_at": datetime.now(UTC).isoformat(),
        "total_backtests": len(results),
        "results": [r.to_dict() for r in results],
    }
    if metadata:
        payload["metadata"] = metadata
    path.write_text(json.dumps(payload, indent=2))
    log.info("Saved %d results → %s", len(results), path)
    return path
