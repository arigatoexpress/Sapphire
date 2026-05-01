from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.modules.pop("lib", None)

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "research_notes.py"
_spec = importlib.util.spec_from_file_location("research_notes_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
research_notes = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = research_notes
_spec.loader.exec_module(research_notes)


def _payload(action: str = "compose", output_root: str | None = None):
    payload = {
        "action": action,
        "as_of_date": "2026-04-29",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "backtest_summary": {
            "best_per_symbol": [
                {
                    "strategy_name": "Sapphire Composite",
                    "symbol": "BTC",
                    "sortino": 1.2,
                    "total_return_pct": 12.5,
                    "win_rate": 0.6,
                    "total_trades": 20,
                }
            ],
            "total_backtests": 80,
            "source_file": "fixture.json",
        },
        "leaderboard": {
            "metric": "sortino",
            "rows": [
                {
                    "strategy_name": "Sapphire Composite",
                    "symbol": "BTC",
                    "sortino": 1.2,
                    "total_return_pct": 12.5,
                    "win_rate": 0.6,
                    "total_trades": 20,
                }
            ],
            "total_rows": 8,
            "filtered_rows": 5,
            "source_file": "fixture.json",
        },
        "performance": {"overall": {"trades": 10, "total_pnl_usd": 1200.0}, "trade_count": 10},
        "timeseries": {
            "initial_capital": 100000,
            "final_equity": 101200,
            "equity_curve": [
                {"ts": "2026-04-01T00:00:00+00:00", "equity_usd": 100000},
                {"ts": "2026-04-02T00:00:00+00:00", "equity_usd": 101200},
            ],
        },
    }
    if output_root:
        payload["output_root"] = output_root
    return payload


def test_compose_action_returns_note():
    result = research_notes.handle(_payload())

    assert result["ok"] is True
    assert result["note"]["strategy_slug"] == "sapphire-composite"
    assert "Research-only artifact" in result["note"]["caveat"]


def test_render_latest_and_aggregate(tmp_path):
    render = research_notes.handle(_payload("render", str(tmp_path)))
    latest = research_notes.handle({"action": "latest", "output_root": str(tmp_path)})
    aggregate = research_notes.handle({"action": "aggregate-summary", "output_root": str(tmp_path)})

    assert render["ok"] is True
    assert latest["latest"]["strategy_slug"] == "sapphire-composite"
    assert aggregate["note_count"] == 1


def test_unknown_action_fails_closed():
    result = research_notes.handle({"action": "send-to-telegram"})

    assert result["ok"] is False
    assert "unknown action" in result["error"]
