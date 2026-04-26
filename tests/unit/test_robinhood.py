"""Edge-case tests for ``lib.portfolio.robinhood``.

Tests-only deliverable. Production source is not modified.

We never hit ``trading.robinhood.com`` and we never read a real key from
``~/.config/sapphire-secrets/``. A deterministic Ed25519 keypair is
generated per-test from a known seed via ``cryptography``. ``urlopen`` is
monkey-patched at the ``urllib.request`` boundary to match the codebase
style used in ``test_security_dependency_scanner.py``.
"""

from __future__ import annotations

import base64
import json
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from lib.portfolio import robinhood as rh

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Deterministic 32-byte Ed25519 seed used across the test file. NOT a real
# key — generated solely from a known repeated byte pattern for reproducible
# signature assertions.
_TEST_SEED = bytes(range(32))
_TEST_API_KEY = "rh-api-test-0000"


def _test_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey, bytes]:
    """Deterministic Ed25519 keypair for the test suite."""
    private = Ed25519PrivateKey.from_private_bytes(_TEST_SEED)
    return private, private.public_key(), _TEST_SEED


def _mock_urlopen_response(payload: Any) -> MagicMock:
    """Build a context-manager-compatible urlopen return value."""
    body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://trading.robinhood.com/test/",
        code=code,
        msg="err",
        hdrs=None,  # type: ignore[arg-type]
        fp=BytesIO(body.encode()),
    )


@pytest.fixture
def secrets_dir(tmp_path, monkeypatch) -> Path:
    """Point ``_SECRETS`` at a temp dir with a valid base64 seed + api key."""
    secrets = tmp_path / "sapphire-secrets"
    secrets.mkdir()
    (secrets / "robinhood_api_key").write_text(_TEST_API_KEY + "\n")
    (secrets / "robinhood_ed25519_private.b64").write_text(
        base64.b64encode(_TEST_SEED).decode() + "\n"
    )
    monkeypatch.setattr(rh, "_SECRETS", secrets)
    return secrets


@pytest.fixture
def reader(secrets_dir) -> rh.RobinhoodReader:
    """Configured RobinhoodReader (stubbed creds, no real network)."""
    return rh.RobinhoodReader()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestAsFloat:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, None),
            ("", None),
            ("not-a-number", None),
            ("1.5", 1.5),
            (2, 2.0),
            (0, 0.0),
            ("-3.25", -3.25),
        ],
    )
    def test_as_float_edge_cases(self, value, expected):
        assert rh._as_float(value) == expected


class TestEncodeQuery:
    def test_empty_returns_empty_string(self):
        assert rh._encode_query(None) == ""
        assert rh._encode_query({}) == ""

    def test_drops_none_values(self):
        # None values must be omitted from the encoded query string entirely.
        assert rh._encode_query({"a": None, "b": "1"}) == "?b=1"

    def test_list_values_expand_with_doseq(self):
        # Multi-symbol best_bid_ask query uses list params.
        result = rh._encode_query({"symbol": ["BTC-USD", "ETH-USD"]})
        # urlencode preserves order; one key per item, encoded once each.
        assert result.startswith("?")
        assert "symbol=BTC-USD" in result
        assert "symbol=ETH-USD" in result


# ---------------------------------------------------------------------------
# Credentials loading
# ---------------------------------------------------------------------------


class TestLoadCredentials:
    def test_loads_from_secrets_dir(self, secrets_dir):
        api_key, private_bytes = rh._load_credentials()
        assert api_key == _TEST_API_KEY
        assert private_bytes == _TEST_SEED

    def test_missing_files_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rh, "_SECRETS", tmp_path / "missing")
        with pytest.raises(FileNotFoundError):
            rh._load_credentials()

    def test_malformed_base64_raises(self, tmp_path, monkeypatch):
        secrets = tmp_path / "broken-secrets"
        secrets.mkdir()
        (secrets / "robinhood_api_key").write_text("k")
        (secrets / "robinhood_ed25519_private.b64").write_text("***not-base64***")
        monkeypatch.setattr(rh, "_SECRETS", secrets)
        # base64.b64decode raises binascii.Error on garbage input.
        with pytest.raises(Exception):
            rh._load_credentials()


# ---------------------------------------------------------------------------
# Ed25519 signing
# ---------------------------------------------------------------------------


class TestSignRequest:
    def test_signature_verifies_with_public_key(self, monkeypatch):
        # Pin the timestamp so message bytes are reproducible across machines.
        monkeypatch.setattr(rh.time, "time", lambda: 1_700_000_000)
        headers = rh._sign_request(
            api_key=_TEST_API_KEY,
            private_bytes=_TEST_SEED,
            method="GET",
            path="/api/v2/crypto/trading/accounts/",
            body="",
        )
        # x-api-key + timestamp + path + method + body — must match what the
        # signer produced. Verifying with the public key proves the signing
        # message was canonicalised exactly that way.
        assert headers["x-api-key"] == _TEST_API_KEY
        assert headers["x-timestamp"] == "1700000000"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

        message = (
            f"{_TEST_API_KEY}1700000000/api/v2/crypto/trading/accounts/GET"
        ).encode()
        _, public_key, _ = _test_keypair()
        public_key.verify(base64.b64decode(headers["x-signature"]), message)

    def test_method_is_uppercased_in_signature(self, monkeypatch):
        # The signer uppercases the method — passing "get" must produce the
        # same signature as "GET" for the same timestamp.
        monkeypatch.setattr(rh.time, "time", lambda: 1_700_000_000)
        h_lower = rh._sign_request(_TEST_API_KEY, _TEST_SEED, "get", "/x", "")
        h_upper = rh._sign_request(_TEST_API_KEY, _TEST_SEED, "GET", "/x", "")
        assert h_lower["x-signature"] == h_upper["x-signature"]

    def test_body_canonicalisation_changes_signature(self, monkeypatch):
        # Different body bytes → different signature. This is the contract:
        # the body string is part of the signing message verbatim.
        monkeypatch.setattr(rh.time, "time", lambda: 1_700_000_000)
        h1 = rh._sign_request(_TEST_API_KEY, _TEST_SEED, "POST", "/x", '{"a":1}')
        h2 = rh._sign_request(_TEST_API_KEY, _TEST_SEED, "POST", "/x", '{"a":2}')
        assert h1["x-signature"] != h2["x-signature"]

    def test_malformed_private_bytes_raise(self):
        # Ed25519PrivateKey.from_private_bytes requires exactly 32 bytes.
        with pytest.raises(Exception):
            rh._sign_request(_TEST_API_KEY, b"too-short", "GET", "/x", "")

    def test_signature_does_not_verify_against_wrong_message(self, monkeypatch):
        monkeypatch.setattr(rh.time, "time", lambda: 1_700_000_000)
        headers = rh._sign_request(_TEST_API_KEY, _TEST_SEED, "GET", "/x", "")
        _, public_key, _ = _test_keypair()
        with pytest.raises(InvalidSignature):
            public_key.verify(base64.b64decode(headers["x-signature"]), b"tampered")


# ---------------------------------------------------------------------------
# _request — HTTP error / retry behaviour
# ---------------------------------------------------------------------------


class TestRequestNetwork:
    @patch("urllib.request.urlopen")
    def test_4xx_raises_immediately_no_retry(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(401, "unauthorized")
        with pytest.raises(RuntimeError, match="HTTP 401"):
            rh._request("GET", "/x", _TEST_API_KEY, _TEST_SEED, timeout=1)
        assert mock_urlopen.call_count == 1

    @patch("urllib.request.urlopen")
    def test_5xx_retries_three_times_then_raises(self, mock_urlopen, monkeypatch):
        # No real sleeps in tests.
        monkeypatch.setattr(rh.time, "sleep", lambda *_a, **_k: None)
        mock_urlopen.side_effect = _http_error(503, "down")
        with pytest.raises(RuntimeError, match="HTTP 503"):
            rh._request("GET", "/x", _TEST_API_KEY, _TEST_SEED, timeout=1)
        # 3 attempts total — the loop runs `range(3)`.
        assert mock_urlopen.call_count == 3

    @patch("urllib.request.urlopen")
    def test_timeout_retries_then_raises(self, mock_urlopen, monkeypatch):
        monkeypatch.setattr(rh.time, "sleep", lambda *_a, **_k: None)
        mock_urlopen.side_effect = TimeoutError("read timed out")
        with pytest.raises(RuntimeError, match="TimeoutError"):
            rh._request("GET", "/x", _TEST_API_KEY, _TEST_SEED, timeout=1)
        assert mock_urlopen.call_count == 3

    @patch("urllib.request.urlopen")
    def test_5xx_then_success_returns_payload(self, mock_urlopen, monkeypatch):
        # First attempt 5xx, second attempt succeeds.
        monkeypatch.setattr(rh.time, "sleep", lambda *_a, **_k: None)
        mock_urlopen.side_effect = [
            _http_error(502, "bad gateway"),
            _mock_urlopen_response({"results": [{"ok": True}]}),
        ]
        result = rh._request("GET", "/x", _TEST_API_KEY, _TEST_SEED, timeout=1)
        assert result == {"results": [{"ok": True}]}
        assert mock_urlopen.call_count == 2

    @patch("urllib.request.urlopen")
    def test_malformed_json_propagates_as_runtime_error(self, mock_urlopen):
        # urlopen succeeds but body is not JSON. The catch-all `except Exception`
        # in `_request` re-wraps as RuntimeError.
        mock_urlopen.return_value = _mock_urlopen_response(b"not-json")
        with pytest.raises(RuntimeError, match="JSONDecodeError|ValueError"):
            rh._request("GET", "/x", _TEST_API_KEY, _TEST_SEED, timeout=1)


# ---------------------------------------------------------------------------
# RobinhoodReader.__init__ + is_configured
# ---------------------------------------------------------------------------


class TestReaderInit:
    def test_unavailable_when_creds_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rh, "_SECRETS", tmp_path / "missing")
        r = rh.RobinhoodReader()
        assert r.is_configured() is False
        # Public methods must degrade safely — no exception, sentinel return.
        assert r.get_account()["source"] == "unavailable"
        assert r.get_holdings() == []
        assert r.get_portfolio_value()["source"] == "unavailable"
        assert r.get_daily_snapshot() == {}

    def test_configured_when_creds_present(self, reader):
        assert reader.is_configured() is True

    def test_get_reader_factory_returns_instance(self, secrets_dir):
        r = rh.get_reader()
        assert isinstance(r, rh.RobinhoodReader)


# ---------------------------------------------------------------------------
# Account selection — prefers is_api_tradable
# ---------------------------------------------------------------------------


class TestAccountSelection:
    def test_picks_api_tradable_account(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda method, path, body=None, timeout=15: {
                "results": [
                    {"account_number": "A0", "is_api_tradable": False, "buying_power": "1.0"},
                    {"account_number": "A1", "is_api_tradable": True, "buying_power": "100.0"},
                ],
                "next": None,
            },
        )
        record = reader._get_account_record()
        assert record["account_number"] == "A1"
        # Cached on second call.
        assert reader._get_account_record()["account_number"] == "A1"

    def test_falls_back_to_first_account_when_none_tradable(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda method, path, body=None, timeout=15: {
                "results": [
                    {"account_number": "A0", "is_api_tradable": False},
                    {"account_number": "A1", "is_api_tradable": False},
                ],
                "next": None,
            },
        )
        record = reader._get_account_record()
        assert record["account_number"] == "A0"

    def test_no_accounts_returns_none(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {"results": [], "next": None},
        )
        assert reader._get_account_record() is None
        assert reader._get_account_number() is None


# ---------------------------------------------------------------------------
# _get_results — pagination + cycle guard
# ---------------------------------------------------------------------------


class TestPagination:
    def test_follows_next_link_and_aggregates(self, reader, monkeypatch):
        pages = [
            {
                "results": [{"id": 1}],
                "next": rh._BASE + "/api/v2/crypto/trading/accounts/?cursor=2",
            },
            {"results": [{"id": 2}, {"id": 3}], "next": None},
        ]
        calls: list[str] = []

        def fake_request(method, path, body=None, timeout=15):
            calls.append(path)
            return pages.pop(0)

        monkeypatch.setattr(reader, "_request_json", fake_request)
        results = reader._get_results("/api/v2/crypto/trading/accounts/")
        assert [r["id"] for r in results] == [1, 2, 3]
        # Second request used the relativized cursor URL.
        assert calls[1] == "/api/v2/crypto/trading/accounts/?cursor=2"

    def test_pagination_cycle_breaks(self, reader, monkeypatch):
        # If the API returns the same `next` repeatedly, the loop must exit
        # via the `seen_paths` guard rather than spin forever.
        same_next = rh._BASE + "/x"
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {"results": [{"id": 1}], "next": same_next},
        )
        results = reader._get_results("/x")
        # First page accepted, then `next` matches the already-seen path → stop.
        assert results == [{"id": 1}]


# ---------------------------------------------------------------------------
# best_bid_ask — bid/ask edge cases
# ---------------------------------------------------------------------------


class TestBestBidAsk:
    def test_empty_symbols_returns_empty(self, reader):
        assert reader._get_best_bid_ask([]) == {}

    def test_averages_bid_and_ask(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "BTC-USD", "bid": "100", "ask": "200"}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["BTC-USD"]) == {"BTC-USD": 150.0}

    def test_zero_spread(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "ETH-USD", "bid": "1000", "ask": "1000"}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["ETH-USD"]) == {"ETH-USD": 1000.0}

    def test_crossed_market_still_averages(self, reader, monkeypatch):
        # bid > ask is unusual but the helper trusts the upstream feed; it
        # still returns the midpoint rather than rejecting the row.
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "SOL-USD", "bid": "120", "ask": "100"}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["SOL-USD"]) == {"SOL-USD": 110.0}

    def test_missing_ask_falls_back_to_bid(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "BTC-USD", "bid": "100", "ask": None}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["BTC-USD"]) == {"BTC-USD": 100.0}

    def test_missing_bid_falls_back_to_ask(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "BTC-USD", "bid": None, "ask": "200"}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["BTC-USD"]) == {"BTC-USD": 200.0}

    def test_both_sides_missing_skipped(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "BTC-USD", "bid": None, "ask": None}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["BTC-USD"]) == {}

    def test_symbol_case_normalised_to_upper(self, reader, monkeypatch):
        # Lowercase upstream symbol must be uppercased so dict lookups hit
        # whatever the holdings code computed (asset_code.upper()).
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{"symbol": "btc-usd", "bid": "1", "ask": "3"}],
                "next": None,
            },
        )
        assert reader._get_best_bid_ask(["btc-usd"]) == {"BTC-USD": 2.0}


# ---------------------------------------------------------------------------
# Cost-basis reconstruction
# ---------------------------------------------------------------------------


def _order(
    *,
    symbol: str,
    side: str,
    qty: str,
    price: str,
    state: str = "filled",
    created_at: str = "2024-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "side": side,
        "filled_asset_quantity": qty,
        "average_price": price,
        "state": state,
        "created_at": created_at,
    }


def _stub_orders(reader: rh.RobinhoodReader, monkeypatch, orders: list[dict[str, Any]]) -> None:
    """Stub `_get_results` to return a fixed order list."""
    monkeypatch.setattr(
        reader,
        "_get_results",
        lambda base_path, params=None: list(orders) if "orders" in base_path else [],
    )


class TestCostBasisReconstruction:
    def test_empty_history(self, reader, monkeypatch):
        _stub_orders(reader, monkeypatch, [])
        assert reader._reconstruct_cost_basis("ACC1") == {}

    def test_single_buy(self, reader, monkeypatch):
        _stub_orders(
            reader,
            monkeypatch,
            [_order(symbol="BTC-USD", side="buy", qty="2", price="100")],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        assert cb == {"BTC": {"qty": 2.0, "avg_cost": 100.0}}

    def test_multi_buy_weighted_average(self, reader, monkeypatch):
        # 2 @ 100 + 3 @ 200 = 5 units, total cost 800 → avg 160.
        _stub_orders(
            reader,
            monkeypatch,
            [
                _order(symbol="BTC-USD", side="buy", qty="2", price="100",
                       created_at="2024-01-01T00:00:00Z"),
                _order(symbol="BTC-USD", side="buy", qty="3", price="200",
                       created_at="2024-02-01T00:00:00Z"),
            ],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        assert cb == {"BTC": {"qty": 5.0, "avg_cost": 160.0}}

    def test_buy_then_partial_sell_keeps_avg_cost(self, reader, monkeypatch):
        # 5 @ 100, sell 2. Remaining qty=3, cost reduced by 2*100=200,
        # leaving cost=300 → avg_cost=100.
        _stub_orders(
            reader,
            monkeypatch,
            [
                _order(symbol="BTC-USD", side="buy", qty="5", price="100",
                       created_at="2024-01-01T00:00:00Z"),
                _order(symbol="BTC-USD", side="sell", qty="2", price="150",
                       created_at="2024-02-01T00:00:00Z"),
            ],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        assert cb["BTC"]["qty"] == 3.0
        assert cb["BTC"]["avg_cost"] == pytest.approx(100.0)

    def test_sell_only_without_prior_buy_zeros_position(self, reader, monkeypatch):
        # Selling something the cost-basis reconstruction never saw bought
        # is a no-op (position skipped via the qty<=0 branch).
        _stub_orders(
            reader,
            monkeypatch,
            [_order(symbol="BTC-USD", side="sell", qty="1", price="100")],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        # Implementation: setdefault creates the bucket, then the sell branch
        # zeros qty/cost. Net result is qty=0, avg_cost=0.0.
        assert cb["BTC"]["qty"] == 0.0
        assert cb["BTC"]["avg_cost"] == 0.0

    def test_cancelled_orders_excluded(self, reader, monkeypatch):
        _stub_orders(
            reader,
            monkeypatch,
            [
                _order(symbol="BTC-USD", side="buy", qty="2", price="100", state="cancelled"),
                _order(symbol="BTC-USD", side="buy", qty="1", price="500", state="filled"),
            ],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        assert cb == {"BTC": {"qty": 1.0, "avg_cost": 500.0}}

    def test_partial_fills_included(self, reader, monkeypatch):
        _stub_orders(
            reader,
            monkeypatch,
            [
                _order(symbol="BTC-USD", side="buy", qty="0.5", price="100",
                       state="partially_filled"),
                _order(symbol="BTC-USD", side="buy", qty="1.5", price="200",
                       state="filled"),
            ],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        # 0.5*100 + 1.5*200 = 350; qty=2.0; avg=175.
        assert cb["BTC"]["qty"] == 2.0
        assert cb["BTC"]["avg_cost"] == pytest.approx(175.0)

    def test_orders_sorted_chronologically(self, reader, monkeypatch):
        # Late-arriving (out-of-order) sell must apply against the earlier
        # buy when sorted, not before it.
        _stub_orders(
            reader,
            monkeypatch,
            [
                _order(symbol="BTC-USD", side="sell", qty="1", price="200",
                       created_at="2024-02-01T00:00:00Z"),
                _order(symbol="BTC-USD", side="buy", qty="2", price="100",
                       created_at="2024-01-01T00:00:00Z"),
            ],
        )
        cb = reader._reconstruct_cost_basis("ACC1")
        # After sorting: buy 2@100 then sell 1 → qty=1, cost reduced 100.
        assert cb["BTC"]["qty"] == 1.0
        assert cb["BTC"]["avg_cost"] == pytest.approx(100.0)

    def test_zero_qty_or_missing_price_skipped(self, reader, monkeypatch):
        _stub_orders(
            reader,
            monkeypatch,
            [
                # qty=0 → skipped
                _order(symbol="BTC-USD", side="buy", qty="0", price="100"),
                # missing price → skipped
                {"symbol": "BTC-USD", "side": "buy", "filled_asset_quantity": "1",
                 "average_price": None, "state": "filled", "created_at": "2024-01-01"},
                # malformed symbol (no dash) → skipped
                _order(symbol="BTCUSD", side="buy", qty="1", price="100"),
                # unknown side → skipped
                _order(symbol="BTC-USD", side="unknown", qty="1", price="100"),
            ],
        )
        # Nothing valid → no positions recorded.
        assert reader._reconstruct_cost_basis("ACC1") == {}


# ---------------------------------------------------------------------------
# get_account — shaping + degraded paths
# ---------------------------------------------------------------------------


class TestGetAccount:
    def test_shapes_account_payload(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {
                "results": [{
                    "account_number": "ACC1",
                    "is_api_tradable": True,
                    "status": "active",
                    "account_type": "crypto",
                    "buying_power": "1234.56",
                    "buying_power_currency": "USD",
                    "fee_tier_status": {"fee_ratio": "0.0025"},
                }],
                "next": None,
            },
        )
        out = reader.get_account()
        assert out["source"] == "robinhood"
        assert out["account_number"] == "ACC1"
        assert out["buying_power"] == 1234.56
        assert out["buying_power_currency"] == "USD"
        assert out["is_api_tradable"] is True
        assert out["fee_ratio"] == pytest.approx(0.0025)

    def test_no_account_returns_unavailable(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_request_json",
            lambda *a, **k: {"results": [], "next": None},
        )
        out = reader.get_account()
        assert out["source"] == "unavailable"
        assert "error" in out


# ---------------------------------------------------------------------------
# get_holdings — full integration with mocked transport
# ---------------------------------------------------------------------------


class TestGetHoldings:
    def test_holdings_with_prices_and_cost_basis(self, reader, monkeypatch):
        # Stub _get_results across the three endpoints holdings touches.
        accounts_payload = [
            {"account_number": "ACC1", "is_api_tradable": True, "buying_power": "100"}
        ]
        holdings_payload = [
            {"asset_code": "btc", "total_quantity": "2",
             "quantity_available_for_trading": "2", "account_number": "ACC1"},
            {"asset_code": "ETH", "total_quantity": "0",  # zero qty filtered out
             "quantity_available_for_trading": "0", "account_number": "ACC1"},
            {"asset_code": "", "total_quantity": "1",  # empty asset filtered out
             "account_number": "ACC1"},
        ]
        prices_payload = [{"symbol": "BTC-USD", "bid": "100", "ask": "200"}]
        orders_payload = [_order(symbol="BTC-USD", side="buy", qty="2", price="50")]

        def fake_get_results(base_path, params=None):
            if base_path.startswith("/api/v2/crypto/trading/accounts"):
                return accounts_payload
            if base_path.startswith("/api/v2/crypto/trading/holdings"):
                return holdings_payload
            if base_path.startswith("/api/v2/crypto/marketdata/best_bid_ask"):
                return prices_payload
            if base_path.startswith("/api/v2/crypto/trading/orders"):
                return orders_payload
            return []

        monkeypatch.setattr(reader, "_get_results", fake_get_results)
        rows = reader.get_holdings()
        # Only BTC survives the filters. Lowercase asset_code is uppercased.
        assert len(rows) == 1
        btc = rows[0]
        assert btc["asset_code"] == "BTC"
        assert btc["qty"] == 2.0
        assert btc["price"] == pytest.approx(150.0)
        assert btc["avg_cost"] == pytest.approx(50.0)
        assert btc["market_value"] == pytest.approx(300.0)
        # total_return = (price-avg_cost)*qty = (150-50)*2 = 200
        assert btc["total_return"] == pytest.approx(200.0)
        # Single position → 100% weight.
        assert btc["weight"] == pytest.approx(100.0)

    def test_holdings_empty_returns_empty_list(self, reader, monkeypatch):
        monkeypatch.setattr(
            reader,
            "_get_results",
            lambda base_path, params=None: (
                [{"account_number": "ACC1", "is_api_tradable": True}]
                if base_path.startswith("/api/v2/crypto/trading/accounts")
                else []
            ),
        )
        assert reader.get_holdings() == []

    def test_currency_case_mismatch_normalised(self, reader, monkeypatch):
        # Holdings come back with lowercase `btc`, prices come back with
        # uppercase `BTC-USD`. The reader must align them so price binds.
        accounts_payload = [{"account_number": "ACC1", "is_api_tradable": True}]
        holdings_payload = [
            {"asset_code": "btc", "total_quantity": "1",
             "quantity_available_for_trading": "1", "account_number": "ACC1"}
        ]
        prices_payload = [{"symbol": "BTC-USD", "bid": "1000", "ask": "1000"}]

        def fake_get_results(base_path, params=None):
            if "accounts" in base_path:
                return accounts_payload
            if "holdings" in base_path:
                return holdings_payload
            if "best_bid_ask" in base_path:
                return prices_payload
            return []

        monkeypatch.setattr(reader, "_get_results", fake_get_results)
        rows = reader.get_holdings()
        assert rows[0]["price"] == 1000.0
        assert rows[0]["market_value"] == 1000.0


# ---------------------------------------------------------------------------
# get_portfolio_value + get_snapshot + get_daily_snapshot
# ---------------------------------------------------------------------------


class TestPortfolioShapes:
    def _wire_reader(self, reader, monkeypatch, holdings, account):
        # Cheap shortcut: monkeypatch the higher-level methods directly so we
        # don't re-run the whole transport stack for each shape test.
        monkeypatch.setattr(reader, "get_holdings", lambda: holdings)
        monkeypatch.setattr(reader, "get_account", lambda: account)

    def test_portfolio_value_aggregates_equity(self, reader, monkeypatch):
        self._wire_reader(
            reader,
            monkeypatch,
            holdings=[
                {"asset_code": "BTC", "qty": 2.0, "price": 150.0,
                 "avg_cost": 50.0, "market_value": 300.0, "total_return": 200.0},
            ],
            account={"source": "robinhood", "buying_power": 1000.0},
        )
        pv = reader.get_portfolio_value()
        assert pv["source"] == "robinhood"
        assert pv["holdings_value"] == 300.0
        assert pv["buying_power"] == 1000.0
        assert pv["equity"] == 1300.0
        assert pv["total_return"] == 200.0
        # cost_basis_total = 50*2 = 100, return 200 → 200%
        assert pv["total_return_pct"] == pytest.approx(200.0)
        assert pv["position_count"] == 1

    def test_snapshot_sectors_when_no_value(self, reader, monkeypatch):
        # No holdings, no cash → no sectors/asset_classes; total_value = 0.
        self._wire_reader(
            reader,
            monkeypatch,
            holdings=[],
            account={"source": "robinhood", "buying_power": 0.0},
        )
        snap = reader.get_snapshot()
        assert snap["source"] == "robinhood"
        assert snap["total_value"] == 0.0
        assert snap["sectors"] == []
        assert snap["asset_classes"] == []

    def test_daily_snapshot_returns_empty_when_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rh, "_SECRETS", tmp_path / "missing")
        r = rh.RobinhoodReader()
        assert r.get_daily_snapshot() == {}
