"""Unit + gated-integration tests for the Pyth Hermes off-chain client.

The gated integration test (env ``SAPPHIRE_HERMES_INTEGRATION=1``)
hits the real public Hermes endpoint and verifies sub-30-second
freshness on all 5 majors. CI runs the unit tests on every push;
the integration test runs only when explicitly opted in (Sapphire
test discipline — gated tests don't break CI on transient internet
hiccups).
"""

from __future__ import annotations

import json
import os
import time
from decimal import Decimal
from typing import Any

import httpx
import pytest

from lib.chains.cross_chain.pyth_hermes import (
    DEFAULT_HERMES_BASE_URL,
    HERMES_PRICE_IDS,
    PythHermesClient,
    PythHermesPrice,
    _normalize_price_id,
    _price_id_hex,
    _price_id_key,
)

# -- fixtures ----------------------------------------------------------------


def _btc_id() -> str:
    return HERMES_PRICE_IDS["BTC"]


def _hermes_response(
    entries: list[tuple[str, int, int, int, int]],
    *,
    vaa_hex: str = "deadbeefcafef00d",
) -> dict[str, Any]:
    """Build a Hermes-shaped response body.

    Each entry is ``(id_hex, raw_price, raw_conf, expo, publish_time)``.
    The id_hex may carry a leading ``0x`` or not — Hermes itself
    returns un-prefixed lowercase hex so we mirror that by default.
    """
    parsed = []
    for id_hex, raw_price, raw_conf, expo, publish_time in entries:
        clean = id_hex.removeprefix("0x").lower()
        parsed.append(
            {
                "id": clean,
                "price": {
                    "price": str(raw_price),
                    "conf": str(raw_conf),
                    "expo": expo,
                    "publish_time": publish_time,
                },
                "ema_price": {
                    "price": str(raw_price),
                    "conf": str(raw_conf),
                    "expo": expo,
                    "publish_time": publish_time,
                },
                "metadata": {
                    "slot": 1,
                    "proof_available_time": publish_time,
                    "prev_publish_time": publish_time,
                },
            }
        )
    return {
        "binary": {"encoding": "hex", "data": [vaa_hex]},
        "parsed": parsed,
    }


def _make_client(handler) -> PythHermesClient:
    """Construct a PythHermesClient with a mock httpx.MockTransport."""
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(
        base_url=DEFAULT_HERMES_BASE_URL,
        transport=transport,
        timeout=2.0,
    )
    return PythHermesClient(client=httpx_client)


# -- normalization tests -----------------------------------------------------


class TestPriceIdNormalization:
    """``_normalize_price_id`` and friends must accept hex / bytes /
    prefixed / un-prefixed and reject malformed inputs cleanly."""

    def test_accepts_0x_prefixed_hex(self):
        raw = _normalize_price_id(_btc_id())
        assert isinstance(raw, bytes)
        assert len(raw) == 32

    def test_accepts_unprefixed_hex(self):
        unprefixed = _btc_id()[2:]
        assert _normalize_price_id(unprefixed) == _normalize_price_id(_btc_id())

    def test_accepts_raw_bytes(self):
        raw = _normalize_price_id(_btc_id())
        assert _normalize_price_id(raw) == raw

    def test_rejects_wrong_length(self):
        with pytest.raises(ValueError, match="64 hex chars"):
            _normalize_price_id("0xdeadbeef")

    def test_rejects_non_hex(self):
        bad = "0x" + "z" * 64
        with pytest.raises(ValueError, match="invalid Pyth priceId"):
            _normalize_price_id(bad)

    def test_rejects_wrong_type(self):
        with pytest.raises(TypeError, match="priceId must be"):
            _normalize_price_id(12345)  # type: ignore[arg-type]

    def test_round_trip_hex(self):
        assert _price_id_hex(_btc_id()) == _btc_id().lower()

    def test_key_is_canonical_bytes(self):
        # Same key whether we pass hex or bytes, prefixed or not.
        a = _price_id_key(_btc_id())
        b = _price_id_key(_btc_id()[2:])
        c = _price_id_key(bytes.fromhex(_btc_id()[2:]))
        assert a == b == c


# -- single-fetch tests ------------------------------------------------------


class TestLatestPrice:
    """``latest_price`` returns a parsed PythHermesPrice for one ID."""

    def test_parses_basic_response(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["params"] = list(request.url.params.multi_items())
            body = _hermes_response([(_btc_id(), 7867149999999, 2311757388, -8, 1777818484)])
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            px = client.latest_price(_btc_id())

        assert px.expo == -8
        # 7867149999999 * 10**-8 = 78671.49999999
        assert px.price == Decimal("78671.49999999")
        assert px.conf == Decimal("23.11757388")
        assert px.publish_time == 1777818484
        assert px.vaa_bytes == bytes.fromhex("deadbeefcafef00d")
        assert px.usd == px.price  # alias

        # Verify request shape — must be GET to /v2/updates/price/latest
        # with ids[]=<0x...> and parsed=true.
        assert "/v2/updates/price/latest" in captured["url"]
        assert ("ids[]", _btc_id()) in captured["params"]
        assert ("parsed", "true") in captured["params"]

    def test_accepts_unprefixed_hex(self):
        def handler(request):
            body = _hermes_response([(_btc_id(), 100, 1, -2, 1000)])
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            px = client.latest_price(_btc_id()[2:])  # strip 0x

        assert px.price == Decimal("1.00")

    def test_lookup_error_when_priceid_absent_from_response(self):
        # Hermes returned an empty parsed list — caller's priceId
        # wasn't recognized. We surface this as LookupError so callers
        # can distinguish "Hermes itself failed" (HTTPError) from
        # "this feed isn't on Hermes" (LookupError).
        def handler(request):
            return httpx.Response(
                200, json={"binary": {"encoding": "hex", "data": []}, "parsed": []}
            )

        with _make_client(handler) as client:
            with pytest.raises(LookupError, match="no parsed entry"):
                client.latest_price(_btc_id())

    def test_http_error_propagates(self):
        def handler(request):
            return httpx.Response(503, text="upstream busy")

        with _make_client(handler) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.latest_price(_btc_id())

    def test_include_vaa_false_omits_vaa_parsing(self):
        # When include_vaa=False the binary.data is still in the wire
        # body but we don't decode it. vaa_bytes should be empty.
        def handler(request):
            body = _hermes_response(
                [(_btc_id(), 100, 1, -2, 1000)],
                vaa_hex="aabbcc",
            )
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            px = client.latest_price(_btc_id(), include_vaa=False)

        assert px.vaa_bytes == b""


# -- batch-fetch tests -------------------------------------------------------


class TestLatestPricesBatch:
    """``latest_prices`` and ``latest_prices_by_symbol`` batch calls."""

    def test_batch_returns_keyed_by_canonical_bytes(self):
        eth_id = HERMES_PRICE_IDS["ETH"]
        sol_id = HERMES_PRICE_IDS["SOL"]

        def handler(request):
            body = _hermes_response(
                [
                    (_btc_id(), 7867149999999, 1, -8, 1777818484),
                    (eth_id, 232400000000, 1, -8, 1777818484),
                    (sol_id, 8425000000, 1, -8, 1777818484),
                ]
            )
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            out = client.latest_prices([_btc_id(), eth_id, sol_id])

        # Keys are canonical 32-byte form, regardless of input shape.
        assert _price_id_key(_btc_id()) in out
        assert _price_id_key(eth_id) in out
        assert _price_id_key(sol_id) in out
        assert out[_price_id_key(_btc_id())].price == Decimal("78671.49999999")
        assert out[_price_id_key(eth_id)].price == Decimal("2324.00000000")

    def test_batch_dedupes_repeated_ids(self):
        captured = {}

        def handler(request):
            captured["params"] = list(request.url.params.multi_items())
            body = _hermes_response([(_btc_id(), 100, 1, -2, 1000)])
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            client.latest_prices([_btc_id(), _btc_id(), _btc_id()])

        # Only one ids[] param sent, despite the input having three.
        ids_params = [v for k, v in captured["params"] if k == "ids[]"]
        assert len(ids_params) == 1

    def test_batch_empty_list_returns_empty_dict(self):
        # A handler that should never be called.
        def handler(request):
            raise AssertionError("unexpected request for empty input")

        with _make_client(handler) as client:
            assert client.latest_prices([]) == {}

    def test_by_symbol_uses_canonical_map(self):
        captured = {}

        def handler(request):
            captured["params"] = list(request.url.params.multi_items())
            body = _hermes_response(
                [
                    (HERMES_PRICE_IDS["BTC"], 100, 1, -2, 1000),
                    (HERMES_PRICE_IDS["ETH"], 200, 1, -2, 1000),
                ]
            )
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            out = client.latest_prices_by_symbol(["btc", "ETH"])

        assert "BTC" in out and "ETH" in out
        assert out["BTC"].price == Decimal("1.00")
        assert out["ETH"].price == Decimal("2.00")
        # The two priceIds were sent.
        ids_sent = sorted(v for k, v in captured["params"] if k == "ids[]")
        expected = sorted([HERMES_PRICE_IDS["BTC"], HERMES_PRICE_IDS["ETH"]])
        assert ids_sent == expected

    def test_by_symbol_unknown_symbol_raises(self):
        with PythHermesClient() as client:
            with pytest.raises(KeyError, match="unknown Hermes symbol"):
                client.latest_prices_by_symbol(["NOT_A_REAL_COIN"])

    def test_batch_handles_extra_unrequested_entries(self):
        # Hermes returned an extra parsed entry the caller didn't
        # ask for. We should still accept it (key by id) — robust
        # against any over-return server behaviour.
        eth_id = HERMES_PRICE_IDS["ETH"]

        def handler(request):
            body = _hermes_response(
                [
                    (_btc_id(), 100, 1, -2, 1000),
                    (eth_id, 200, 1, -2, 1000),  # not asked
                ]
            )
            return httpx.Response(200, json=body)

        with _make_client(handler) as client:
            out = client.latest_prices([_btc_id()])

        # Both come back — caller can ignore unwanted entries.
        assert _price_id_key(_btc_id()) in out
        assert _price_id_key(eth_id) in out


class TestPythHermesPriceDataclass:
    """The PythHermesPrice dataclass surface."""

    def test_to_dict_serializes_decimals_and_bytes(self):
        p = PythHermesPrice(
            price=Decimal("78671.49"),
            conf=Decimal("23.11"),
            expo=-8,
            publish_time=1777818484,
            vaa_bytes=b"\xde\xad\xbe\xef",
        )
        d = p.to_dict()
        # Round-trip through json.dumps to confirm everything is
        # JSON-friendly — nothing leaks Decimal or bytes.
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped == {
            "price": "78671.49",
            "conf": "23.11",
            "expo": -8,
            "publish_time": 1777818484,
            "vaa_hex": "deadbeef",
        }

    def test_usd_alias_equals_price(self):
        p = PythHermesPrice(
            price=Decimal("100"),
            conf=Decimal("1"),
            expo=-2,
            publish_time=0,
            vaa_bytes=b"",
        )
        assert p.usd == p.price


# -- gated integration test --------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SAPPHIRE_HERMES_INTEGRATION") != "1",
    reason="set SAPPHIRE_HERMES_INTEGRATION=1 to hit the real Hermes API",
)
def test_integration_real_hermes_returns_fresh_majors():
    """Hits the public Hermes endpoint and asserts sub-30-second
    freshness on every Sapphire major (BTC/ETH/SOL/USDC/USDT).

    Pinned plausibility ranges (50k-200k for BTC etc.) are
    intentionally wide — the test is checking that Hermes is *up*
    and returning *plausible* fresh prices, not auditing the price
    itself. Tighter ranges would convert this from a smoke test into
    a market-aware test that flakes on every regime change.
    """
    with PythHermesClient(timeout_s=10.0) as client:
        prices = client.latest_prices_by_symbol(["BTC", "ETH", "SOL", "USDC", "USDT"])

    assert set(prices) == {"BTC", "ETH", "SOL", "USDC", "USDT"}

    now = time.time()
    btc = prices["BTC"]
    eth = prices["ETH"]
    sol = prices["SOL"]
    usdc = prices["USDC"]
    usdt = prices["USDT"]

    # All five must be fresh.
    for sym, p in prices.items():
        age = now - p.publish_time
        assert age < 30, f"{sym} publish_time {p.publish_time} is {age:.1f}s old"

    # Plausible price ranges. Wide on purpose.
    assert Decimal("50000") < btc.price < Decimal("200000"), btc.price
    assert Decimal("1000") < eth.price < Decimal("10000"), eth.price
    assert Decimal("20") < sol.price < Decimal("1000"), sol.price
    # Stablecoins should be very near 1.
    assert Decimal("0.95") < usdc.price < Decimal("1.05"), usdc.price
    assert Decimal("0.95") < usdt.price < Decimal("1.05"), usdt.price

    # Sanity-check the VAA was returned and is a non-trivial blob.
    # 100 bytes is the floor — actual VAAs are 1-3 KB.
    assert len(btc.vaa_bytes) > 100
