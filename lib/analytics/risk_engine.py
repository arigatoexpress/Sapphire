"""Portfolio risk engine.

Computes production-grade risk metrics from closed-trade history:
  - Sharpe, Sortino, Calmar (annualized)
  - Max drawdown (% and duration in days)
  - Win rate, profit factor, avg win/loss, expectancy
  - Kelly fraction + quarter-Kelly recommended position size

Data sources (unified into a single closed-trade stream):
  - data/paper_trading.jsonl  (paper_outcome / paper_pnl_usd)
  - data/signals/YYYY-MM-DD.jsonl  (outcome / pnl_usd)
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PAPER_LOG = ROOT / "data" / "paper_trading.jsonl"
SIGNALS_DIR = ROOT / "data" / "signals"

# Annualisation factor (crypto trades 365 days/year)
TRADING_DAYS_PER_YEAR = 365
RISK_FREE_RATE = 0.045  # annual rate for Sharpe numerator

# Defaults for Kelly when data is thin
DEFAULT_WIN_RATE = 0.55
DEFAULT_RR = 1.5  # avg_win / avg_loss


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    timestamp: str
    symbol: str
    direction: str
    outcome: str  # win | loss | break_even
    pnl_usd: float
    position_usd: float
    source: str  # "signals" | "paper"


@dataclass
class PortfolioMetrics:
    # Core counts
    total_trades: int
    wins: int
    losses: int
    breakevens: int

    # Profitability
    total_pnl_usd: float
    win_rate: float | None
    profit_factor: float | None
    avg_win: float
    avg_loss: float
    expectancy: float  # average $ per trade (signed)

    # Risk-adjusted returns (annualized)
    sharpe: float | None
    sortino: float | None
    calmar: float | None

    # Drawdown
    max_drawdown_pct: float
    max_drawdown_usd: float
    max_drawdown_duration_days: int
    current_drawdown_pct: float

    # Position sizing
    kelly_fraction: float  # raw Kelly
    kelly_quarter: float  # quarter-Kelly (conservative default)
    recommended_size_usd: float

    # Equity curve for chart rendering
    equity_curve: list[dict] = field(default_factory=list)
    # [{timestamp, equity_usd, pnl_usd, drawdown_pct}]

    # Metadata
    bankroll: float = 10000.0
    computed_at: str = ""
    source_files: int = 0


# ---------------------------------------------------------------------------
# Kelly sizing (standalone)
# ---------------------------------------------------------------------------


def kelly_size(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    bankroll: float,
    mode: str = "quarter",
) -> float:
    """Kelly-optimal position size in dollars.

    f* = p − (1 − p) / (W / L)      where W = avg_win, L = avg_loss (>0)

    Modes:
      - "full"    → raw Kelly (aggressive)
      - "half"    → half-Kelly
      - "quarter" → quarter-Kelly (recommended — drawdown-tolerant)
    """
    if avg_loss <= 0 or win_rate <= 0 or bankroll <= 0:
        return 0.0
    p = max(0.0, min(1.0, win_rate))
    rr = avg_win / avg_loss
    if rr <= 0:
        return 0.0
    f = p - (1.0 - p) / rr
    if f <= 0:
        return 0.0
    if mode == "full":
        frac = f
    elif mode == "half":
        frac = f * 0.5
    else:
        frac = f * 0.25
    # Cap at 25% of bankroll even for full-Kelly — no single-trade ruin
    frac = min(frac, 0.25)
    return round(frac * bankroll, 2)


# ---------------------------------------------------------------------------
# RiskEngine
# ---------------------------------------------------------------------------


class RiskEngine:
    """Aggregates closed trades and computes portfolio-level risk metrics."""

    def __init__(self, bankroll: float = 10000.0):
        self.bankroll = bankroll

    # ------------------------------------------------------------------

    def _load_trades(self) -> list[Trade]:
        trades: list[Trade] = []

        # Paper trading log
        if PAPER_LOG.exists():
            for line in PAPER_LOG.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                outcome = r.get("paper_outcome")
                if outcome in {"win", "loss", "break_even"}:
                    trades.append(
                        Trade(
                            timestamp=r.get("closed_at") or r.get("timestamp", ""),
                            symbol=r.get("symbol", "?"),
                            direction=r.get("direction", "?"),
                            outcome=outcome,
                            pnl_usd=float(r.get("paper_pnl_usd") or 0.0),
                            position_usd=float(r.get("position_usd") or 0.0),
                            source="paper",
                        )
                    )

        # Signal audit files — closed positions have outcome + pnl_usd
        files = sorted(SIGNALS_DIR.glob("*.jsonl")) if SIGNALS_DIR.exists() else []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
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
                    trades.append(
                        Trade(
                            timestamp=r.get("closed_at") or r.get("timestamp", ""),
                            symbol=r.get("symbol", "?"),
                            direction=r.get("direction", "?"),
                            outcome=outcome,
                            pnl_usd=float(r.get("pnl_usd") or 0.0),
                            position_usd=float(r.get("position_usd") or 0.0),
                            source="signals",
                        )
                    )

        # Parse timestamps for a stable chronological sort. Lexicographic sort
        # breaks when inputs mix "...+00:00" and "...Z" suffixes (the latter
        # sorts before the former for the same instant, producing out-of-order
        # equity curves and bad drawdown-duration math).
        def _ts_key(t: Trade) -> datetime:
            raw = t.timestamp or ""
            if not raw:
                return datetime.min.replace(tzinfo=UTC)
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=UTC)

        trades.sort(key=_ts_key)
        return trades

    # ------------------------------------------------------------------

    def compute(self) -> PortfolioMetrics:
        trades = self._load_trades()
        n = len(trades)
        wins = [t for t in trades if t.outcome == "win"]
        losses = [t for t in trades if t.outcome == "loss"]
        breakevens = [t for t in trades if t.outcome == "break_even"]

        total_pnl = round(sum(t.pnl_usd for t in trades), 2)
        win_pnls = [t.pnl_usd for t in wins]
        loss_pnls = [abs(t.pnl_usd) for t in losses]

        # Win rate
        decisive = len(wins) + len(losses)
        win_rate = (len(wins) / decisive) if decisive > 0 else None

        # Avg win/loss / expectancy
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
        expectancy = (total_pnl / n) if n > 0 else 0.0

        # Profit factor
        pf = None
        total_win = sum(win_pnls)
        total_loss = sum(loss_pnls)
        if total_loss > 0:
            pf = round(total_win / total_loss, 3)
        elif total_win > 0:
            pf = float("inf")

        # Equity curve + drawdown
        equity_curve: list[dict] = []
        equity = self.bankroll
        peak = equity
        # Seed peak_ts with the first trade's timestamp so a losing first
        # trade still produces a non-zero drawdown duration (prior code
        # only set peak_ts inside `if equity > peak`, leaving it None forever
        # when the first trade was a loss).
        peak_ts: str | None = trades[0].timestamp if trades else None
        max_dd_pct = 0.0
        max_dd_usd = 0.0
        max_dd_duration = 0
        current_dd_pct = 0.0

        for t in trades:
            equity = round(equity + t.pnl_usd, 2)
            if equity > peak:
                peak = equity
                peak_ts = t.timestamp
            dd_usd = peak - equity
            dd_pct = (dd_usd / peak) if peak > 0 else 0.0
            # Duration in days since peak
            duration = 0
            if peak_ts and t.timestamp:
                try:
                    p = datetime.fromisoformat(peak_ts.replace("Z", "+00:00"))
                    c = datetime.fromisoformat(t.timestamp.replace("Z", "+00:00"))
                    duration = max(0, (c - p).days)
                except (ValueError, TypeError):
                    pass
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_usd = dd_usd
                max_dd_duration = duration
            equity_curve.append(
                {
                    "timestamp": t.timestamp,
                    "equity_usd": equity,
                    "pnl_usd": round(t.pnl_usd, 2),
                    "drawdown_pct": round(dd_pct, 4),
                }
            )
            current_dd_pct = dd_pct

        # Sharpe / Sortino — from per-trade returns as % of bankroll
        sharpe = sortino = calmar = None
        if n >= 2:
            pct_rets = [(t.pnl_usd / self.bankroll) for t in trades]
            mean_r = sum(pct_rets) / n
            # Sample std
            var = sum((r - mean_r) ** 2 for r in pct_rets) / (n - 1)
            std = math.sqrt(var)
            # Downside deviation for Sortino — standard form divides by the
            # full sample count (n), not len(downside). The loss-count
            # denominator systematically understates Sortino for profitable
            # strategies. Use MAR=0 and measure deviation of returns below
            # MAR against the full population.
            downside_sq = [(max(0.0, -r)) ** 2 for r in pct_rets]
            dvar = sum(downside_sq) / n
            dstd = math.sqrt(dvar)

            # Assume trades-per-day from the span of history
            tpd = self._trades_per_day(trades)
            annualise = tpd * TRADING_DAYS_PER_YEAR
            rf_per_trade = RISK_FREE_RATE / (TRADING_DAYS_PER_YEAR * max(1, tpd))

            if std > 0:
                sharpe = round(((mean_r - rf_per_trade) / std) * math.sqrt(annualise), 3)
            if dstd > 0:
                sortino = round(((mean_r - rf_per_trade) / dstd) * math.sqrt(annualise), 3)

            # Calmar = annualised return / max drawdown
            annual_return = mean_r * annualise
            if max_dd_pct > 0:
                calmar = round(annual_return / max_dd_pct, 3)

        # Kelly / recommended size (fall back to defaults when thin)
        if win_rate is not None and avg_win > 0 and avg_loss > 0:
            k_win_rate = win_rate
            k_avg_win = avg_win
            k_avg_loss = avg_loss
        else:
            k_win_rate = DEFAULT_WIN_RATE
            k_avg_win = DEFAULT_RR
            k_avg_loss = 1.0

        # Raw Kelly fraction (for display) — capped at 0.25 to match the
        # invariant enforced by kelly_size() for `recommended`. Without this
        # cap the dashboard would show a Kelly fraction that never maps to
        # the recommended size (e.g. raw 0.8 vs recommended capped at 0.25).
        rr = k_avg_win / k_avg_loss if k_avg_loss > 0 else 0.0
        raw_kelly_uncapped = max(0.0, k_win_rate - (1 - k_win_rate) / rr) if rr > 0 else 0.0
        raw_kelly = min(raw_kelly_uncapped, 0.25)
        quarter_kelly = raw_kelly * 0.25
        recommended = kelly_size(k_win_rate, k_avg_win, k_avg_loss, self.bankroll, mode="quarter")

        return PortfolioMetrics(
            total_trades=n,
            wins=len(wins),
            losses=len(losses),
            breakevens=len(breakevens),
            total_pnl_usd=total_pnl,
            win_rate=round(win_rate, 3) if win_rate is not None else None,
            profit_factor=pf,
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            expectancy=round(expectancy, 2),
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_duration_days=max_dd_duration,
            current_drawdown_pct=round(current_dd_pct, 4),
            kelly_fraction=round(raw_kelly, 4),
            kelly_quarter=round(quarter_kelly, 4),
            recommended_size_usd=recommended,
            equity_curve=equity_curve,
            bankroll=self.bankroll,
            computed_at=datetime.now(UTC).isoformat(),
            source_files=1
            + (len(list(SIGNALS_DIR.glob("*.jsonl"))) if SIGNALS_DIR.exists() else 0),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _trades_per_day(trades: list[Trade]) -> int:
        """Estimate trading frequency from history span."""
        if len(trades) < 2:
            return 1
        try:
            first = datetime.fromisoformat(trades[0].timestamp.replace("Z", "+00:00"))
            last = datetime.fromisoformat(trades[-1].timestamp.replace("Z", "+00:00"))
            days = max(1, (last - first).days)
            return max(1, round(len(trades) / days))
        except (ValueError, TypeError):
            return 1


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    eng = RiskEngine(bankroll=10000.0)
    m = eng.compute()
    print(f"=== Portfolio Metrics ({m.total_trades} trades) ===")
    print(f"Win rate:       {m.win_rate}  ({m.wins}W / {m.losses}L / {m.breakevens}BE)")
    print(f"Total PnL:      ${m.total_pnl_usd:+,.2f}")
    print(f"Profit factor:  {m.profit_factor}")
    print(f"Avg win/loss:   +${m.avg_win:.2f} / -${m.avg_loss:.2f}")
    print(f"Expectancy:     ${m.expectancy:+.2f}/trade")
    print()
    print(f"Sharpe:         {m.sharpe}")
    print(f"Sortino:        {m.sortino}")
    print(f"Calmar:         {m.calmar}")
    print()
    print(
        f"Max drawdown:   {m.max_drawdown_pct:.2%}  (-${m.max_drawdown_usd:,.2f}, "
        f"{m.max_drawdown_duration_days}d)"
    )
    print(f"Current DD:     {m.current_drawdown_pct:.2%}")
    print()
    print(f"Kelly raw:      {m.kelly_fraction:.4f}")
    print(f"Kelly 1/4:      {m.kelly_quarter:.4f}")
    print(f"Recommended:    ${m.recommended_size_usd:,.2f}")
