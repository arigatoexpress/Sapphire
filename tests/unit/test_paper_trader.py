"""Unit tests for plugins/claw-sapphire/tools/internal/paper_trader.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "paper_trader.py"


@pytest.fixture
def trader(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("paper_trader", TOOL)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "PORTFOLIO_FILE", tmp_path / "paper_portfolio.json")
    monkeypatch.setattr(mod, "_record_outcome", lambda pipeline_id, pnl_usd, close_price=0.0: None)
    return mod


def test_manual_close_applies_round_trip_friction(trader, monkeypatch) -> None:
    opened = trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    monkeypatch.setattr(trader, "_get_price", lambda symbol: 100.0)

    closed = trader.action_close("BTCUSDT")
    pf = trader._load_portfolio()

    assert opened["entry_fee"] == "$40.00"
    assert opened["estimated_round_trip_friction"] == "$80.00"
    assert closed["pnl"] == "$-80.00"
    assert closed["fees"] == "$80.00"
    assert closed["capital"] == "$99,920.00"
    assert pf["capital"] == 99920.0
    assert pf["history"][0]["fees_usd"] == 80.0


def test_positions_include_fee_adjusted_unrealized_pnl(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    monkeypatch.setattr(trader, "_get_price", lambda symbol: 100.0)

    status = trader.action_positions()
    position = status["positions"][0]

    assert position["gross_unrealized_pnl"] == "$+0.00"
    assert position["unrealized_pnl"] == "$-80.00"
    assert position["fees_if_closed_now"] == "$80.00"
    assert status["estimated_liquidation_value"] == "$99,920.00"


def test_partial_exit_history_and_final_outcome_reconcile(trader, monkeypatch) -> None:
    outcome = {}
    monkeypatch.setattr(
        trader,
        "_record_outcome",
        lambda pipeline_id, pnl_usd, close_price=0.0: outcome.update(
            {
                "pipeline_id": pipeline_id,
                "pnl_usd": pnl_usd,
                "close_price": close_price,
            }
        ),
    )
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0, pipeline_id="sig-1")

    prices = iter([110.0, 100.0])
    monkeypatch.setattr(trader, "_get_price", lambda symbol: next(prices))

    partial = trader.action_check_stops()
    closed = trader.action_close("BTCUSDT")
    pf = trader._load_portfolio()

    assert partial["partial_exits"] == 1
    assert partial["closed"] == 0
    assert len(pf["history"]) == 2
    assert pf["history"][0]["pnl"] == 458.0
    assert pf["history"][0]["fees_usd"] == 42.0
    assert pf["history"][1]["pnl"] == -40.0
    assert pf["history"][1]["fees_usd"] == 40.0
    assert pf["capital"] == 100418.0
    assert closed["pnl"] == "$-40.00"
    assert outcome == {
        "pipeline_id": "sig-1",
        "pnl_usd": 418.0,
        "close_price": 100.0,
    }


def test_check_stops_closes_long_position_on_hard_stop_loss(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    pf = trader._load_portfolio()
    sl = pf["positions"][0]["stop_loss"]
    monkeypatch.setattr(trader, "_get_price", lambda symbol: sl - 0.01)

    result = trader.action_check_stops()

    assert result["closed"] == 1
    assert result["details"][0]["reason"] == "stop_loss"
    pf_after = trader._load_portfolio()
    assert pf_after["positions"] == []
    assert any(row["exit_reason"] == "stop_loss" for row in pf_after["history"])


def test_check_stops_closes_long_position_on_take_profit(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    pf = trader._load_portfolio()
    tp = pf["positions"][0]["take_profit"]
    monkeypatch.setattr(trader, "_get_price", lambda symbol: tp + 0.01)

    result = trader.action_check_stops()

    assert result["closed"] == 1
    assert result["details"][0]["reason"] == "take_profit"
    pf_after = trader._load_portfolio()
    assert pf_after["positions"] == []


def test_check_stops_closes_short_position_on_hard_stop_loss(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "SELL", 100.0, atr=10.0)
    pf = trader._load_portfolio()
    sl = pf["positions"][0]["stop_loss"]
    # For shorts, stop_loss is above entry; hit when price >= stop_loss.
    monkeypatch.setattr(trader, "_get_price", lambda symbol: sl + 0.01)

    result = trader.action_check_stops()

    assert result["closed"] == 1
    assert result["details"][0]["reason"] == "stop_loss"


def test_monitor_action_is_read_only_preview(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    pf = trader._load_portfolio()
    sl = pf["positions"][0]["stop_loss"]
    monkeypatch.setattr(trader, "_get_price", lambda symbol: sl - 0.01)

    monitor = trader.action_monitor()

    assert monitor["writes"] is False
    assert monitor["mode"] == "monitor_dry_run"
    assert monitor["open_positions"] == 1
    assert monitor["summary"]["would_close"] == 1
    assert monitor["rows"][0]["trigger"] == "stop_loss"

    # Critically, no state mutation: position still open after monitor.
    pf_after = trader._load_portfolio()
    assert len(pf_after["positions"]) == 1
    assert pf_after["history"] == []


def test_monitor_handles_missing_price_feed(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    monkeypatch.setattr(trader, "_get_price", lambda symbol: None)

    monitor = trader.action_monitor()

    assert monitor["summary"]["no_price"] == 1
    assert monitor["rows"][0]["trigger"] == "no_price"
    assert monitor["rows"][0]["current"] is None


def test_monitor_flags_trailing_breach_without_closing(trader, monkeypatch) -> None:
    trader.action_execute("BTCUSDT", "BUY", 100.0, atr=10.0)
    pf = trader._load_portfolio()
    pos = pf["positions"][0]
    pos["trailing_active"] = True
    pos["peak_price"] = 110.0
    trader._save_portfolio(pf)
    # 110 * (1 - 40bps) = 109.56; price below that triggers trailing breach.
    monkeypatch.setattr(trader, "_get_price", lambda symbol: 109.0)

    monitor = trader.action_monitor()

    assert monitor["rows"][0]["trigger"] == "trailing_stop"
    assert monitor["summary"]["would_trail"] == 1
    pf_after = trader._load_portfolio()
    assert len(pf_after["positions"]) == 1  # still no mutation
