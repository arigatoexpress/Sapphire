from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "robinhood_live_readiness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("robinhood_live_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_report_is_offline_and_blocked(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "credential_presence",
        lambda: {
            "configured": True,
            "env": {},
            "files": {},
            "values_redacted": True,
        },
    )

    report = module.collect_report(symbol="BTC", action="buy", notional_usd=5.0)

    assert report["network_calls_performed"] is False
    assert report["secret_values_read"] is False
    assert report["verdict"] == "BLOCKED_PENDING_MANUAL_CONFIRMATION"
    assert report["order_draft"]["payload"]["symbol"] == "BTC-USD"
    assert report["order_draft"]["payload"]["body_template"]["type"] == "limit"


def test_render_markdown_keeps_confirmation_wall_visible(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module,
        "credential_presence",
        lambda: {
            "configured": False,
            "env": {},
            "files": {},
            "values_redacted": True,
        },
    )

    report = module.collect_report(symbol="BTC", action="buy", notional_usd=5.0)
    rendered = module.render_markdown(report)

    assert "Network calls performed: `False`" in rendered
    assert "Secret values read: `False`" in rendered
    assert "no real order without explicit operator order details" in rendered


def test_live_read_only_ready_report_uses_redacted_account(monkeypatch):
    module = _load_module()

    class FakeReader:
        def is_configured(self):
            return True

        def get_account(self):
            return {
                "source": "robinhood",
                "account_number": "ACCT123456789",
                "status": "active",
                "buying_power": 50.0,
                "is_api_tradable": True,
            }

        def _get_results(self, base_path, params=None):
            if base_path == "/api/v2/crypto/marketdata/best_bid_ask/":
                return [
                    {
                        "symbol": "BTC-USD",
                        "price": "100000",
                        "bid_inclusive_of_sell_spread": "99950",
                        "ask_inclusive_of_buy_spread": "100050",
                    }
                ]
            if base_path == "/api/v2/crypto/trading/trading_pairs/":
                return [{"symbol": "BTC-USD", "status": "tradable"}]
            raise AssertionError(base_path)

        def _request_json(self, method, path):
            assert method == "GET"
            assert path.startswith("/api/v2/crypto/trading/estimated_price/?")
            return {
                "results": [
                    {
                        "symbol": "BTC-USD",
                        "side": "ask",
                        "price": "100050",
                        "quantity": "0.000049975012",
                    }
                ]
            }

    monkeypatch.setattr(module, "_reader_class", lambda: FakeReader)

    report = module.collect_report(
        symbol="BTC",
        action="buy",
        notional_usd=5.0,
        live_read_only=True,
        max_spread_bps=20.0,
    )

    assert report["verdict"] == "READY_FOR_MANUAL_CONFIRMATION"
    assert report["network_calls_performed"] is True
    assert report["secret_values_read"] is True
    assert report["secret_values_printed"] is False
    assert report["live_read_only"]["account"]["account_number_masked"] == "ACCT...6789"
    assert "account_number" not in report["live_read_only"]["account"]
    assert report["live_read_only"]["quote"]["spread_bps"] == 10.0
    assert report["live_read_only"]["quote"]["bid_ask_crossed"] is False


def test_live_read_only_blocks_wide_spread(monkeypatch):
    module = _load_module()

    class FakeReader:
        def is_configured(self):
            return True

        def get_account(self):
            return {
                "source": "robinhood",
                "account_number": "ACCT123456789",
                "status": "active",
                "buying_power": 50.0,
                "is_api_tradable": True,
            }

        def _get_results(self, base_path, params=None):
            if base_path == "/api/v2/crypto/marketdata/best_bid_ask/":
                return [
                    {
                        "symbol": "BTC-USD",
                        "price": "100000",
                        "bid_inclusive_of_sell_spread": "98000",
                        "ask_inclusive_of_buy_spread": "102000",
                    }
                ]
            if base_path == "/api/v2/crypto/trading/trading_pairs/":
                return [{"symbol": "BTC-USD", "status": "tradable"}]
            raise AssertionError(base_path)

        def _request_json(self, method, path):
            return {"results": [{"symbol": "BTC-USD", "side": "ask", "price": "102000"}]}

    monkeypatch.setattr(module, "_reader_class", lambda: FakeReader)

    report = module.collect_report(
        symbol="BTC",
        action="buy",
        notional_usd=5.0,
        live_read_only=True,
        max_spread_bps=20.0,
    )

    assert report["verdict"] == "BLOCKED_LIVE_READINESS_GATES"
    assert report["live_read_only"]["gates"]["spread_within_threshold"] is False


def test_quote_summary_uses_absolute_spread_for_crossed_inclusive_quote():
    module = _load_module()

    quote = module._summarize_quote(
        "BTC-USD",
        {
            "symbol": "BTC-USD",
            "price": "100",
            "bid_inclusive_of_sell_spread": "101",
            "ask_inclusive_of_buy_spread": "99",
        },
    )

    assert quote["spread_bps"] == 200.0
    assert quote["bid_ask_crossed"] is True


def test_estimated_price_summary_accepts_ask_field():
    module = _load_module()

    summary = module._summarize_estimated_price(
        {
            "symbol": "BTC-USD",
            "side": "ask",
            "ask": "100.5",
            "est_fee": "0.04",
            "est_total_cost": "5.04",
        }
    )

    assert summary["price"] == 100.5
    assert summary["estimated_fee"] == 0.04
    assert summary["estimated_total_cost"] == 5.04
