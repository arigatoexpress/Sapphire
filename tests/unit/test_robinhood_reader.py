"""Tests for lib/portfolio/robinhood.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.portfolio.robinhood import RobinhoodReader, _encode_query  # type: ignore


def _reader() -> RobinhoodReader:
    reader = RobinhoodReader.__new__(RobinhoodReader)
    reader._available = True
    reader._api_key = "test-key"
    reader._private_bytes = b"0" * 32
    reader._account_cache = {
        "account_number": "ACCT-1",
        "status": "active",
        "buying_power": "2500.00",
        "buying_power_currency": "USD",
        "is_api_tradable": True,
    }
    reader._cost_basis_cache = None
    return reader


class TestEncodeQuery:
    def test_repeats_list_values(self):
        query = _encode_query({"symbol": ["BTC-USD", "ETH-USD"], "limit": 2})
        assert query == "?symbol=BTC-USD&symbol=ETH-USD&limit=2"

    def test_skips_empty_values(self):
        query = _encode_query({"cursor": None, "limit": 10})
        assert query == "?limit=10"


class TestRobinhoodReader:
    def test_get_account_parses_default_crypto_account(self):
        reader = _reader()
        account = reader.get_account()
        assert account["source"] == "robinhood"
        assert account["account_number"] == "ACCT-1"
        assert account["buying_power"] == 2500.0

    def test_get_holdings_reconstructs_cost_basis(self, monkeypatch):
        reader = _reader()

        def fake_get_results(base_path, params=None):
            if base_path == "/api/v2/crypto/trading/holdings/":
                assert params == {"account_number": "ACCT-1"}
                return [
                    {
                        "account_number": "ACCT-1",
                        "asset_code": "BTC",
                        "total_quantity": "0.5",
                        "quantity_available_for_trading": "0.5",
                    },
                    {
                        "account_number": "ACCT-1",
                        "asset_code": "ETH",
                        "total_quantity": "2",
                        "quantity_available_for_trading": "1.5",
                    },
                ]
            if base_path == "/api/v2/crypto/trading/orders/":
                assert params["account_number"] == "ACCT-1"
                return [
                    {
                        "symbol": "BTC-USD",
                        "side": "buy",
                        "state": "filled",
                        "average_price": 60000,
                        "filled_asset_quantity": 1.0,
                        "created_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "symbol": "BTC-USD",
                        "side": "sell",
                        "state": "filled",
                        "average_price": 62000,
                        "filled_asset_quantity": 0.5,
                        "created_at": "2026-01-10T00:00:00Z",
                    },
                    {
                        "symbol": "ETH-USD",
                        "side": "buy",
                        "state": "filled",
                        "average_price": 3000,
                        "filled_asset_quantity": 2.0,
                        "created_at": "2026-01-05T00:00:00Z",
                    },
                ]
            raise AssertionError(base_path)

        monkeypatch.setattr(reader, "_get_results", fake_get_results)
        monkeypatch.setattr(
            reader,
            "_get_best_bid_ask",
            lambda symbols: {"BTC-USD": 65000.0, "ETH-USD": 3200.0},
        )

        holdings = reader.get_holdings()
        assert len(holdings) == 2

        btc = next(h for h in holdings if h["asset_code"] == "BTC")
        eth = next(h for h in holdings if h["asset_code"] == "ETH")

        assert btc["avg_cost"] == 60000.0
        assert round(btc["total_return"], 2) == 2500.0
        assert round(eth["total_return"], 2) == 400.0

    def test_daily_snapshot_degrades_when_cost_basis_missing(self, monkeypatch):
        reader = _reader()

        monkeypatch.setattr(
            reader,
            "get_holdings",
            lambda: [
                {
                    "symbol": "BTC",
                    "qty": 0.5,
                    "price": 65000.0,
                    "market_value": 32500.0,
                    "avg_cost": None,
                    "total_return": None,
                }
            ],
        )
        monkeypatch.setattr(
            reader,
            "get_portfolio_value",
            lambda: {
                "source": "robinhood",
                "equity": 35000.0,
                "cash": 2500.0,
                "holdings_value": 32500.0,
            },
        )

        snap = reader.get_daily_snapshot()
        assert snap["pnl_available"] is False
        assert snap["unrealized_pnl_usd"] is None
        assert snap["positions"][0]["unrealized_pnl_pct"] is None
