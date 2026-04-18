"""Unit tests — lib.analytics.performance."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.analytics.performance import (
    _monthly_returns,
    _regime_breakdown,
    _rolling_sharpe,
    build_performance_report,
)


def _curve(n: int = 40, slope: float = 10.0) -> list[tuple[str, float]]:
    return [(f"2026-01-{(i % 28) + 1:02d}", 100_000 + slope * i) for i in range(n)]


class TestRollingSharpe:
    def test_empty_when_curve_too_short(self):
        assert _rolling_sharpe(_curve(5), window=30) == []

    def test_uptrending_curve_positive_sharpe(self):
        rs = _rolling_sharpe(_curve(60, slope=50), window=30)
        assert len(rs) > 0
        assert all(p["sharpe"] > 0 for p in rs)

    def test_flat_curve_zero_sharpe(self):
        curve = [(f"d{i}", 100_000.0) for i in range(60)]
        rs = _rolling_sharpe(curve, window=30)
        for p in rs:
            assert p["sharpe"] == 0.0


class TestRegimeBreakdown:
    def test_groups_and_aggregates(self):
        trades = [
            {"regime": "TREND_UP",   "pnl":  50, "pnl_pct":  5.0},
            {"regime": "TREND_UP",   "pnl": -20, "pnl_pct": -2.0},
            {"regime": "TREND_DOWN", "pnl": 100, "pnl_pct": 10.0},
        ]
        out = _regime_breakdown(trades)
        by = {r["regime"]: r for r in out}
        assert by["TREND_UP"]["trade_count"] == 2
        assert by["TREND_UP"]["win_rate"] == 0.5
        assert by["TREND_UP"]["total_pnl"] == 30.0
        assert by["TREND_DOWN"]["win_rate"] == 1.0

    def test_empty_input(self):
        assert _regime_breakdown([]) == []


class TestMonthlyReturns:
    def test_groups_by_year_month(self):
        trades = [
            {"exit_date": "2026-01-15", "pnl_pct": 2.0},
            {"exit_date": "2026-01-22", "pnl_pct": 1.0},
            {"exit_date": "2026-03-01", "pnl_pct": -0.5},
            {"exit_date": "2025-11-11", "pnl_pct": 4.0},
        ]
        out = _monthly_returns(trades)
        assert out["2026"][0] == 3.0  # Jan
        assert out["2026"][2] == -0.5  # Mar
        assert out["2025"][10] == 4.0  # Nov
        assert out["2026"][1] == 0.0   # Feb empty

    def test_malformed_dates_skipped(self):
        out = _monthly_returns([
            {"exit_date": "bad", "pnl_pct": 5},
            {"exit_date": "", "pnl_pct": 5},
            {"exit_date": "2026-02-05", "pnl_pct": 3},
        ])
        assert out["2026"][1] == 3.0


class TestBuildPerformanceReport:
    def test_missing_file_returns_error(self, tmp_path):
        out = build_performance_report(tmp_path / "nope.json")
        assert "error" in out

    def test_malformed_file_returns_error(self, tmp_path):
        p = tmp_path / "bt.json"
        p.write_text("not json")
        out = build_performance_report(p)
        assert "error" in out

    def test_builds_full_payload(self, tmp_path):
        sample = {
            "timestamp": "2026-04-18T00:00:00Z",
            "with_regime": {
                "BTC-USD": {
                    "total_return_pct": 5.0,
                    "sharpe": 1.2,
                    "sortino": 1.5,
                    "max_drawdown_pct": 3.0,
                    "win_rate": 0.7,
                    "profit_factor": 2.1,
                    "trade_count": 3,
                    "equity_curve":    [["2026-01-01", 100000], ["2026-01-02", 101000]],
                    "benchmark_curve": [["2026-01-01", 100000], ["2026-01-02", 102000]],
                    "trades": [
                        {"exit_date": "2026-01-05", "confidence": 0.7, "pnl": 100,
                         "pnl_pct": 1.0, "regime": "TREND_UP", "score": 80},
                        {"exit_date": "2026-01-10", "confidence": 0.5, "pnl": -30,
                         "pnl_pct": -0.3, "regime": "RANGE", "score": 60},
                    ],
                },
            },
            "without_regime": {
                "BTC-USD": {
                    "total_return_pct": 3.0,
                    "sharpe": 0.8,
                    "sortino": 1.0,
                    "max_drawdown_pct": 4.0,
                    "win_rate": 0.5,
                    "profit_factor": 1.5,
                    "trade_count": 4,
                    "equity_curve":    [["2026-01-01", 100000], ["2026-01-02", 100500]],
                    "trades": [],
                },
            },
        }
        p = tmp_path / "bt.json"
        p.write_text(json.dumps(sample))
        out = build_performance_report(p, primary_symbol="BTC-USD")
        assert out["primary_symbol"] == "BTC-USD"
        assert len(out["equity_curve"]) == 2
        assert len(out["equity_curve_off"]) == 2
        assert len(out["benchmark_curve"]) == 2
        assert out["signal_quality"][0]["symbol"] == "BTC-USD"
        assert len(out["regime_breakdown"]) == 2
        assert out["monthly_returns"]["2026"][0] == 0.7   # 1.0 + (-0.3)
        assert len(out["summary"]) == 1

    def test_falls_back_to_first_symbol_when_primary_missing(self, tmp_path):
        sample = {
            "timestamp": "2026-04-18T00:00:00Z",
            "with_regime":    {"ETH-USD": {"equity_curve": [["2026-01-01", 100000]], "trades": []}},
            "without_regime": {"ETH-USD": {"equity_curve": [], "trades": []}},
        }
        p = tmp_path / "bt.json"
        p.write_text(json.dumps(sample))
        out = build_performance_report(p, primary_symbol="SOL-USD")
        assert out["primary_symbol"] == "ETH-USD"
