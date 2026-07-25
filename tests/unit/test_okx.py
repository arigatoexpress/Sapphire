"""Tests for ``lib.portfolio.okx``.

Never hits ``www.okx.com`` and never reads a real credential from
``~/.config/sapphire-secrets/``. Credentials are monkey-patched at the
``_load_credentials`` boundary and ``urlopen`` is patched at
``urllib.request``, matching the style of ``test_robinhood.py``.
"""

from __future__ import annotations

import base64
import hmac
import json
from hashlib import sha256
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lib.portfolio import okx

# Deterministic fake credentials — not real, and never sent anywhere.
_KEY = "okx-key-test-0000"
_SECRET = "okx-secret-test-0000"
_PASS = "okx-pass-test"


def _response(payload: dict[str, Any]) -> MagicMock:
    """Build a context-manager mock shaped like ``urlopen``'s return."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _ok(data: list[dict[str, Any]]) -> dict[str, Any]:
    return {"code": "0", "msg": "", "data": data}


@pytest.fixture
def configured_reader(monkeypatch: pytest.MonkeyPatch) -> okx.OKXReader:
    monkeypatch.setattr(okx, "_load_credentials", lambda: (_KEY, _SECRET, _PASS))
    monkeypatch.setattr(okx, "_simulated_enabled", lambda: False)
    return okx.OKXReader()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_reader_not_configured_when_credentials_missing(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    assert reader.is_configured() is False
    assert reader.get_holdings() == []
    assert reader.get_account()["source"] == "unavailable"
    assert reader.get_portfolio_value()["source"] == "unavailable"


def test_partial_credentials_are_not_configured(monkeypatch):
    """All three components are required — a key without a passphrase is unusable."""
    monkeypatch.setattr(okx, "_load_credentials", lambda: (_KEY, _SECRET, ""))
    assert okx.OKXReader().is_configured() is False


def test_snapshot_without_credentials_is_safe(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    snap = okx.OKXReader().get_snapshot()
    assert snap["source"] == "unavailable"
    assert snap["total_value"] == 0.0
    assert snap["holdings"] == []
    assert snap["error"]


def test_read_secret_prefers_file_over_env(monkeypatch, tmp_path):
    (tmp_path / "okx_api_key").write_text("from-file\n")
    monkeypatch.setattr(okx, "_SECRETS", tmp_path)
    monkeypatch.setenv("OKX_API_KEY", "from-env")
    assert okx._read_secret("okx_api_key", "OKX_API_KEY") == "from-file"


def test_read_secret_falls_back_to_env(monkeypatch, tmp_path):
    monkeypatch.setattr(okx, "_SECRETS", tmp_path)
    monkeypatch.setenv("OKX_API_SECRET", "from-env")
    assert okx._read_secret("okx_api_secret", "OKX_API_SECRET") == "from-env"


def test_read_secret_returns_empty_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(okx, "_SECRETS", tmp_path)
    monkeypatch.delenv("OKX_PASSPHRASE", raising=False)
    assert okx._read_secret("okx_passphrase", "OKX_PASSPHRASE") == ""


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_signature_matches_okx_contract():
    """Signature is base64(HMAC-SHA256(ts + METHOD + path + body, secret))."""
    ts = "2026-07-25T09:08:57.715Z"
    path = "/api/v5/account/balance"
    sig = okx._sign_request(_SECRET, ts, "GET", path)
    expected = base64.b64encode(
        hmac.new(_SECRET.encode(), f"{ts}GET{path}".encode(), sha256).digest()
    ).decode()
    assert sig == expected


def test_signature_covers_query_string():
    """Query params are part of the signed path — dropping them breaks auth."""
    ts = "2026-07-25T09:08:57.715Z"
    bare = okx._sign_request(_SECRET, ts, "GET", "/api/v5/asset/balances")
    with_query = okx._sign_request(_SECRET, ts, "GET", "/api/v5/asset/balances?ccy=BTC")
    assert bare != with_query


def test_signature_method_is_uppercased():
    ts = "2026-07-25T09:08:57.715Z"
    assert okx._sign_request(_SECRET, ts, "get", "/x") == okx._sign_request(
        _SECRET, ts, "GET", "/x"
    )


def test_timestamp_format_is_iso8601_milliseconds():
    ts = okx._timestamp()
    # OKX rejects anything that is not exactly ...THH:MM:SS.mmmZ
    assert ts.endswith("Z")
    assert len(ts) == 24
    assert ts[10] == "T" and ts[19] == "."


def test_auth_headers_present_on_private_request(configured_reader, monkeypatch):
    captured: dict[str, Any] = {}

    def fake_urlopen(req, **_kwargs):
        captured["headers"] = dict(req.headers)
        captured["url"] = req.full_url
        return _response(_ok([]))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    configured_reader._private_get("/api/v5/account/balance")

    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["Ok-access-key".lower()] == _KEY
    assert headers["Ok-access-passphrase".lower()] == _PASS
    assert headers["Ok-access-sign".lower()]
    assert headers["Ok-access-timestamp".lower()]


def test_public_request_sends_no_credentials(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_urlopen(req, **_kwargs):
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _response(_ok([]))

    monkeypatch.setattr(okx, "_load_credentials", lambda: (_KEY, _SECRET, _PASS))
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    okx.OKXReader()._public_get("/api/v5/market/tickers", {"instType": "SPOT"})

    assert "ok-access-key" not in captured["headers"]
    assert "ok-access-sign" not in captured["headers"]


def test_browser_user_agent_is_sent(monkeypatch):
    """Cloudflare 403s the default Python-urllib UA — the header is load-bearing."""
    captured: dict[str, Any] = {}

    def fake_urlopen(req, **_kwargs):
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _response(_ok([]))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    okx._request("GET", "/api/v5/market/tickers")
    assert "Mozilla/5.0" in captured["headers"]["user-agent"]


def test_simulated_flag_adds_demo_header(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_urlopen(req, **_kwargs):
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _response(_ok([]))

    monkeypatch.setattr(okx, "_load_credentials", lambda: (_KEY, _SECRET, _PASS))
    monkeypatch.setattr(okx, "_simulated_enabled", lambda: True)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    okx.OKXReader()._private_get("/api/v5/account/balance")
    assert captured["headers"]["x-simulated-trading"] == "1"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_application_level_error_code_raises(monkeypatch):
    """OKX returns HTTP 200 with a non-zero ``code`` — that must not look like success."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _response({"code": "50111", "msg": "Invalid OK-ACCESS-KEY", "data": []}),
    )
    with pytest.raises(RuntimeError, match="50111"):
        okx._request("GET", "/api/v5/account/balance")


def test_server_error_retries_then_raises(monkeypatch):
    import urllib.error

    calls = {"n": 0}

    def fake_urlopen(*_a, **_k):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 503, "boom", {}, BytesIO(b"upstream down"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(okx.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError, match="503"):
        okx._request("GET", "/api/v5/account/balance")
    assert calls["n"] == 3


def test_client_error_does_not_retry(monkeypatch):
    import urllib.error

    calls = {"n": 0}

    def fake_urlopen(*_a, **_k):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "unauth", {}, BytesIO(b"bad key"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="401"):
        okx._request("GET", "/api/v5/account/balance")
    assert calls["n"] == 1


def test_get_holdings_survives_one_failing_account(configured_reader, monkeypatch):
    """A funding-account outage must not wipe out trading-account holdings."""
    monkeypatch.setattr(
        configured_reader,
        "_trading_balances",
        lambda: {"BTC": {"qty": 0.5, "usd": 32000.0}},
    )
    monkeypatch.setattr(
        configured_reader,
        "_funding_balances",
        lambda: (_ for _ in ()).throw(RuntimeError("funding down")),
    )
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {"BTC": 64000.0})

    holdings = configured_reader.get_holdings()
    assert [h["symbol"] for h in holdings] == ["BTC"]
    assert holdings[0]["market_value"] == pytest.approx(32000.0)


def test_get_account_swallows_transport_failure(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_private_get",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network")),
    )
    result = configured_reader.get_account()
    assert result["source"] == "unavailable"
    assert "network" in result["error"]


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def test_spot_prices_pin_stablecoins_to_one(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    monkeypatch.setattr(reader, "_public_get", lambda *a, **k: [])
    prices = reader.get_spot_prices()
    assert prices["USDT"] == 1.0
    assert prices["USDC"] == 1.0


def test_spot_prices_parse_usdt_pairs(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    monkeypatch.setattr(
        reader,
        "_public_get",
        lambda *a, **k: [
            {"instId": "BTC-USDT", "last": "64000.5"},
            {"instId": "SOL-USDT", "last": "73.8"},
            {"instId": "BTC-ETH", "last": "34.2"},  # non-USD quote, ignored
        ],
    )
    prices = reader.get_spot_prices()
    assert prices["BTC"] == pytest.approx(64000.5)
    assert prices["SOL"] == pytest.approx(73.8)
    assert "BTC-ETH" not in prices


def test_spot_prices_prefer_usdt_over_usd(monkeypatch):
    """USDT books are deepest, so USDT must win the last-write ordering."""
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    monkeypatch.setattr(
        reader,
        "_public_get",
        lambda *a, **k: [
            {"instId": "BTC-USD", "last": "63000"},
            {"instId": "BTC-USDT", "last": "64000"},
        ],
    )
    assert reader.get_spot_prices()["BTC"] == pytest.approx(64000.0)


def test_spot_prices_degrade_to_stables_on_failure(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    monkeypatch.setattr(
        reader, "_public_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cf block"))
    )
    prices = reader.get_spot_prices()
    assert prices["USDT"] == 1.0
    assert "BTC" not in prices


def test_spot_prices_ignore_zero_and_bad_values(monkeypatch):
    monkeypatch.setattr(okx, "_load_credentials", lambda: ("", "", ""))
    reader = okx.OKXReader()
    monkeypatch.setattr(
        reader,
        "_public_get",
        lambda *a, **k: [
            {"instId": "AAA-USDT", "last": "0"},
            {"instId": "BBB-USDT", "last": ""},
            {"instId": "CCC-USDT", "last": "1.5"},
        ],
    )
    prices = reader.get_spot_prices()
    assert "AAA" not in prices
    assert "BBB" not in prices
    assert prices["CCC"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Holdings + valuation
# ---------------------------------------------------------------------------


def test_holdings_merge_trading_and_funding_accounts(configured_reader, monkeypatch):
    """The same currency in both sub-accounts is one position, quantity summed."""
    monkeypatch.setattr(
        configured_reader, "_trading_balances", lambda: {"SOL": {"qty": 10.0, "usd": 0.0}}
    )
    monkeypatch.setattr(
        configured_reader, "_funding_balances", lambda: {"SOL": {"qty": 5.0, "usd": 0.0}}
    )
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {"SOL": 70.0})

    holdings = configured_reader.get_holdings()
    assert len(holdings) == 1
    assert holdings[0]["qty"] == pytest.approx(15.0)
    assert holdings[0]["market_value"] == pytest.approx(1050.0)
    assert holdings[0]["sub_accounts"] == ["funding", "trading"]


def test_holdings_prefer_okx_reported_usd_over_ticker_math(configured_reader, monkeypatch):
    """``eqUsd`` is OKX's own valuation and is authoritative when present."""
    monkeypatch.setattr(
        configured_reader, "_trading_balances", lambda: {"BTC": {"qty": 1.0, "usd": 63999.0}}
    )
    monkeypatch.setattr(configured_reader, "_funding_balances", lambda: {})
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {"BTC": 64000.0})
    assert configured_reader.get_holdings()[0]["market_value"] == pytest.approx(63999.0)


def test_holdings_drop_dust_below_one_cent(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_trading_balances",
        lambda: {"DUST": {"qty": 0.001, "usd": 0.0}, "SOL": {"qty": 1.0, "usd": 0.0}},
    )
    monkeypatch.setattr(configured_reader, "_funding_balances", lambda: {})
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {"DUST": 0.0001, "SOL": 70.0})
    assert [h["symbol"] for h in configured_reader.get_holdings()] == ["SOL"]


def test_holdings_sorted_by_value_descending(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_trading_balances",
        lambda: {"A": {"qty": 1.0, "usd": 10.0}, "B": {"qty": 1.0, "usd": 500.0}},
    )
    monkeypatch.setattr(configured_reader, "_funding_balances", lambda: {})
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {})
    assert [h["symbol"] for h in configured_reader.get_holdings()] == ["B", "A"]


def test_holding_weights_sum_to_one_hundred(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_trading_balances",
        lambda: {"A": {"qty": 1.0, "usd": 250.0}, "B": {"qty": 1.0, "usd": 750.0}},
    )
    monkeypatch.setattr(configured_reader, "_funding_balances", lambda: {})
    monkeypatch.setattr(configured_reader, "get_spot_prices", lambda: {})
    weights = [h["weight"] for h in configured_reader.get_holdings()]
    assert sum(weights) == pytest.approx(100.0)


def test_trading_balances_parse_nested_details(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_private_get",
        lambda *a, **k: [
            {
                "totalEq": "2394.00",
                "details": [
                    {"ccy": "USDT", "eq": "100.0", "eqUsd": "100.0"},
                    {"ccy": "SOL", "eq": "10.0", "eqUsd": "700.0"},
                    {"ccy": "ZERO", "eq": "0"},
                ],
            }
        ],
    )
    balances = configured_reader._trading_balances()
    assert balances["SOL"]["qty"] == pytest.approx(10.0)
    assert balances["SOL"]["usd"] == pytest.approx(700.0)
    assert "ZERO" not in balances


def test_funding_balances_parse_flat_rows(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "_private_get",
        lambda *a, **k: [{"ccy": "BTC", "bal": "0.25"}, {"ccy": "EMPTY", "bal": "0"}],
    )
    balances = configured_reader._funding_balances()
    assert balances["BTC"]["qty"] == pytest.approx(0.25)
    assert "EMPTY" not in balances


def test_portfolio_value_classifies_stables_as_cash(configured_reader, monkeypatch):
    monkeypatch.setattr(
        configured_reader,
        "get_account",
        lambda: {"source": "okx", "total_equity_usd": 1100.0},
    )
    monkeypatch.setattr(
        configured_reader,
        "get_holdings",
        lambda: [
            {"symbol": "USDT", "qty": 100.0, "market_value": 100.0},
            {"symbol": "SOL", "qty": 10.0, "market_value": 700.0},
        ],
    )
    pv = configured_reader.get_portfolio_value()
    assert pv["cash"] == pytest.approx(100.0)
    assert pv["holdings_value"] == pytest.approx(700.0)
    assert pv["equity"] == pytest.approx(800.0)
    # OKX balance endpoints carry no cost basis — P&L must be None, not zero.
    assert pv["total_return"] is None


def test_snapshot_shape_matches_robinhood_contract(configured_reader, monkeypatch):
    """Both readers must be interchangeable for the aggregator."""
    from lib.portfolio.robinhood import RobinhoodReader

    monkeypatch.setattr(
        configured_reader, "get_account", lambda: {"source": "okx", "total_equity_usd": 0.0}
    )
    monkeypatch.setattr(configured_reader, "get_holdings", lambda: [])
    okx_keys = set(configured_reader.get_snapshot())

    with patch.object(RobinhoodReader, "__init__", lambda self: None):
        rh = RobinhoodReader()
        rh._available = False
        rh._api_key = ""
        rh._account_cache = None
        rh._cost_basis_cache = None
        rh_keys = set(rh.get_snapshot())

    assert rh_keys - okx_keys == {"sectors", "asset_classes"}
