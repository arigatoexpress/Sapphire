from __future__ import annotations

import json
from pathlib import Path

from lib.core.provenance import sidecar_path, verify
from lib.research_notes.pipeline import compose_note, render_note


def _note():
    row = {
        "strategy_name": "Sapphire Composite",
        "symbol": "BTC",
        "sortino": 1.42,
        "total_return_pct": 18.5,
        "win_rate": 0.62,
        "max_drawdown_pct": -0.08,
        "total_trades": 42,
    }
    return compose_note(
        backtest_summary_data={
            "best_per_symbol": [row],
            "total_backtests": 144,
            "source_file": "fixture.json",
        },
        leaderboard_data={
            "metric": "sortino",
            "rows": [row],
            "total_rows": 12,
            "filtered_rows": 7,
            "source_file": "fixture.json",
        },
        performance_data={"overall": {"trades": 18, "total_pnl_usd": 1840.0}, "trade_count": 18},
        timeseries_data={},
        as_of_date="2026-04-29",
        generated_at="2026-04-29T00:00:00+00:00",
    )


def test_render_note_writes_pdf_and_verifiable_envelope(tmp_path: Path):
    pdf = render_note(
        _note(),
        timeseries_data={
            "equity_curve": [{"equity_usd": 100000}, {"equity_usd": 101840}],
            "drawdown_series": [{"dd_pct": 0.0}, {"dd_pct": -0.02}],
        },
        output_root=tmp_path,
    )
    envelope = sidecar_path(pdf)

    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert envelope.exists()
    assert verify(json.loads(envelope.read_text()))
    assert "sapphire-composite" in envelope.read_text()
