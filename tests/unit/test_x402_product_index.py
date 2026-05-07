"""Tests for the x402 product discovery index."""

from __future__ import annotations

from lib.payments.x402_product_index import build_product_index
from lib.payments.x402_products import load_product_catalog, load_source_registry


def test_product_index_lists_products_and_safety_posture() -> None:
    payload = build_product_index(
        load_product_catalog(),
        load_source_registry(),
        generated_at="2026-05-06T19:45:00Z",
    )

    assert payload["ok"] is True
    assert payload["generated_at"] == "2026-05-06T19:45:00Z"
    assert payload["summary"]["product_count"] >= 8
    assert payload["summary"]["live_settlement_allowed_count"] == 0
    assert payload["safety"] == {
        "live_settlement_default": False,
        "real_trading_enabled": False,
        "telegram_sends_enabled": False,
        "production_mutation_enabled": False,
    }
    by_id = {product["product_id"]: product for product in payload["products"]}
    assert by_id["market_regime_report"]["route"] == "/api/x402/market-regime"
    assert by_id["backtest_receipt"]["route"] == "/api/x402/backtest"
    assert by_id["agentwiki_builder_brief"]["category"] == "agentwiki"
    assert by_id["backtest_receipt"]["readiness"] == "source_review_required"
    assert by_id["agentwiki_builder_brief"]["readiness"] == "source_review_required"
    assert by_id["backtest_receipt"]["source_count"] >= 1


def test_product_index_marks_all_sources_allowed() -> None:
    payload = build_product_index(load_product_catalog(), load_source_registry())

    for product in payload["products"]:
        assert all(source["allowed"] for source in product["sources"])
