"""Tests for the x402 backtest receipt artifact builder."""

from __future__ import annotations

from lib.payments.x402_backtest_receipt import (
    artifact_id_for_backtest_receipt,
    build_backtest_receipt,
)
from lib.payments.x402_products import load_product_catalog, load_source_registry


def _summary() -> dict:
    return {
        "have_results": True,
        "total_backtests": 756,
        "computed_at": "2026-05-06T12:00:00+00:00",
        "age_hours": 3.5,
        "source_file": "best_per_symbol_20260506T120000Z.json",
        "best_per_symbol": [{"symbol": "BTC-USD"}, {"symbol": "ETH-USD"}],
    }


def _leaderboard() -> dict:
    return {
        "metric": "sortino",
        "limit": 10,
        "total_rows": 3,
        "filtered_rows": 3,
        "source_file": "strategy_sweep_20260506T120000Z.json",
        "computed_at": "2026-05-06T12:00:00+00:00",
        "rows": [
            {"strategy_cls": "Trend", "symbol": "BTC-USD", "sortino": 2.4, "total_trades": 12},
            {"strategy_cls": "MeanRev", "symbol": "ETH-USD", "sortino": 1.7, "total_trades": 8},
            {"strategy_cls": "Breakout", "symbol": "SOL-USD", "sortino": 1.2, "total_trades": 9},
        ],
    }


def test_backtest_receipt_is_catalog_grounded_and_paper_only() -> None:
    product = load_product_catalog().get("backtest_receipt")
    registry = load_source_registry()

    receipt = build_backtest_receipt(
        product=product,
        registry=registry,
        summary=_summary(),
        leaderboard=_leaderboard(),
        metric="sortino",
        symbols=("BTC-USD",),
        limit=5,
        generated_at="2026-05-06T12:05:00Z",
    )

    assert receipt["product_id"] == "backtest_receipt"
    assert receipt["artifact_kind"] == "backtest_receipt"
    assert receipt["settlement_mode"] == "simulated_or_testnet"
    assert receipt["live_settlement_allowed"] is False
    assert receipt["paper_only"] is True
    assert receipt["assumptions"]["no_strategy_execution"] is True
    assert receipt["summary"]["total_backtests"] == 756
    assert receipt["leaderboard"]["rows"][0]["symbol"] == "BTC-USD"
    assert receipt["reproducibility"]["hash"]
    assert receipt["artifact_id"].startswith("x402-bt-")
    assert {source["source_id"] for source in receipt["catalog_sources"]} >= {
        "databento",
        "alpaca_market_data",
        "polymarket",
        "bigquery_public",
    }


def test_backtest_receipt_artifact_id_is_deterministic() -> None:
    product = load_product_catalog().get("backtest_receipt")
    registry = load_source_registry()
    receipt = build_backtest_receipt(
        product=product,
        registry=registry,
        summary=_summary(),
        leaderboard=_leaderboard(),
        generated_at="2026-05-06T12:05:00Z",
    )

    artifact_id = receipt.pop("artifact_id")

    assert artifact_id == artifact_id_for_backtest_receipt(receipt)


def test_backtest_receipt_warns_when_artifacts_are_missing() -> None:
    product = load_product_catalog().get("backtest_receipt")
    registry = load_source_registry()

    receipt = build_backtest_receipt(
        product=product,
        registry=registry,
        summary={"have_results": False, "total_backtests": 0},
        leaderboard={"rows": []},
        generated_at="2026-05-06T12:05:00Z",
    )

    assert receipt["ok"] is False
    assert "no local backtest artifacts found" in receipt["warnings"]
    assert "leaderboard has no rows for the requested filter" in receipt["warnings"]
