"""Unit tests for lib.analytics.performance — rolling metrics, regime breakdown,
monthly returns, extremes, equity curve assembly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _evict_stale_lib_analytics():
    """Worktree-safety: another test may have cached lib.analytics from the
    main repo path via signal_pipeline.py. Evict on each test so the next
    import resolves against the current worktree.
    """
    expected = str(ROOT / "lib" / "analytics")
    cached = sys.modules.get("lib.analytics")
    if cached is not None:
        paths = list(getattr(cached, "__path__", []))
        if expected not in paths:
            for key in [k for k in list(sys.modules) if k == "lib" or k.startswith("lib.")]:
                del sys.modules[key]
    if sys.path[0] != str(ROOT):
        sys.path.insert(0, str(ROOT))
    yield


# ---------------------------------------------------------------------------
# Rolling Sharpe
# ---------------------------------------------------------------------------


def _trade(
    pnl: float,
    ts: str = "2026-01-01",
    outcome: str = None,
    regime: str = "NEUTRAL",
    confidence: float = 0.7,
):
    return {
        "timestamp": ts,
        "symbol": "BTC",
        "direction": "long",
        "outcome": outcome or ("win" if pnl > 0 else "loss"),
        "pnl_usd": pnl,
        "confidence": confidence,
        "regime": regime,
        "position_usd": 1000.0,
    }


def test_rolling_sharpe_empty_when_below_window():
    from lib.analytics.performance import _rolling_sharpe

    trades = [_trade(10.0, "2026-01-01")] * 5
    assert _rolling_sharpe(trades, 10_000.0, window=10) == []


def test_rolling_sharpe_returns_one_entry_at_window_size():
    from lib.analytics.performance import _rolling_sharpe

    trades = [_trade(100.0 if i % 2 == 0 else -50.0, f"2026-01-{i + 1:02d}") for i in range(10)]
    out = _rolling_sharpe(trades, 10_000.0, window=10)
    assert len(out) == 1
    assert "sharpe" in out[0]


def test_rolling_sharpe_zero_variance_yields_nothing():
    from lib.analytics.performance import _rolling_sharpe

    # Identical PnL → zero std → no sharpe emitted
    trades = [_trade(10.0, f"2026-01-{i + 1:02d}") for i in range(10)]
    out = _rolling_sharpe(trades, 10_000.0, window=10)
    assert out == []


# ---------------------------------------------------------------------------
# Rolling Kelly
# ---------------------------------------------------------------------------


def test_rolling_kelly_empty_when_below_window():
    from lib.analytics.performance import _rolling_kelly

    assert _rolling_kelly([_trade(10.0)] * 5, window=10) == []


def test_rolling_kelly_quarter_capped_at_025():
    from lib.analytics.performance import _rolling_kelly

    # 10 wins of $500, no losses → raw Kelly would be +inf, quarter capped at 0.25
    trades = [_trade(500.0, f"2026-01-{i + 1:02d}") for i in range(10)]
    out = _rolling_kelly(trades, window=10)
    # With all wins, avg_loss=0 → skip
    assert out == []


def test_rolling_kelly_positive_edge():
    from lib.analytics.performance import _rolling_kelly

    # Need decisive count >= 5. Mix of wins and losses with positive edge:
    # 7 wins of $200, 3 losses of $100 → wr=0.7, rr=2.0, kelly=0.55, quarter=0.1375
    trades = [_trade(200.0, f"2026-01-{i + 1:02d}") for i in range(7)] + [
        _trade(-100.0, f"2026-01-{i + 8:02d}") for i in range(3)
    ]
    out = _rolling_kelly(trades, window=10)
    assert len(out) == 1
    assert out[0]["kelly_quarter"] == pytest.approx(0.1375, abs=0.01)
    assert out[0]["kelly_quarter"] <= 0.25


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------


def test_regime_breakdown_buckets_correctly():
    from lib.analytics.performance import _regime_breakdown

    trades = [
        _trade(100.0, regime="RISK_ON"),
        _trade(-50.0, regime="RISK_ON"),
        _trade(200.0, regime="RISK_OFF"),
        _trade(150.0, regime="RISK_OFF"),
    ]
    out = _regime_breakdown(trades)
    assert out["RISK_ON"]["trades"] == 2
    assert out["RISK_ON"]["wins"] == 1
    assert out["RISK_ON"]["losses"] == 1
    assert out["RISK_ON"]["win_rate"] == 0.5
    assert out["RISK_OFF"]["trades"] == 2
    assert out["RISK_OFF"]["wins"] == 2
    assert out["RISK_OFF"]["total_pnl_usd"] == 350.0


def test_regime_breakdown_handles_unknown():
    from lib.analytics.performance import _regime_breakdown

    trades = [{"outcome": "win", "pnl_usd": 10.0, "regime": None, "timestamp": "2026-01-01"}]
    out = _regime_breakdown(trades)
    assert "UNKNOWN" in out


# ---------------------------------------------------------------------------
# Monthly returns
# ---------------------------------------------------------------------------


def test_monthly_returns_aggregates_by_month():
    from lib.analytics.performance import _monthly_returns

    trades = [
        _trade(100.0, "2026-01-15T10:00:00+00:00"),
        _trade(50.0, "2026-01-20T10:00:00+00:00"),
        _trade(200.0, "2026-02-05T10:00:00+00:00"),
    ]
    out = _monthly_returns(trades, 10_000.0)
    assert len(out) == 2
    jan = next(m for m in out if m["month"] == "2026-01")
    feb = next(m for m in out if m["month"] == "2026-02")
    assert jan["pnl_usd"] == 150.0
    assert feb["pnl_usd"] == 200.0
    assert jan["pct"] == pytest.approx(0.015, abs=0.001)


def test_monthly_returns_skips_bad_timestamps():
    from lib.analytics.performance import _monthly_returns

    trades = [_trade(100.0, "not-a-date"), _trade(50.0, "2026-01-15T10:00:00+00:00")]
    out = _monthly_returns(trades, 10_000.0)
    assert len(out) == 1
    assert out[0]["pnl_usd"] == 50.0


# ---------------------------------------------------------------------------
# Extremes
# ---------------------------------------------------------------------------


def test_extreme_trades_best_and_worst():
    from lib.analytics.performance import _extreme_trades

    trades = [
        _trade(500.0, "2026-01-01"),
        _trade(-300.0, "2026-01-02"),
        _trade(100.0, "2026-01-03"),
        _trade(-150.0, "2026-01-04"),
        _trade(700.0, "2026-01-05"),
        _trade(-400.0, "2026-01-06"),
    ]
    ext = _extreme_trades(trades, n=3)
    assert len(ext["best"]) == 3
    assert len(ext["worst"]) == 3
    assert ext["best"][0]["pnl_usd"] == 700.0
    assert ext["worst"][0]["pnl_usd"] == -400.0


def test_extreme_trades_fewer_than_n():
    from lib.analytics.performance import _extreme_trades

    trades = [_trade(100.0, "2026-01-01"), _trade(-50.0, "2026-01-02")]
    ext = _extreme_trades(trades, n=5)
    # Top-n and worst-n overlap when there aren't enough trades
    assert len(ext["best"]) == 2
    assert len(ext["worst"]) == 2


# ---------------------------------------------------------------------------
# compute_performance (end-to-end with redirected paths)
# ---------------------------------------------------------------------------


def test_compute_performance_with_no_data(tmp_path, monkeypatch):
    from lib.analytics import performance as perf

    monkeypatch.setattr(perf, "SIGNALS_DIR", tmp_path / "signals")
    monkeypatch.setattr(perf, "PAPER_LOG", tmp_path / "paper.jsonl")

    # Network-bound BTC benchmark gets skipped in the empty-trade path,
    # but stub for safety.
    monkeypatch.setattr(perf, "_btc_benchmark_curve", lambda trades, bankroll: [])

    out = perf.compute_performance(bankroll=10_000.0)
    assert out["trades"] == 0
    assert out["final_equity"] == 10_000.0
    assert out["equity_curve"] == []
    assert out["btc_benchmark"] == []


def test_compute_performance_builds_equity_curve(tmp_path, monkeypatch):
    from lib.analytics import performance as perf

    signals = tmp_path / "signals"
    signals.mkdir()
    records = [
        {
            "outcome": "win",
            "pnl_usd": 500.0,
            "confidence": 0.8,
            "closed_at": "2026-04-10T10:00:00+00:00",
            "symbol": "BTC",
            "direction": "long",
            "regime": "RISK_ON",
        },
        {
            "outcome": "loss",
            "pnl_usd": -200.0,
            "confidence": 0.6,
            "closed_at": "2026-04-11T10:00:00+00:00",
            "symbol": "ETH",
            "direction": "short",
            "regime": "RISK_OFF",
        },
    ]
    (signals / "2026-04-10.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    monkeypatch.setattr(perf, "SIGNALS_DIR", signals)
    monkeypatch.setattr(perf, "PAPER_LOG", tmp_path / "paper.jsonl")
    monkeypatch.setattr(perf, "_btc_benchmark_curve", lambda trades, bankroll: [])

    out = perf.compute_performance(bankroll=10_000.0)
    assert out["trades"] == 2
    assert out["final_equity"] == 10_300.0
    assert len(out["equity_curve"]) == 2
    assert out["equity_curve"][-1]["equity_usd"] == 10_300.0
    # Signal quality scatter holds only rows with confidence
    assert len(out["signal_quality"]) == 2
    # Regime breakdown includes both regimes
    assert "RISK_ON" in out["regime_breakdown"]
    assert "RISK_OFF" in out["regime_breakdown"]
