from __future__ import annotations

from lib.research_notes.pipeline import compose_note


def _fixtures():
    backtest = {
        "have_results": True,
        "best_per_symbol": [
            {
                "strategy_name": "Sapphire Composite",
                "symbol": "BTC",
                "sortino": 1.42,
                "total_return_pct": 18.5,
                "win_rate": 0.62,
                "max_drawdown_pct": -0.08,
                "total_trades": 42,
            }
        ],
        "total_backtests": 144,
        "computed_at": "2026-04-29T00:00:00+00:00",
        "source_file": "strategy_sweep_fixture.json",
    }
    leaderboard = {
        "metric": "sortino",
        "rows": [backtest["best_per_symbol"][0]],
        "total_rows": 12,
        "filtered_rows": 7,
        "source_file": "strategy_sweep_fixture.json",
    }
    performance = {
        "overall": {"trades": 18, "total_pnl_usd": 1840.0, "win_rate": 0.61},
        "trade_count": 18,
    }
    timeseries = {"equity_curve": [{"equity_usd": 100000}, {"equity_usd": 101840}]}
    return backtest, leaderboard, performance, timeseries


def test_compose_research_note_core_sections_are_stable():
    backtest, leaderboard, performance, timeseries = _fixtures()
    note = compose_note(
        backtest_summary_data=backtest,
        leaderboard_data=leaderboard,
        performance_data=performance,
        timeseries_data=timeseries,
        context={"market_regime": "risk-on"},
        as_of_date="2026-04-29",
        generated_at="2026-04-29T00:00:00+00:00",
    )

    assert note.note_id == "2026-04-29/sapphire-composite"
    assert note.strategy_name == "Sapphire Composite"
    assert note.key_metrics["rank_metric"] == "sortino"
    assert note.key_metrics["rank_metric_value"] == 1.42
    assert note.key_metrics["trade_count"] == 18
    assert len(note.evidence) >= 5
    assert len(note.invalidators) == 4
    assert len(note.next_steps) == 3
    assert "buyer" in note.counter_thesis
    assert "does not place trades" in note.caveat
    assert note.provenance["mode"] == "offline"
    assert note.provenance["input_hash"]


def test_compose_research_note_falls_back_without_backtests():
    note = compose_note(
        backtest_summary_data={"have_results": False, "total_backtests": 0},
        leaderboard_data={"metric": "sortino", "rows": [], "total_rows": 0, "filtered_rows": 0},
        performance_data={"overall": {}, "trade_count": 0},
        timeseries_data={},
        context={},
        as_of_date="2026-04-29",
        generated_at="2026-04-29T00:00:00+00:00",
    )

    assert note.strategy_slug == "sapphire-composite"
    assert note.key_metrics["symbol"] == "multi-asset"
    assert "research-only" in note.caveat.lower()
