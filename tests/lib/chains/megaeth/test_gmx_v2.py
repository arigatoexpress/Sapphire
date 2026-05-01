"""Tests for the GMX V2 typed wrapper.

Uses recorded ``eth_call`` responses captured from MegaETH mainnet
(chain 4326) on 2026-04-30. Fixtures live at
``tests/lib/chains/megaeth/fixtures/gmx_v2/`` — one JSON per call,
storing the request payload + raw hex response so we can replay
without network.

There is also a single live integration test
(:func:`test_list_markets_live`) that hits real mainnet — gated
behind ``SAPPHIRE_MEGAETH_INTEGRATION=1``.
"""

from __future__ import annotations

import json
import os
import pathlib
from decimal import Decimal
from typing import Any

import pytest

from lib.chains.megaeth.contracts.base import TypedContract
from lib.chains.megaeth.contracts.gmx_v2 import (
    GMX_PRICE_BASE,
    SECONDS_PER_YEAR,
    GmxV2,
    GmxV2Addresses,
    Market,
    MarketInfo,
    decode_gmx_price,
    encode_gmx_price,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "gmx_v2"

# Live mainnet addresses (verified 2026-04-30 via eth_getCode).
READER = "0x0f038EB4a38B08cd3c937a3256b51aa01904a684"
DATA_STORE = "0xE43C7B694f6b652a9F4A0f275C008d18758Dce35"
ADDRS = GmxV2Addresses(reader=READER, data_store=DATA_STORE)

# Markets pulled from the getMarkets fixture.
ETH_MARKET = "0xbc7edfa7491cfbf317a65788e0e0cd89e91ec8a7"  # all-WETH legacy market
BTC_MARKET = "0x31edcc52be2fa55ba68f50409f9e6b7d9ebf3d59"  # WBTC/USDM market


# ---------------------------------------------------------------------------
# Stub client — duck-typed _MegaETHCallable.
# ---------------------------------------------------------------------------


class StubClient:
    """Replays recorded ``eth_call`` results keyed by request ``data`` payload.

    Tests prime it with ``responses[data_hex] = result_hex``. If the
    wrapper produces a request payload that isn't primed, the call
    raises so we catch ABI drift loudly.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses: dict[str, str] = {k.lower(): v for k, v in (responses or {}).items()}
        self.calls: list[tuple[str, list[Any]]] = []

    def add(self, data: str, result: str) -> None:
        self.responses[data.lower()] = result

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method != "eth_call":
            raise RuntimeError(f"unexpected method {method!r}")
        if not params or not isinstance(params[0], dict):
            raise RuntimeError(f"unexpected params {params!r}")
        data = str(params[0].get("data", "")).lower()
        if data not in self.responses:
            raise RuntimeError(
                f"no stub for data={data[:32]}... primed_keys={list(self.responses)[:3]}"
            )
        return self.responses[data]


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        pytest.skip(f"fixture missing: {path}")
    return json.loads(path.read_text())


def _wire_fixture(stub: StubClient, fx: dict[str, Any]) -> None:
    req = fx["request"]
    stub.add(req["data"], fx["result"])


# ---------------------------------------------------------------------------
# encode_gmx_price / decode_gmx_price
# ---------------------------------------------------------------------------


def test_encode_gmx_price_btc_8_decimals() -> None:
    # BTC at $70k, 8 decimals → 70_000 * 10^22 = 7e26
    encoded = encode_gmx_price(70_000, 8)
    assert encoded == 7 * 10**26


def test_encode_gmx_price_usdm_6_decimals() -> None:
    # USDM at $1, 6 decimals → 1 * 10^24
    assert encode_gmx_price(1, 6) == 10**24


def test_encode_gmx_price_eth_18_decimals() -> None:
    # ETH at $2305, 18 decimals → 2305 * 10^12
    assert encode_gmx_price(2305, 18) == 2305 * 10**12


def test_encode_gmx_price_decimal_input() -> None:
    encoded = encode_gmx_price(Decimal("0.99926"), 6)
    # 0.99926 * 10^24 == 99926 * 10^19
    assert encoded == int(Decimal("0.99926") * Decimal(10) ** 24)


def test_encode_gmx_price_decoder_round_trip() -> None:
    # encode then decode should match.
    encoded = encode_gmx_price(2305, 18)
    decoded = decode_gmx_price(encoded, 18)
    assert decoded == Decimal(2305)


def test_encode_gmx_price_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        encode_gmx_price(-1, 18)


def test_encode_gmx_price_rejects_bad_decimals() -> None:
    with pytest.raises(ValueError, match="decimals"):
        encode_gmx_price(1, 31)
    with pytest.raises(ValueError, match="decimals"):
        encode_gmx_price(1, -1)


# ---------------------------------------------------------------------------
# GmxV2Addresses
# ---------------------------------------------------------------------------


def test_addresses_dataclass_is_frozen() -> None:
    a = GmxV2Addresses(reader=READER, data_store=DATA_STORE)
    with pytest.raises((AttributeError, Exception)):
        a.reader = "0x" + "00" * 20  # type: ignore[misc]


def test_addresses_holds_only_read_side_addresses() -> None:
    """Wave B.3 must NOT include ExchangeRouter/OrderHandler — those are write-side."""
    fields = GmxV2Addresses.__dataclass_fields__
    assert set(fields) == {"reader", "data_store"}, (
        "GmxV2Addresses leaked write-side addresses; B.3 is read-only"
    )


# ---------------------------------------------------------------------------
# list_markets — uses recorded fixture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_markets_decodes_six_markets_from_fixture() -> None:
    fx = _load_fixture("getMarkets_0_50")
    stub = StubClient()
    _wire_fixture(stub, fx)
    gmx = GmxV2(stub, ADDRS)

    markets = await gmx.list_markets(start=0, end=50)
    # Captured 2026-04-30 — chain had 6 active markets.
    assert len(markets) == 6
    # Smoke check structure on first market (all-WETH).
    assert markets[0].market_token.lower() == ETH_MARKET
    for m in markets:
        assert m.market_token.startswith("0x") and len(m.market_token) == 42
        assert m.index_token.startswith("0x")
        assert m.long_token.startswith("0x")
        assert m.short_token.startswith("0x")
        assert isinstance(m.name, str) and m.name


@pytest.mark.asyncio
async def test_list_markets_sends_correct_arguments() -> None:
    fx = _load_fixture("getMarkets_0_50")
    stub = StubClient()
    _wire_fixture(stub, fx)
    gmx = GmxV2(stub, ADDRS)

    await gmx.list_markets(start=0, end=50)
    assert len(stub.calls) == 1
    method, params = stub.calls[0]
    assert method == "eth_call"
    assert params[0]["to"].lower() == READER.lower()


@pytest.mark.asyncio
async def test_list_markets_validates_range() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError):
        await gmx.list_markets(start=10, end=5)
    with pytest.raises(ValueError):
        await gmx.list_markets(start=-1, end=10)


# ---------------------------------------------------------------------------
# get_market
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_market_btc() -> None:
    fx = _load_fixture("getMarket_BTC")
    stub = StubClient()
    _wire_fixture(stub, fx)
    gmx = GmxV2(stub, ADDRS)

    market = await gmx.get_market(BTC_MARKET)
    assert isinstance(market, Market)
    assert market.market_token.lower() == BTC_MARKET
    # BTC market has WBTC index, USDM both legs.
    assert market.long_token.lower() == "0xfafddbb3fc7688494971a79cc65dca3ef82079e7"
    assert market.short_token.lower() == "0xfafddbb3fc7688494971a79cc65dca3ef82079e7"


@pytest.mark.asyncio
async def test_get_market_eth() -> None:
    fx = _load_fixture("getMarket_ETH")
    stub = StubClient()
    _wire_fixture(stub, fx)
    gmx = GmxV2(stub, ADDRS)

    market = await gmx.get_market(ETH_MARKET)
    assert market.market_token.lower() == ETH_MARKET
    # The legacy ETH market is the all-WETH one — index/long/short all WETH.
    weth = "0x4200000000000000000000000000000000000006"
    assert market.index_token == weth
    assert market.long_token == weth
    assert market.short_token == weth


@pytest.mark.asyncio
async def test_get_market_rejects_bad_address() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError, match="invalid market_key"):
        await gmx.get_market("not-an-address")


# ---------------------------------------------------------------------------
# market_info — combines getMarketInfo + 2x getOpenInterestWithPnl
# ---------------------------------------------------------------------------


def _btc_prices() -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    # Same prices used to capture the BTC fixture: BTC=70_000 (8d), USDM=1 (6d).
    bp = encode_gmx_price(70_000, 8)
    up = encode_gmx_price(1, 6)
    return ((bp, bp), (up, up), (up, up))


def _eth_prices() -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    ep = encode_gmx_price(2305, 18)
    return ((ep, ep), (ep, ep), (ep, ep))


@pytest.mark.asyncio
async def test_market_info_btc_decode() -> None:
    stub = StubClient()
    _wire_fixture(stub, _load_fixture("getMarketInfo_BTC"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_long"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_short"))
    gmx = GmxV2(stub, ADDRS)

    info = await gmx.market_info(BTC_MARKET, _btc_prices())
    assert isinstance(info, MarketInfo)
    assert info.market.market_token.lower() == BTC_MARKET
    # Captured live 2026-04-30: shorts pay longs, ~75% APR.
    assert info.longs_pay_shorts is False
    assert info.funding_factor_per_second > 0
    assert info.is_disabled is False
    # OI both sides are non-zero on the active BTC market.
    assert info.open_interest_long > 0
    assert info.open_interest_short > 0


@pytest.mark.asyncio
async def test_market_info_eth_decode() -> None:
    stub = StubClient()
    _wire_fixture(stub, _load_fixture("getMarketInfo_ETH"))
    _wire_fixture(stub, _load_fixture("getOI_ETH_long"))
    _wire_fixture(stub, _load_fixture("getOI_ETH_short"))
    gmx = GmxV2(stub, ADDRS)

    info = await gmx.market_info(ETH_MARKET, _eth_prices())
    # Legacy ETH market has zero OI on both sides.
    assert info.open_interest_long == 0
    assert info.open_interest_short == 0
    # Captured live: the legacy all-WETH market is flagged disabled
    # on chain (the LayerZero-bridged WBTC/USDM markets are the
    # active venues). isDisabled exposes that — we don't filter it
    # in list_markets so callers can decide policy.
    assert info.is_disabled is True


@pytest.mark.asyncio
async def test_market_info_rejects_bad_market_address() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError, match="invalid market"):
        await gmx.market_info("0xshort", _btc_prices())


@pytest.mark.asyncio
async def test_market_info_rejects_bad_prices_shape() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError, match="3-tuple"):
        await gmx.market_info(BTC_MARKET, ((1, 1), (1, 1)))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be"):
        await gmx.market_info(BTC_MARKET, ((1, 1), (1, 1), (1,)))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_market_info_rejects_negative_prices() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError, match="non-negative"):
        await gmx.market_info(BTC_MARKET, ((-1, 1), (1, 1), (1, 1)))


@pytest.mark.asyncio
async def test_market_info_rejects_min_gt_max() -> None:
    stub = StubClient()
    gmx = GmxV2(stub, ADDRS)
    with pytest.raises(ValueError, match="min > .max"):
        await gmx.market_info(BTC_MARKET, ((10, 1), (1, 1), (1, 1)))


# ---------------------------------------------------------------------------
# funding_rate_apr / oi_skew
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funding_rate_apr_btc_negative_when_shorts_pay_longs() -> None:
    """Captured live: BTC market funding flag was longsPayShorts=False, factor ~7.5e-9/s.

    APR fraction = factor/1e30 * SECONDS_PER_YEAR ≈ 0.75 (75% APR).
    Sign: negative because shorts are paying longs.
    """
    stub = StubClient()
    _wire_fixture(stub, _load_fixture("getMarketInfo_BTC"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_long"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_short"))
    gmx = GmxV2(stub, ADDRS)

    apr = await gmx.funding_rate_apr(BTC_MARKET, _btc_prices())
    assert isinstance(apr, Decimal)
    # Negative: shorts pay longs.
    assert apr < 0
    # Magnitude in the 50-100% APR range.
    assert Decimal("0.5") < abs(apr) < Decimal("1.0")


def test_funding_apr_static_helper_zero_factor() -> None:
    info = MarketInfo(
        market=Market(
            market_token="0x" + "00" * 20,
            index_token="0x" + "00" * 20,
            long_token="0x" + "00" * 20,
            short_token="0x" + "00" * 20,
            name="x",
        ),
        funding_factor_per_second=0,
        longs_pay_shorts=True,
        borrowing_factor_long=0,
        borrowing_factor_short=0,
        open_interest_long=0,
        open_interest_short=0,
        is_disabled=False,
    )
    assert GmxV2._funding_apr_from_info(info) == Decimal("0")


def test_funding_apr_static_helper_known_factor() -> None:
    """A factor of 1e22 per second → APR = 1e22/1e30 * SPY = SPY * 1e-8 ≈ 0.31536."""
    factor = 10**22
    info = MarketInfo(
        market=Market(
            market_token="0x" + "00" * 20,
            index_token="0x" + "00" * 20,
            long_token="0x" + "00" * 20,
            short_token="0x" + "00" * 20,
            name="x",
        ),
        funding_factor_per_second=factor,
        longs_pay_shorts=True,
        borrowing_factor_long=0,
        borrowing_factor_short=0,
        open_interest_long=0,
        open_interest_short=0,
        is_disabled=False,
    )
    apr = GmxV2._funding_apr_from_info(info)
    expected = Decimal(factor) / Decimal(10) ** GMX_PRICE_BASE * Decimal(SECONDS_PER_YEAR)
    assert apr == expected


def test_oi_skew_balanced_book_returns_half() -> None:
    info = MarketInfo(
        market=Market(market_token="0x" + "00" * 20, index_token="0x" + "00" * 20,
                      long_token="0x" + "00" * 20, short_token="0x" + "00" * 20, name="x"),
        funding_factor_per_second=0, longs_pay_shorts=True,
        borrowing_factor_long=0, borrowing_factor_short=0,
        open_interest_long=10**30, open_interest_short=10**30,
        is_disabled=False,
    )
    assert GmxV2._oi_skew_from_info(info) == Decimal("0.5")


def test_oi_skew_empty_book_returns_half() -> None:
    info = MarketInfo(
        market=Market(market_token="0x" + "00" * 20, index_token="0x" + "00" * 20,
                      long_token="0x" + "00" * 20, short_token="0x" + "00" * 20, name="x"),
        funding_factor_per_second=0, longs_pay_shorts=True,
        borrowing_factor_long=0, borrowing_factor_short=0,
        open_interest_long=0, open_interest_short=0,
        is_disabled=False,
    )
    assert GmxV2._oi_skew_from_info(info) == Decimal("0.5")


def test_oi_skew_all_long() -> None:
    info = MarketInfo(
        market=Market(market_token="0x" + "00" * 20, index_token="0x" + "00" * 20,
                      long_token="0x" + "00" * 20, short_token="0x" + "00" * 20, name="x"),
        funding_factor_per_second=0, longs_pay_shorts=True,
        borrowing_factor_long=0, borrowing_factor_short=0,
        open_interest_long=10**30, open_interest_short=0,
        is_disabled=False,
    )
    assert GmxV2._oi_skew_from_info(info) == Decimal("1")


def test_oi_skew_all_short() -> None:
    info = MarketInfo(
        market=Market(market_token="0x" + "00" * 20, index_token="0x" + "00" * 20,
                      long_token="0x" + "00" * 20, short_token="0x" + "00" * 20, name="x"),
        funding_factor_per_second=0, longs_pay_shorts=True,
        borrowing_factor_long=0, borrowing_factor_short=0,
        open_interest_long=0, open_interest_short=10**30,
        is_disabled=False,
    )
    assert GmxV2._oi_skew_from_info(info) == Decimal("0")


@pytest.mark.asyncio
async def test_oi_skew_btc_live_data() -> None:
    """Captured: BTC long_oi ~4.7e34, short_oi ~6.66e34 → skew ≈ 0.41."""
    stub = StubClient()
    _wire_fixture(stub, _load_fixture("getMarketInfo_BTC"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_long"))
    _wire_fixture(stub, _load_fixture("getOI_BTC_short"))
    gmx = GmxV2(stub, ADDRS)

    skew = await gmx.oi_skew(BTC_MARKET, _btc_prices())
    # Captured numbers: 47217… long, 66574… short → skew ≈ 0.4148.
    assert Decimal("0.40") < skew < Decimal("0.42")


# ---------------------------------------------------------------------------
# ABI / TypedContract sanity — make sure the pinned ABI loads & has functions
# ---------------------------------------------------------------------------


def test_pinned_reader_abi_exposes_expected_functions() -> None:
    gmx = GmxV2(StubClient(), ADDRS)
    for fn in ("getMarkets", "getMarket", "getMarketInfo", "getOpenInterestWithPnl"):
        assert gmx._reader.has_function(fn), f"{fn!r} missing from pinned ABI"


def test_typed_contract_address_set_to_reader() -> None:
    gmx = GmxV2(StubClient(), ADDRS)
    assert isinstance(gmx._reader, TypedContract)
    assert gmx._reader.address.lower() == READER.lower()


# ---------------------------------------------------------------------------
# Live integration test (skip-by-default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to hit live mainnet",
)
async def test_list_markets_live() -> None:
    """Hit real MegaETH RPC and confirm at least one market is listed.

    This is the smoke that proves the wrapper still talks to the real
    chain — gated so CI doesn't depend on RPC availability.
    """
    import urllib.request

    class HttpClient:
        def __init__(self, url: str) -> None:
            self.url = url

        async def _call(self, method: str, params: list[Any] | None = None) -> Any:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
            ).encode()
            req = urllib.request.Request(
                self.url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "sapphire-megaeth-test/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
            if "error" in payload:
                raise RuntimeError(f"RPC error: {payload['error']}")
            return payload.get("result")

    rpc_url = os.getenv("SAPPHIRE_MEGAETH_RPC", "https://mainnet.megaeth.com/rpc")
    client = HttpClient(rpc_url)
    gmx = GmxV2(client, ADDRS)

    markets = await gmx.list_markets()
    assert len(markets) >= 1, "live mainnet had 0 markets — sanity check failed"
    print(f"\n[live] GMX V2 listed {len(markets)} market(s):")
    for m in markets:
        print(f"  - {m.market_token} idx={m.index_token} L={m.long_token} S={m.short_token}")
