from __future__ import annotations

from lib.trading import strategy_lab as lab


def test_canonicalize_symbol_corrects_known_aliases():
    assert lab.canonicalize_symbol("BINANCE:HYPERUSDT") == "HYPE"
    assert lab.canonicalize_symbol("MATIC-USD") == "POL"
    assert lab.canonicalize_symbol("BTCUSDT") == "BTC"
    assert lab.canonicalize_symbol("ETH/USD") == "ETH"
    assert lab.canonicalize_symbol("KRAKEN:XMRUSD") == "XMR"
    assert lab.canonicalize_symbol("BINANCE:OPUSDT") == "OP"


def test_parse_trending_tokens_marks_liked_and_keeps_unknowns():
    payload = {
        "coins": [
            {
                "item": {
                    "id": "aave",
                    "symbol": "AAVE",
                    "name": "Aave",
                    "score": 0,
                    "market_cap_rank": 54,
                    "data": {
                        "price": 96.5,
                        "price_change_percentage_24h": {"usd": 0.46},
                    },
                }
            },
            {
                "item": {
                    "id": "chip-2",
                    "symbol": "CHIP",
                    "name": "USD.AI",
                    "score": 1,
                    "data": {
                        "price": 0.07,
                        "price_change_percentage_24h": {"usd": -4.37},
                    },
                }
            },
        ]
    }

    rows = lab.parse_trending_tokens(payload, liked_symbols={"AAVE"})

    assert rows[0]["symbol"] == "AAVE"
    assert "liked" in rows[0]["tags"]
    assert rows[0]["change_24h_pct"] == 0.46
    assert rows[1]["symbol"] == "CHIP"
    assert rows[1]["tradingview_symbol"] == "CHIPUSDT"


def test_build_market_universe_without_live_fetch_is_deterministic(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_LIKED_TOKENS", raising=False)

    report = lab.build_market_universe(fetch_live=False)

    symbols = [row["symbol"] for row in report["liked_tokens"]]
    assert symbols[:6] == ["ETH", "BTC", "ZEC", "XMR", "AAVE", "LINK"]
    assert report["stale"] is False
    assert report["venue_matrix"][0]["tradingview"] == "BINANCE:ETHUSDT"
    assert "preferred" in report["liked_tokens"][0]["tags"]
    assert {row["symbol"] for row in report["liked_tokens"]} >= {"ONDO", "UNI", "ENS", "ARB", "OP"}
    assert report["corrected_aliases"]["MATIC"] == "POL"
    ondo = {row["symbol"]: row for row in report["liked_tokens"]}["ONDO"]
    assert ondo["tradingview_symbol"] == "BINANCE:ONDOUSDT"
    assert "tokenized_finance" in ondo["tags"]


def test_order_drafts_never_enable_execution():
    drafts = lab.build_order_drafts("BTCUSDT", "buy", notional_usd=125.0, strategy="unit")

    venues = {draft["venue"]: draft for draft in drafts}
    assert set(venues) >= {"paper", "tradingview_webhook", "robinhood_crypto", "hyperliquid"}
    assert all(draft["execution_enabled"] is False for draft in drafts)
    assert venues["hyperliquid"]["payload"]["requires_wallet_signature"] is True
    assert venues["hyperliquid"]["payload"]["coin"] == "BTC"
    assert venues["robinhood_crypto"]["payload"]["symbol"] == "BTC-USD"
    assert venues["robinhood_crypto"]["payload"]["endpoint"] == "/api/v2/crypto/trading/orders/"
    assert venues["robinhood_crypto"]["payload"]["body_template"]["type"] == "limit"
    assert (
        venues["robinhood_crypto"]["payload"]["body_template"]["limit_order_config"]["quote_amount"]
        == "<usd_quote_amount_after_live_test_cap>"
    )
    assert (
        venues["robinhood_crypto"]["payload"]["live_test_caps"]["first_order_max_notional_usd"]
        == 5.0
    )
    assert (
        venues["robinhood_crypto"]["payload"]["live_test_caps"]["requested_exceeds_first_order_cap"]
        is True
    )


def test_robinhood_sell_draft_requires_position_quantity():
    drafts = lab.build_order_drafts("BTC", "sell", notional_usd=3.0, strategy="unit")
    robinhood = {draft["venue"]: draft for draft in drafts}["robinhood_crypto"]

    config = robinhood["payload"]["body_template"]["limit_order_config"]
    assert robinhood["payload"]["side"] == "sell"
    assert "asset_quantity" in config
    assert "quote_amount" not in config
    assert robinhood["payload"]["live_test_caps"]["requested_exceeds_first_order_cap"] is False


def test_robinhood_hold_draft_has_no_order_body():
    drafts = lab.build_order_drafts("BTC", "hold", notional_usd=3.0, strategy="unit")
    robinhood = {draft["venue"]: draft for draft in drafts}["robinhood_crypto"]

    assert robinhood["payload"]["side"] == "hold"
    assert "body_template" not in robinhood["payload"]
    assert "blocked_reason" in robinhood["payload"]


def test_strategy_lab_report_keeps_live_trading_off(monkeypatch):
    monkeypatch.setattr(lab, "_secret_group_present", lambda **_kwargs: False)

    report = lab.build_strategy_lab_report(fetch_live=False)

    assert report["safety"]["live_trading_enabled"] is False
    assert report["safety"]["execution_stage"] == "paper"
    assert "TRADINGVIEW_EXECUTION_ENABLED=false" in report["safety"]["guards"]
    assert report["tradingview"]["broker_rest_endpoints"][0] == "/config"
    assert report["real_funds_readiness"]["stage"] == "manual_confirmed_crypto_only"
    assert report["real_funds_readiness"]["crypto"]["first_order_max_notional_usd"] == 5.0
    assert (
        report["real_funds_readiness"]["stocks"]["official_public_trading_api_identified"] is False
    )
