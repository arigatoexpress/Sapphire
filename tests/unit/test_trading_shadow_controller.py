from __future__ import annotations

import pytest

from lib.trading import shadow_controller as controller


def _market(rows):
    return {
        "generated_at": "2026-04-28T00:00:00+00:00",
        "source": "fixture",
        "stale": False,
        "errors": [],
        "combined_tokens": rows,
    }


def test_shadow_controller_promotes_only_paper_manual_candidates():
    report = controller.build_shadow_trading_report(
        market_universe=_market(
            [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "priority": "high",
                    "tags": ["liked", "core", "robinhood"],
                    "robinhood_symbol": "BTC-USD",
                    "price_usd": 77000,
                    "change_24h_pct": 2.4,
                    "trend_score": 0,
                }
            ]
        ),
        policy=controller.ShadowRiskPolicy(),
    )

    assert report["mode"] == "paper_shadow"
    assert report["live_execution_enabled"] is False
    assert report["risk_policy"]["bounded_candidate_notional_usd"] == 5.0
    assert report["candidates"][0]["symbol"] == "BTC"
    assert report["candidates"][0]["action"] == "buy"
    assert report["candidates"][0]["manual_order_candidate"]["execute_flag_included"] is False
    assert "--execute" not in report["candidates"][0]["manual_order_candidate"]["command"]
    assert all(
        draft["execution_enabled"] is False
        for draft in report["candidates"][0]["order_drafts"]
    )
    assert {
        action["surface"]
        for action in report["blocked_live_actions"]
    } >= {"scheduler_live_submit", "tradingview_webhook_live_submit"}


def test_shadow_controller_blocks_missing_robinhood_or_live_market_data():
    report = controller.build_shadow_trading_report(
        market_universe=_market(
            [
                {
                    "symbol": "HYPE",
                    "name": "Hyperliquid",
                    "priority": "high",
                    "tags": ["liked", "perp"],
                    "robinhood_symbol": None,
                    "price_usd": None,
                    "change_24h_pct": None,
                }
            ]
        )
    )

    assert report["candidates"] == []
    assert report["watchlist"][0]["decision"] == "blocked"
    assert "not_robinhood_crypto_tradable" in report["watchlist"][0]["blockers"]
    assert "missing_live_price" in report["watchlist"][0]["blockers"]
    assert report["operator_next_step"]["status"] == "no_manual_order_candidate"


def test_shadow_controller_chase_guard_blocks_extended_moves():
    row = {
        "symbol": "ETH",
        "name": "Ethereum",
        "priority": "high",
        "tags": ["liked", "core", "preferred", "robinhood"],
        "robinhood_symbol": "ETH-USD",
        "price_usd": 4200,
        "change_24h_pct": 14.0,
    }

    candidate = controller.evaluate_market_row(row, controller.ShadowRiskPolicy())

    assert candidate.decision == "blocked"
    assert candidate.action == "hold"
    assert "chase_guard_triggered" in candidate.blockers


def test_shadow_policy_refuses_live_execution_toggle():
    with pytest.raises(ValueError, match="cannot enable live execution"):
        controller.ShadowRiskPolicy(live_execution_enabled=True)


def test_shadow_policy_caps_requested_notional_to_first_order_limit():
    policy = controller.ShadowRiskPolicy(requested_candidate_notional_usd=100.0)

    assert policy.bounded_candidate_notional_usd == 5.0
