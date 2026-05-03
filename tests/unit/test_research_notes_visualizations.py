from __future__ import annotations

from pathlib import Path

from lib.research_notes.visualizations import render_drawdown_chart, render_equity_chart


def _timeseries():
    return {
        "initial_capital": 100_000,
        "final_equity": 101_840,
        "equity_curve": [
            {"ts": "2026-04-01T00:00:00+00:00", "equity_usd": 100_000, "pnl_usd": 0},
            {"ts": "2026-04-02T00:00:00+00:00", "equity_usd": 100_800, "pnl_usd": 800},
            {"ts": "2026-04-03T00:00:00+00:00", "equity_usd": 101_840, "pnl_usd": 1040},
        ],
        "drawdown_series": [
            {"ts": "2026-04-01T00:00:00+00:00", "dd_pct": 0.0},
            {"ts": "2026-04-02T00:00:00+00:00", "dd_pct": -0.02},
            {"ts": "2026-04-03T00:00:00+00:00", "dd_pct": 0.0},
        ],
        "max_drawdown": {"pct": -0.02, "ts": "2026-04-02T00:00:00+00:00"},
    }


def test_equity_chart_is_deterministic_and_local(tmp_path: Path):
    one = render_equity_chart(_timeseries(), tmp_path / "one.png")
    two = render_equity_chart(_timeseries(), tmp_path / "two.png")

    assert one["kind"] == "equity_curve"
    assert one["point_count"] == 3
    assert one["data_hash_material"] == two["data_hash_material"]
    assert Path(one["path"]).exists()
    assert (
        "customer" not in Path(one["path"]).read_bytes().decode("latin1", errors="ignore").lower()
    )


def test_drawdown_chart_is_deterministic_and_local(tmp_path: Path):
    one = render_drawdown_chart(_timeseries(), tmp_path / "dd-one.png")
    two = render_drawdown_chart(_timeseries(), tmp_path / "dd-two.png")

    assert one["kind"] == "drawdown"
    assert one["point_count"] == 3
    assert one["data_hash_material"] == two["data_hash_material"]
    assert Path(one["path"]).exists()
