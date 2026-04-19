"""Unit tests for lib.analytics.strategy_performance."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from lib.analytics import strategy_performance as sp


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _trade(
    strategy: str = "S",
    symbol: str = "BTC",
    outcome: str = "win",
    pnl: float = 100.0,
    entry: float = 50000.0,
    exit_: float = 51000.0,
    position: float = 1000.0,
    opened: str | None = "2026-04-18T00:00:00+00:00",
    closed: str | None = "2026-04-18T03:00:00+00:00",
) -> dict:
    return {
        "pipeline_id": f"{strategy}-{symbol}",
        "timestamp": opened,
        "symbol": symbol,
        "direction": "long",
        "strategy": strategy,
        "price": entry,
        "confidence": 0.7,
        "regime": "RISK_ON",
        "position_usd": position,
        "outcome": outcome,
        "pnl_usd": pnl,
        "close_price": exit_,
        "closed_at": closed,
    }


class TestBucketing:
    def test_bucket_for_under_1h(self):
        assert sp._bucket_for(timedelta(minutes=30)) == "1h"

    def test_bucket_for_4h(self):
        assert sp._bucket_for(timedelta(hours=3)) == "4h"

    def test_bucket_for_1d(self):
        assert sp._bucket_for(timedelta(hours=23)) == "1d"

    def test_bucket_for_7d(self):
        assert sp._bucket_for(timedelta(days=6)) == "7d"

    def test_bucket_for_30d(self):
        assert sp._bucket_for(timedelta(days=15)) == "30d"

    def test_bucket_for_none(self):
        assert sp._bucket_for(None) == "all"

    def test_bucket_for_over_30d(self):
        assert sp._bucket_for(timedelta(days=60)) == "all"


class TestStatsComputation:
    def test_empty(self):
        s = sp._stats_for([])
        assert s["trades"] == 0
        assert s["win_rate"] is None
        assert s["total_pnl_usd"] == 0.0
        assert s["portfolio_roi_pct"] is None

    def test_all_wins(self):
        trades = [sp._normalize("S", "BTC", "long", "win", 100, 50000, 51000, 1000, 0.7, "R", None, None, "t") for _ in range(3)]
        s = sp._stats_for(trades)
        assert s["trades"] == 3
        assert s["wins"] == 3
        assert s["losses"] == 0
        assert s["win_rate"] == 1.0
        assert s["profit_factor"] == "inf"
        assert s["total_pnl_usd"] == 300.0
        assert s["portfolio_roi_pct"] == 10.0

    def test_mixed_outcomes(self):
        trades = [
            sp._normalize("S", "BTC", "long", "win", 200, 50000, 51000, 1000, 0.7, "R", None, None, "t"),
            sp._normalize("S", "BTC", "long", "loss", -100, 50000, 49500, 1000, 0.7, "R", None, None, "t"),
        ]
        s = sp._stats_for(trades)
        assert s["trades"] == 2
        assert s["wins"] == 1
        assert s["losses"] == 1
        assert s["win_rate"] == 0.5
        assert s["total_pnl_usd"] == 100.0
        assert s["profit_factor"] == 2.0  # 200 / 100

    def test_only_losses(self):
        trades = [sp._normalize("S", "BTC", "long", "loss", -100, 50000, 49500, 1000, 0.7, "R", None, None, "t") for _ in range(2)]
        s = sp._stats_for(trades)
        assert s["win_rate"] == 0.0
        assert s["profit_factor"] == 0.0


class TestSortino:
    def test_needs_multiple_downside(self):
        assert sp._sortino([100, 200]) is None  # no downside
        assert sp._sortino([100, -50]) is None  # only one downside

    def test_computes_when_valid(self):
        pnls = [100, -50, 200, -30, 150]
        s = sp._sortino(pnls)
        assert s is not None
        assert s > 0  # positive mean, should be > 0


class TestReport:
    def test_empty_when_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sp, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "perf.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "portfolio.json")
        r = sp.report()
        assert r["trade_count"] == 0
        assert r["overall"]["trades"] == 0
        assert "note" in r

    def test_reads_signals_dir(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        _write_jsonl(sigs / "2026-04-18.jsonl", [
            _trade(strategy="rsi", pnl=100, outcome="win"),
            _trade(strategy="rsi", pnl=-50, outcome="loss", symbol="ETH"),
            _trade(strategy="bb", pnl=200, outcome="win"),
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "nonexistent.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "nonexistent.json")
        r = sp.report()
        assert r["trade_count"] == 3
        assert r["overall"]["win_rate"] == pytest.approx(2/3, rel=0.01)
        assert "rsi" in r["by_strategy"]
        assert "bb" in r["by_strategy"]
        assert r["by_strategy"]["rsi"]["trades"] == 2
        assert r["by_strategy"]["bb"]["wins"] == 1

    def test_timeframe_bucketing(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        _write_jsonl(sigs / "2026-04-18.jsonl", [
            _trade(strategy="S", pnl=100, outcome="win",
                   opened="2026-04-18T00:00:00+00:00", closed="2026-04-18T00:30:00+00:00"),  # 30min
            _trade(strategy="S", pnl=50, outcome="win", symbol="ETH",
                   opened="2026-04-18T00:00:00+00:00", closed="2026-04-18T12:00:00+00:00"),  # 12h
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "np.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        r = sp.report()
        assert r["by_timeframe"]["1h"]["trades"] == 1
        assert r["by_timeframe"]["1d"]["trades"] == 1
        assert r["by_strategy_timeframe"]["S"]["1h"]["trades"] == 1
        assert r["by_strategy_timeframe"]["S"]["1d"]["trades"] == 1

    def test_dedupe_across_sources(self, tmp_path, monkeypatch):
        """Same trade appearing in signals/ and perf/ should count once."""
        sigs = tmp_path / "signals"
        sigs.mkdir()
        same_trade = _trade(strategy="dup", symbol="BTC",
                            opened="2026-04-18T00:00:00+00:00",
                            closed="2026-04-18T03:00:00+00:00")
        _write_jsonl(sigs / "d.jsonl", [same_trade])
        perf = tmp_path / "perf.jsonl"
        perf.write_text(json.dumps({
            "symbol": "BTC",
            "strategy": "dup",
            "recorded_at": "2026-04-18T00:00:00+00:00",
            "closed_at": "2026-04-18T03:00:00+00:00",
            "outcome": "win",
            "pnl_pct": 0.1,
            "position_usd": 1000,
            "entry_price": 50000,
            "exit_price": 55000,
        }) + "\n")
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", perf)
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        r = sp.report()
        assert r["trade_count"] == 1, "duplicate across sources should be deduped"

    def test_skips_open_positions(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        # One closed, one still open (no outcome)
        open_trade = _trade(strategy="open", pnl=0, outcome="win")
        open_trade["outcome"] = None
        _write_jsonl(sigs / "x.jsonl", [
            _trade(strategy="S", pnl=100, outcome="win"),
            open_trade,
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "np.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        r = sp.report()
        assert r["trade_count"] == 1


class TestTimeseries:
    def test_empty_when_no_trades(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sp, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "perf.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "portfolio.json")
        ts = sp.timeseries()
        assert ts["trade_count"] == 0
        assert ts["equity_curve"] == []
        assert ts["drawdown_series"] == []
        assert ts["monthly_returns"] == []

    def test_equity_curve_monotonic_wins(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        _write_jsonl(sigs / "d.jsonl", [
            _trade(pnl=100, opened="2026-04-01T00:00:00+00:00", closed="2026-04-01T01:00:00+00:00"),
            _trade(pnl=200, opened="2026-04-02T00:00:00+00:00", closed="2026-04-02T01:00:00+00:00", symbol="ETH"),
            _trade(pnl=50, opened="2026-04-03T00:00:00+00:00", closed="2026-04-03T01:00:00+00:00", symbol="SOL"),
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "np.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        ts = sp.timeseries(initial_capital=100000)
        assert ts["trade_count"] == 3
        assert len(ts["equity_curve"]) == 3
        assert ts["equity_curve"][0]["equity_usd"] == 100100.0
        assert ts["equity_curve"][1]["equity_usd"] == 100300.0
        assert ts["equity_curve"][2]["equity_usd"] == 100350.0
        assert ts["max_drawdown"]["pct"] == 0.0
        assert ts["total_pnl_usd"] == 350.0
        assert ts["total_return_pct"] == pytest.approx(0.35, rel=0.01)

    def test_drawdown_tracked(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        _write_jsonl(sigs / "d.jsonl", [
            _trade(pnl=1000, outcome="win",
                   opened="2026-04-01T00:00:00+00:00", closed="2026-04-01T01:00:00+00:00"),
            _trade(pnl=-500, outcome="loss", symbol="ETH",
                   opened="2026-04-02T00:00:00+00:00", closed="2026-04-02T01:00:00+00:00"),
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "np.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        ts = sp.timeseries(initial_capital=100000)
        # peak = 101000 (after win), then -500 → dd = -500/101000 ≈ -0.00495
        assert ts["max_drawdown"]["pct"] < 0
        assert ts["max_drawdown"]["pct"] == pytest.approx(-500/101000, rel=0.01)

    def test_monthly_bucketing(self, tmp_path, monkeypatch):
        sigs = tmp_path / "signals"
        sigs.mkdir()
        _write_jsonl(sigs / "d.jsonl", [
            _trade(pnl=100, opened="2026-03-15T00:00:00+00:00", closed="2026-03-15T01:00:00+00:00"),
            _trade(pnl=200, opened="2026-04-02T00:00:00+00:00", closed="2026-04-02T01:00:00+00:00", symbol="ETH"),
            _trade(pnl=-50, opened="2026-04-10T00:00:00+00:00", closed="2026-04-10T01:00:00+00:00", symbol="SOL"),
        ])
        monkeypatch.setattr(sp, "SIGNALS_DIR", sigs)
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "np.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", tmp_path / "np.json")
        ts = sp.timeseries(initial_capital=100000)
        months = {(m["year"], m["month"]): m for m in ts["monthly_returns"]}
        assert (2026, 3) in months
        assert (2026, 4) in months
        assert months[(2026, 3)]["pnl_usd"] == 100.0
        assert months[(2026, 3)]["trades"] == 1
        assert months[(2026, 4)]["pnl_usd"] == 150.0  # 200 - 50
        assert months[(2026, 4)]["trades"] == 2


class TestPaperPortfolioSource:
    def test_reads_portfolio_history(self, tmp_path, monkeypatch):
        pf = tmp_path / "portfolio.json"
        pf.write_text(json.dumps({
            "capital": 100500.0,
            "initial_capital": 100000.0,
            "positions": [],
            "history": [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "entry_price": 70000,
                    "exit_price": 75000,
                    "original_size_usd": 10000,
                    "pnl": 500,
                    "confidence": 0.85,
                    "opened_at": "2026-04-01T00:00:00+00:00",
                    "closed_at": "2026-04-09T21:51:42+00:00",
                    "exit_reason": "trailing_stop",
                },
            ],
        }))
        monkeypatch.setattr(sp, "SIGNALS_DIR", tmp_path / "empty")
        monkeypatch.setattr(sp, "PERF_SIGNALS", tmp_path / "empty.jsonl")
        monkeypatch.setattr(sp, "PAPER_PORTFOLIO", pf)
        r = sp.report()
        assert r["trade_count"] == 1
        assert r["overall"]["wins"] == 1
        assert r["by_strategy"]["paper_trader"]["trades"] == 1
        # 8-day hold → 30d bucket
        assert r["by_timeframe"]["30d"]["trades"] == 1
