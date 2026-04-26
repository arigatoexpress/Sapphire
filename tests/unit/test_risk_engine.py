"""Unit tests — lib.analytics.risk_engine.

Covers the standalone `kelly_size` helper plus the `RiskEngine.compute()`
pipeline: trade ingestion (paper + signals JSONL), equity curve / drawdown,
Sharpe / Sortino / Calmar, and the recommended-size calculation.

The module reads from `PAPER_LOG` / `SIGNALS_DIR` at module scope, so each
test that exercises `compute()` monkeypatches those paths into a tmp dir.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.analytics import risk_engine as risk_engine_mod
from lib.analytics.risk_engine import (
    PortfolioMetrics,
    RiskEngine,
    Trade,
    kelly_size,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Redirect `PAPER_LOG` and `SIGNALS_DIR` to a tmp dir for isolation."""
    paper_log = tmp_path / "paper_trading.jsonl"
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    monkeypatch.setattr(risk_engine_mod, "PAPER_LOG", paper_log)
    monkeypatch.setattr(risk_engine_mod, "SIGNALS_DIR", signals_dir)
    return {"paper_log": paper_log, "signals_dir": signals_dir}


def _write_paper_trade(
    paper_log: Path,
    *,
    closed_at: str,
    symbol: str = "BTC",
    direction: str = "long",
    outcome: str = "win",
    pnl_usd: float = 100.0,
    position_usd: float = 1000.0,
) -> None:
    rec = {
        "closed_at": closed_at,
        "symbol": symbol,
        "direction": direction,
        "paper_outcome": outcome,
        "paper_pnl_usd": pnl_usd,
        "position_usd": position_usd,
    }
    with paper_log.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _write_signal_trade(
    signals_dir: Path,
    *,
    closed_at: str,
    symbol: str = "BTC",
    direction: str = "long",
    outcome: str = "win",
    pnl_usd: float = 100.0,
    position_usd: float = 1000.0,
    file_stem: str = "2026-04-01",
) -> None:
    rec = {
        "closed_at": closed_at,
        "symbol": symbol,
        "direction": direction,
        "outcome": outcome,
        "pnl_usd": pnl_usd,
        "position_usd": position_usd,
    }
    f_path = signals_dir / f"{file_stem}.jsonl"
    with f_path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------------------
# kelly_size — standalone helper
# ---------------------------------------------------------------------------


class TestKellySize:
    def test_quarter_kelly_basic(self):
        """Quarter-Kelly with positive edge produces a fraction of full Kelly."""
        # win_rate=0.6, avg_win=200, avg_loss=100 → rr=2 → f*=0.4
        # quarter = 0.1 → 10% of 10000 = 1000
        size = kelly_size(0.6, 200.0, 100.0, 10_000.0, mode="quarter")
        assert size == 1000.0

    def test_half_kelly_doubles_quarter(self):
        q = kelly_size(0.6, 200.0, 100.0, 10_000.0, mode="quarter")
        h = kelly_size(0.6, 200.0, 100.0, 10_000.0, mode="half")
        assert h == pytest.approx(q * 2)

    def test_full_kelly_capped_at_25_percent(self):
        """Full Kelly is hard-capped at 25% of bankroll — no single-trade ruin."""
        # win_rate=0.9, rr=10 → f*=0.89, would normally allocate 89% of bankroll.
        size = kelly_size(0.9, 1000.0, 100.0, 10_000.0, mode="full")
        assert size == 2500.0  # capped at 25% × 10_000

    def test_zero_edge_returns_zero(self):
        """Negative-EV setup (rr too low for win_rate) returns 0."""
        # win_rate=0.5, rr=1 → f*=0
        assert kelly_size(0.5, 100.0, 100.0, 10_000.0) == 0.0

    def test_zero_avg_loss_returns_zero(self):
        """Guard against division by zero when avg_loss is 0."""
        assert kelly_size(0.6, 200.0, 0.0, 10_000.0) == 0.0

    def test_zero_bankroll_returns_zero(self):
        assert kelly_size(0.6, 200.0, 100.0, 0.0) == 0.0

    def test_zero_win_rate_returns_zero(self):
        assert kelly_size(0.0, 200.0, 100.0, 10_000.0) == 0.0

    def test_unknown_mode_falls_back_to_quarter(self):
        """Mode strings other than full/half/quarter use quarter as default."""
        q = kelly_size(0.6, 200.0, 100.0, 10_000.0, mode="quarter")
        unknown = kelly_size(0.6, 200.0, 100.0, 10_000.0, mode="banana")
        assert q == unknown


# ---------------------------------------------------------------------------
# RiskEngine.compute — empty / single trade
# ---------------------------------------------------------------------------


class TestComputeEdgeCases:
    def test_empty_no_files_returns_zero_metrics(self, tmp_paths):
        m = RiskEngine(bankroll=10_000.0).compute()
        assert isinstance(m, PortfolioMetrics)
        assert m.total_trades == 0
        assert m.wins == 0
        assert m.losses == 0
        assert m.total_pnl_usd == 0.0
        # Risk-adjusted metrics undefined with no trades
        assert m.sharpe is None
        assert m.sortino is None
        assert m.calmar is None
        assert m.win_rate is None
        assert m.equity_curve == []

    def test_single_trade_no_sharpe(self, tmp_paths):
        """One trade is below the n>=2 threshold for variance — Sharpe stays None."""
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00+00:00",
            outcome="win",
            pnl_usd=100.0,
        )
        m = RiskEngine(bankroll=10_000.0).compute()
        assert m.total_trades == 1
        assert m.wins == 1
        assert m.total_pnl_usd == 100.0
        assert m.sharpe is None
        assert m.sortino is None
        # Equity curve has the one entry
        assert len(m.equity_curve) == 1

    def test_only_breakeven_no_decisive_trades(self, tmp_paths):
        """Win rate is None when wins+losses == 0 (only break_even trades)."""
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00+00:00",
            outcome="break_even",
            pnl_usd=0.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-02T00:00:00+00:00",
            outcome="break_even",
            pnl_usd=0.0,
        )
        m = RiskEngine().compute()
        assert m.win_rate is None
        assert m.breakevens == 2


# ---------------------------------------------------------------------------
# RiskEngine.compute — multi-trade arithmetic
# ---------------------------------------------------------------------------


class TestComputeArithmetic:
    def test_win_rate_and_counts_correct(self, tmp_paths):
        # 3 wins, 1 loss, 1 break-even
        for i, outcome in enumerate(["win", "win", "win", "loss", "break_even"]):
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=f"2026-04-{i + 1:02d}T00:00:00+00:00",
                outcome=outcome,
                pnl_usd=100.0 if outcome == "win" else (-50.0 if outcome == "loss" else 0.0),
            )
        m = RiskEngine().compute()
        assert m.total_trades == 5
        assert m.wins == 3
        assert m.losses == 1
        assert m.breakevens == 1
        # 3 wins / (3+1) decisive = 0.75
        assert m.win_rate == 0.75

    def test_profit_factor_basic(self, tmp_paths):
        # 2 wins of 100 each ($200 gross), 1 loss of 50 ($50 gross loss)
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00+00:00",
            outcome="win",
            pnl_usd=100.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-02T00:00:00+00:00",
            outcome="win",
            pnl_usd=100.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-03T00:00:00+00:00",
            outcome="loss",
            pnl_usd=-50.0,
        )
        m = RiskEngine().compute()
        # PF = 200 / 50 = 4.0
        assert m.profit_factor == 4.0

    def test_profit_factor_inf_when_no_losses(self, tmp_paths):
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00+00:00",
            outcome="win",
            pnl_usd=100.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-02T00:00:00+00:00",
            outcome="win",
            pnl_usd=200.0,
        )
        m = RiskEngine().compute()
        assert m.profit_factor == float("inf")

    def test_total_pnl_signed(self, tmp_paths):
        """Net PnL is the signed sum of all per-trade PnLs."""
        for ts, outcome, pnl in [
            ("2026-04-01T00:00:00+00:00", "win", 100.0),
            ("2026-04-02T00:00:00+00:00", "loss", -75.0),
            ("2026-04-03T00:00:00+00:00", "win", 50.0),
        ]:
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=ts,
                outcome=outcome,
                pnl_usd=pnl,
            )
        m = RiskEngine().compute()
        assert m.total_pnl_usd == pytest.approx(75.0)

    def test_drawdown_from_peak_tracking(self, tmp_paths):
        """Max drawdown = (peak - trough) / peak across the equity curve."""
        # +200 (peak=10200) → -300 (trough=9900) → +100 (recover to 10000)
        # Drawdown from peak 10200 to 9900 = 300/10200 ≈ 2.94%
        for ts, outcome, pnl in [
            ("2026-04-01T00:00:00+00:00", "win", 200.0),
            ("2026-04-02T00:00:00+00:00", "loss", -300.0),
            ("2026-04-03T00:00:00+00:00", "win", 100.0),
        ]:
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=ts,
                outcome=outcome,
                pnl_usd=pnl,
            )
        m = RiskEngine(bankroll=10_000.0).compute()
        # Equity sequence: 10000 → 10200 → 9900 → 10000
        assert m.max_drawdown_usd == pytest.approx(300.0)
        # 300 / 10200 ≈ 0.0294
        assert m.max_drawdown_pct == pytest.approx(0.0294, abs=1e-3)


# ---------------------------------------------------------------------------
# RiskEngine.compute — Sharpe / Sortino / Calmar
# ---------------------------------------------------------------------------


class TestRiskAdjustedReturns:
    def test_sharpe_positive_for_winning_strategy(self, tmp_paths):
        """A strategy with all wins has positive Sharpe."""
        for i in range(5):
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=f"2026-04-{i + 1:02d}T00:00:00+00:00",
                outcome="win",
                pnl_usd=100.0 + i * 10,  # vary slightly so std > 0
            )
        m = RiskEngine().compute()
        assert m.sharpe is not None
        assert m.sharpe > 0

    def test_sortino_only_penalises_downside(self, tmp_paths):
        """For a winning strategy, Sortino should exceed Sharpe (no downside vol)."""
        for i in range(6):
            # 5 wins + 1 small loss → mostly upside
            outcome = "win" if i < 5 else "loss"
            pnl = 100.0 + i * 5 if outcome == "win" else -30.0
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=f"2026-04-{i + 1:02d}T00:00:00+00:00",
                outcome=outcome,
                pnl_usd=pnl,
            )
        m = RiskEngine().compute()
        assert m.sharpe is not None
        assert m.sortino is not None
        # Asymmetric upside → Sortino > Sharpe
        assert m.sortino > m.sharpe

    def test_calmar_uses_max_drawdown(self, tmp_paths):
        """Calmar is defined when there is any drawdown (>0)."""
        for ts, outcome, pnl in [
            ("2026-04-01T00:00:00+00:00", "win", 200.0),
            ("2026-04-02T00:00:00+00:00", "loss", -300.0),
            ("2026-04-03T00:00:00+00:00", "win", 250.0),
            ("2026-04-04T00:00:00+00:00", "win", 100.0),
        ]:
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=ts,
                outcome=outcome,
                pnl_usd=pnl,
            )
        m = RiskEngine().compute()
        assert m.calmar is not None
        assert math.isfinite(m.calmar)

    def test_zero_volatility_sharpe_is_none(self, tmp_paths):
        """If all per-trade returns are identical, std=0 → Sharpe undefined."""
        for i in range(4):
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=f"2026-04-{i + 1:02d}T00:00:00+00:00",
                outcome="win",
                pnl_usd=100.0,  # constant
            )
        m = RiskEngine().compute()
        # Identical returns → std == 0 → guard returns None for Sharpe.
        assert m.sharpe is None
        # No downside trades → dstd == 0 → Sortino also None.
        assert m.sortino is None


# ---------------------------------------------------------------------------
# Trade ingestion + ordering
# ---------------------------------------------------------------------------


class TestTradeIngestion:
    def test_chronological_sort_mixes_z_and_offset_suffixes(self, tmp_paths):
        """Equity curve must respect actual instants, not lexicographic order.

        `2026-04-02T00:00:00Z` (UTC) is the same instant as
        `2026-04-02T00:00:00+00:00`, but lexicographically `Z` sorts before
        `+`. The engine parses both and orders by parsed datetime.
        """
        # Out of chronological order: write later then earlier
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-03T00:00:00+00:00",
            outcome="win",
            pnl_usd=50.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00Z",
            outcome="win",
            pnl_usd=100.0,
        )
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-02T00:00:00Z",
            outcome="loss",
            pnl_usd=-30.0,
        )
        m = RiskEngine().compute()
        assert len(m.equity_curve) == 3
        # The first entry must be the chronologically-earliest 2026-04-01.
        # Verify by comparing the bankroll-relative PnL of the first row.
        first = m.equity_curve[0]
        assert first["pnl_usd"] == 100.0  # the +100 from 2026-04-01

    def test_paper_and_signals_streams_combined(self, tmp_paths):
        """compute() unifies trades from both paper_trading.jsonl and signals/*."""
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-01T00:00:00+00:00",
            outcome="win",
            pnl_usd=100.0,
        )
        _write_signal_trade(
            tmp_paths["signals_dir"],
            closed_at="2026-04-02T00:00:00+00:00",
            outcome="loss",
            pnl_usd=-25.0,
        )
        m = RiskEngine().compute()
        assert m.total_trades == 2
        assert m.wins == 1
        assert m.losses == 1

    def test_malformed_jsonl_lines_skipped(self, tmp_paths):
        """Bad JSON lines are silently dropped (resilience over strictness)."""
        # Write a mix of valid + corrupt
        with tmp_paths["paper_log"].open("w") as f:
            f.write(
                json.dumps(
                    {
                        "closed_at": "2026-04-01T00:00:00+00:00",
                        "symbol": "BTC",
                        "direction": "long",
                        "paper_outcome": "win",
                        "paper_pnl_usd": 100.0,
                        "position_usd": 1000.0,
                    }
                )
                + "\n"
            )
            f.write("{not json garbage}\n")
            f.write("\n")  # empty line
            f.write(
                json.dumps(
                    {
                        "closed_at": "2026-04-02T00:00:00+00:00",
                        "symbol": "BTC",
                        "direction": "short",
                        "paper_outcome": "loss",
                        "paper_pnl_usd": -50.0,
                        "position_usd": 1000.0,
                    }
                )
                + "\n"
            )
        m = RiskEngine().compute()
        assert m.total_trades == 2  # garbage skipped


# ---------------------------------------------------------------------------
# Recommended size / Kelly integration
# ---------------------------------------------------------------------------


class TestRecommendedSize:
    def test_recommended_size_thin_data_uses_defaults(self, tmp_paths):
        """With no trades, recommended_size falls back to default win_rate/rr."""
        m = RiskEngine(bankroll=10_000.0).compute()
        # DEFAULT_WIN_RATE=0.55, DEFAULT_RR=1.5 → quarter Kelly > 0
        assert m.recommended_size_usd > 0

    def test_kelly_fraction_capped_at_25_pct(self, tmp_paths):
        """The displayed kelly_fraction obeys the 25% cap, matching kelly_size()."""
        # Build a strategy with raw Kelly far above 0.25 (high win rate, big rr)
        for i in range(10):
            _write_paper_trade(
                tmp_paths["paper_log"],
                closed_at=f"2026-04-{i + 1:02d}T00:00:00+00:00",
                outcome="win",
                pnl_usd=1000.0,
            )
        # add one tiny loss so avg_loss is defined
        _write_paper_trade(
            tmp_paths["paper_log"],
            closed_at="2026-04-15T00:00:00+00:00",
            outcome="loss",
            pnl_usd=-10.0,
        )
        m = RiskEngine(bankroll=10_000.0).compute()
        # raw Kelly displayed is capped at 0.25
        assert m.kelly_fraction <= 0.25
        # quarter is 0.25 of raw → at most 0.0625
        assert m.kelly_quarter <= 0.0625


# ---------------------------------------------------------------------------
# _trades_per_day helper
# ---------------------------------------------------------------------------


class TestTradesPerDay:
    def test_one_trade_returns_one(self):
        t = Trade(
            timestamp="2026-04-01T00:00:00+00:00",
            symbol="BTC",
            direction="long",
            outcome="win",
            pnl_usd=10.0,
            position_usd=100.0,
            source="paper",
        )
        assert RiskEngine._trades_per_day([t]) == 1

    def test_two_trades_one_day_apart(self):
        a = Trade(
            timestamp="2026-04-01T00:00:00+00:00",
            symbol="BTC",
            direction="long",
            outcome="win",
            pnl_usd=10.0,
            position_usd=100.0,
            source="paper",
        )
        b = Trade(
            timestamp="2026-04-02T00:00:00+00:00",
            symbol="BTC",
            direction="long",
            outcome="loss",
            pnl_usd=-5.0,
            position_usd=100.0,
            source="paper",
        )
        # 2 trades over 1 day → 2 trades/day
        assert RiskEngine._trades_per_day([a, b]) == 2

    def test_malformed_timestamps_default_to_one(self):
        a = Trade(
            timestamp="garbage",
            symbol="BTC",
            direction="long",
            outcome="win",
            pnl_usd=10.0,
            position_usd=100.0,
            source="paper",
        )
        b = Trade(
            timestamp="also garbage",
            symbol="BTC",
            direction="long",
            outcome="loss",
            pnl_usd=-5.0,
            position_usd=100.0,
            source="paper",
        )
        assert RiskEngine._trades_per_day([a, b]) == 1
