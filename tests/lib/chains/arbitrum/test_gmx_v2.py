"""Unit tests for GmxV2Arbitrum read wrapper.

Pure-decode coverage — every test injects a stub client; no network.
Exercises the chain-agnostic primitives (encode/decode price, dataclass
shapes, _funding_apr_from_info, _oi_skew_from_info) and the wrapper
methods (list_markets, get_market, market_info) against synthetic
fixtures shaped like the verified Reader return tuples.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from lib.chains.arbitrum.contracts.gmx_v2 import (
    GMX_PRICE_BASE,
    SECONDS_PER_YEAR,
    GmxV2Addresses,
    GmxV2Arbitrum,
    Market,
    MarketInfo,
    _market_from_tuple,
    _validate_address,
    _validate_prices,
    decode_gmx_price,
    encode_gmx_price,
)
from lib.chains.arbitrum.registry import ProtocolEntry, ProtocolRegistry

# ---------- helper stub client ------------------------------------------------


class StubClient:
    """Minimal client stub — returns canned responses keyed by call signature."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.canned: dict[str, Any] = {}

    def respond(self, method_key: str, value: Any) -> None:
        self.canned[method_key] = value

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        # eth_call routed via TypedContract; here we never see eth_call.
        # The wrapper uses TypedContract.call() — but since we pass a raw
        # client to TypedContract, that goes through eth_call path. For
        # unit tests we monkeypatch TypedContract.call instead. Kept here
        # so the structural contract is satisfied.
        raise NotImplementedError(method)


# ---------- price encode/decode -----------------------------------------------


def test_encode_gmx_price_btc_70000_8_decimals() -> None:
    """BTC ($70_000, 8 decimals) → 7e26 (verified against GMX docs)."""
    assert encode_gmx_price(70_000, 8) == 7 * 10**26


def test_encode_gmx_price_usdc_one_dollar_6_decimals() -> None:
    """USDC ($1, 6 decimals) → 1e24."""
    assert encode_gmx_price(1, 6) == 10**24


def test_encode_gmx_price_eth_3500_18_decimals() -> None:
    """ETH ($3500, 18 decimals) → 3.5e15."""
    assert encode_gmx_price(3500, 18) == 35 * 10**14


def test_encode_decode_round_trips_decimal() -> None:
    raw = encode_gmx_price(Decimal("12345.6789"), 18)
    back = decode_gmx_price(raw, 18)
    assert back == Decimal("12345.6789")


def test_encode_gmx_price_rejects_negative_price() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        encode_gmx_price(-1, 18)


def test_encode_gmx_price_rejects_out_of_range_decimals() -> None:
    with pytest.raises(ValueError, match="decimals must be"):
        encode_gmx_price(100, 99)


def test_decode_gmx_price_rejects_out_of_range_decimals() -> None:
    with pytest.raises(ValueError, match="decimals must be"):
        decode_gmx_price(123, -1)


# ---------- validators --------------------------------------------------------


def test_validate_address_accepts_lowercase_42_char() -> None:
    _validate_address("0x" + "a" * 40, "x")  # no raise


def test_validate_address_rejects_short() -> None:
    with pytest.raises(ValueError, match="invalid x"):
        _validate_address("0xabc", "x")


def test_validate_address_rejects_missing_prefix() -> None:
    with pytest.raises(ValueError, match="invalid"):
        _validate_address("a" * 42, "x")


def test_validate_prices_accepts_canonical_shape() -> None:
    _validate_prices(((1, 2), (3, 4), (5, 6)))


def test_validate_prices_rejects_short() -> None:
    with pytest.raises(ValueError, match="3-tuple"):
        _validate_prices(((1, 2), (3, 4)))


def test_validate_prices_rejects_min_greater_than_max() -> None:
    with pytest.raises(ValueError, match="min > .max"):
        _validate_prices(((10, 5), (1, 2), (3, 4)))


def test_validate_prices_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _validate_prices(((-1, 2), (3, 4), (5, 6)))


# ---------- _market_from_tuple ------------------------------------------------


def test_market_from_tuple_renders_synthetic() -> None:
    row = (
        "0x" + "a" * 40,  # market_token
        "0x" + "b" * 40,  # index_token
        "0x" + "c" * 40,  # long_token
        "0x" + "d" * 40,  # short_token
    )
    m = _market_from_tuple(row)
    assert m.market_token == row[0]
    assert m.index_token == row[1]
    assert m.long_token == row[2]
    assert m.short_token == row[3]
    # Name uses the 6-char prefix of the index/long/short addresses.
    assert m.name.startswith("0xbbbb")


def test_market_from_tuple_rejects_short_row() -> None:
    with pytest.raises(ValueError, match="expected 4 fields"):
        _market_from_tuple(("0x" + "a" * 40,))


# ---------- funding APR + skew helpers (pure) --------------------------------


def _info(*, ff: int, lps: bool, oi_long: int, oi_short: int, disabled: bool = False) -> MarketInfo:
    return MarketInfo(
        market=Market(
            market_token="0x" + "a" * 40,
            index_token="0x" + "b" * 40,
            long_token="0x" + "c" * 40,
            short_token="0x" + "d" * 40,
            name="m",
        ),
        funding_factor_per_second=ff,
        longs_pay_shorts=lps,
        borrowing_factor_long=0,
        borrowing_factor_short=0,
        open_interest_long=oi_long,
        open_interest_short=oi_short,
        is_disabled=disabled,
    )


def test_funding_apr_zero_factor_returns_zero() -> None:
    apr = GmxV2Arbitrum._funding_apr_from_info(_info(ff=0, lps=True, oi_long=0, oi_short=0))
    assert apr == Decimal(0)


def test_funding_apr_positive_when_longs_pay_shorts() -> None:
    # 1% per year = 1e30 * 0.01 / SECONDS_PER_YEAR per second
    factor = int(Decimal(10) ** 30 * Decimal("0.01") / Decimal(SECONDS_PER_YEAR))
    apr = GmxV2Arbitrum._funding_apr_from_info(_info(ff=factor, lps=True, oi_long=0, oi_short=0))
    assert Decimal("0.0099") < apr < Decimal("0.0101")


def test_funding_apr_negative_when_shorts_pay_longs() -> None:
    factor = int(Decimal(10) ** 30 * Decimal("0.05") / Decimal(SECONDS_PER_YEAR))
    apr = GmxV2Arbitrum._funding_apr_from_info(_info(ff=factor, lps=False, oi_long=0, oi_short=0))
    assert Decimal("-0.0501") < apr < Decimal("-0.0499")


def test_oi_skew_balanced_returns_half() -> None:
    skew = GmxV2Arbitrum._oi_skew_from_info(_info(ff=0, lps=True, oi_long=100, oi_short=100))
    assert skew == Decimal("0.5")


def test_oi_skew_empty_returns_half() -> None:
    skew = GmxV2Arbitrum._oi_skew_from_info(_info(ff=0, lps=True, oi_long=0, oi_short=0))
    assert skew == Decimal("0.5")


def test_oi_skew_pure_long_returns_one() -> None:
    skew = GmxV2Arbitrum._oi_skew_from_info(_info(ff=0, lps=True, oi_long=1000, oi_short=0))
    assert skew == Decimal("1")


def test_oi_skew_three_quarters_long() -> None:
    skew = GmxV2Arbitrum._oi_skew_from_info(_info(ff=0, lps=True, oi_long=300, oi_short=100))
    assert skew == Decimal("0.75")


# ---------- list_markets / get_market via TypedContract monkey patch ---------


class _Queue:
    """Wrap a list when you want sequential responses. Plain lists are returned as-is."""

    def __init__(self, items: list[Any]) -> None:
        self.items = list(items)


class FakeTypedContract:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def call(self, method: str, *args: Any) -> Any:
        self.calls.append((method, args))
        if method not in self._responses:
            raise KeyError(f"no canned response for {method!r}")
        v = self._responses[method]
        if callable(v):
            return v(*args)
        if isinstance(v, _Queue):
            return v.items.pop(0)
        return v


def _build_wrapper(monkeypatch: pytest.MonkeyPatch, responses: dict[str, Any]) -> GmxV2Arbitrum:
    addrs = GmxV2Addresses(
        reader="0x" + "1" * 40,
        data_store="0x" + "2" * 40,
        event_emitter="0x" + "3" * 40,
    )
    # Patch __init__ to skip ABI load + replace _reader with our fake.
    fake = FakeTypedContract(responses)

    def _init_no_abi(self: GmxV2Arbitrum, client: Any, addresses: GmxV2Addresses) -> None:
        self._client = client
        self.addresses = addresses
        self._reader = fake  # type: ignore[assignment]

    monkeypatch.setattr(GmxV2Arbitrum, "__init__", _init_no_abi)
    return GmxV2Arbitrum(StubClient(), addrs)


@pytest.mark.asyncio
async def test_list_markets_decodes_two_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        ("0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40),
        ("0x" + "e" * 40, "0x" + "f" * 40, "0x" + "0" * 40, "0x" + "1" * 40),
    ]
    gmx = _build_wrapper(monkeypatch, {"getMarkets": rows})
    markets = await gmx.list_markets()
    assert len(markets) == 2
    assert markets[0].index_token == "0x" + "b" * 40
    assert markets[1].long_token == "0x" + "0" * 40


@pytest.mark.asyncio
async def test_list_markets_skips_malformed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        ("0x" + "a" * 40,),  # too short — skipped
        ("0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40, "0x" + "e" * 40),
    ]
    gmx = _build_wrapper(monkeypatch, {"getMarkets": rows})
    out = await gmx.list_markets()
    assert len(out) == 1


@pytest.mark.asyncio
async def test_list_markets_rejects_invalid_range(monkeypatch: pytest.MonkeyPatch) -> None:
    gmx = _build_wrapper(monkeypatch, {})
    with pytest.raises(ValueError, match="invalid range"):
        await gmx.list_markets(start=10, end=5)


@pytest.mark.asyncio
async def test_get_market_decodes_single_row(monkeypatch: pytest.MonkeyPatch) -> None:
    row = ("0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40)
    gmx = _build_wrapper(monkeypatch, {"getMarket": row})
    m = await gmx.get_market("0x" + "a" * 40)
    assert m.market_token == row[0]


@pytest.mark.asyncio
async def test_get_market_rejects_invalid_address(monkeypatch: pytest.MonkeyPatch) -> None:
    gmx = _build_wrapper(monkeypatch, {})
    with pytest.raises(ValueError, match="invalid market_key"):
        await gmx.get_market("nope")


# ---------- market_info — exercises the multi-call decode -------------------


@pytest.mark.asyncio
async def test_market_info_decodes_full_struct(monkeypatch: pytest.MonkeyPatch) -> None:
    market_row = ("0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40)
    base_funding = ((((0, 0), (0, 0)), ((0, 0), (0, 0))),)  # placeholder
    next_funding = (True, 12345, 0, ((0, 0), (0, 0)), ((0, 0), (0, 0)))
    virtual_inv = (0, 0, 0)
    market_info_tuple = (
        market_row,
        100,  # borrowing_factor_long
        200,  # borrowing_factor_short
        base_funding,
        next_funding,
        virtual_inv,
        False,  # is_disabled
    )
    responses = {
        "getMarketInfo": market_info_tuple,
        "getOpenInterestWithPnl": _Queue([555_000, 444_000]),
    }
    gmx = _build_wrapper(monkeypatch, responses)

    info = await gmx.market_info(
        "0x" + "a" * 40,
        ((10, 20), (30, 40), (50, 60)),
    )
    assert info.borrowing_factor_long == 100
    assert info.borrowing_factor_short == 200
    assert info.funding_factor_per_second == 12345
    assert info.longs_pay_shorts is True
    assert info.open_interest_long == 555_000
    assert info.open_interest_short == 444_000
    assert info.is_disabled is False


@pytest.mark.asyncio
async def test_market_info_propagates_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    market_row = ("0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40)
    next_funding = (False, 999, 0, ((0, 0), (0, 0)), ((0, 0), (0, 0)))
    info_tuple = (
        market_row,
        0,
        0,
        ((((0, 0), (0, 0)), ((0, 0), (0, 0))),),
        next_funding,
        (0, 0, 0),
        True,
    )
    gmx = _build_wrapper(
        monkeypatch,
        {"getMarketInfo": info_tuple, "getOpenInterestWithPnl": _Queue([0, 0])},
    )
    info = await gmx.market_info(
        "0x" + "a" * 40,
        ((1, 1), (1, 1), (1, 1)),
    )
    assert info.is_disabled is True
    assert info.longs_pay_shorts is False


# ---------- registry / address bundle ----------------------------------------


def test_addresses_from_registry_entry() -> None:
    entry = ProtocolEntry(
        key="gmx_v2",
        name="GMX V2 (Arbitrum One)",
        category="perps",
        priority=1,
        status="active",
        docs_url="",
        addresses={
            "reader": "0x" + "1" * 40,
            "data_store": "0x" + "2" * 40,
            "event_emitter": "0x" + "3" * 40,
        },
    )
    a = GmxV2Addresses.from_registry_entry(entry)
    assert a.reader == "0x" + "1" * 40
    assert a.data_store == "0x" + "2" * 40
    assert a.event_emitter == "0x" + "3" * 40


def test_registry_yaml_pins_gmx_v2_with_three_addresses() -> None:
    reg = ProtocolRegistry.from_yaml()
    assert "gmx_v2" in reg
    e = reg.get("gmx_v2")
    assert e.category == "perps"
    assert e.address("reader").lower().startswith("0xf60becbba")
    assert e.address("data_store").lower().startswith("0xfd70de6b")
    assert e.address("event_emitter").lower().startswith("0xc8ee91a")


def test_constants_exported() -> None:
    assert GMX_PRICE_BASE == 30
    assert SECONDS_PER_YEAR == 31_536_000
