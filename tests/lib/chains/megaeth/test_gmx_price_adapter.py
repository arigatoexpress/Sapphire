"""Tests for the Wave B.3-followup ``GmxPriceAdapter``.

Mocks both the AaveV3 oracle and the GmxV2 list. We don't go through
``encode_gmx_price`` mocking — the helper itself is already covered by
``test_gmx_v2.py``; these tests cover the wiring + the expected encoded
values for the production decimal shapes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.chains.megaeth.contracts.gmx_price_adapter import (
    GmxPriceAdapter,
    TokenDecimals,
)
from lib.chains.megaeth.contracts.gmx_v2 import (
    GMX_PRICE_BASE,
    Market,
    encode_gmx_price,
)


# ---------------------------------------------------------------------------
# Fakes — small enough that we don't pull in the full StubClient machinery.
# ---------------------------------------------------------------------------


class FakeAave:
    """Drop-in for AaveV3 — implements only ``get_asset_price``."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        # Lower-case keys so callers can pass mixed-case addresses.
        self.prices = {k.lower(): v for k, v in prices.items()}
        self.calls: list[str] = []

    async def get_asset_price(self, asset: str) -> Decimal:
        self.calls.append(asset.lower())
        if asset.lower() not in self.prices:
            return Decimal(0)
        return self.prices[asset.lower()]


class FakeGmx:
    """Drop-in for GmxV2 — implements only ``list_markets``."""

    def __init__(self, markets: list[Market]) -> None:
        self.markets = markets
        self.list_calls = 0

    async def list_markets(self, *, start: int = 0, end: int = 200) -> list[Market]:
        self.list_calls += 1
        _ = (start, end)  # ignored by the fake
        return list(self.markets)


# Fixed test addresses — all real-shaped (42-char 0x...) but distinct so
# the fake oracle can disambiguate.
WBTC = "0x" + "11" * 20
WETH = "0x" + "22" * 20
USDM = "0x" + "33" * 20
MARKET_TOKEN = "0x" + "44" * 20

BTC_MARKET = Market(
    market_token=MARKET_TOKEN,
    index_token=WBTC,
    long_token=WETH,
    short_token=USDM,
    name="WBTC/WETH-USDM",
)


# ---------------------------------------------------------------------------
# prices_for_market
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prices_for_market_returns_three_props_pairs() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]

    prices = await adapter.prices_for_market(BTC_MARKET)
    assert isinstance(prices, tuple) and len(prices) == 3
    for pair in prices:
        assert isinstance(pair, tuple) and len(pair) == 2
        # min == max (read-only callers don't want a synthetic spread)
        assert pair[0] == pair[1]


@pytest.mark.asyncio
async def test_prices_for_market_encodes_with_correct_decimals() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]

    # Default decimals: index=18 (treats WBTC as 18-dec because the test
    # uses defaults). Override to (8, 18, 6) for realistic WBTC.
    prices = await adapter.prices_for_market(
        BTC_MARKET,
        decimals=TokenDecimals(index=8, long=18, short=6),
    )
    expected_btc = encode_gmx_price(70_000, 8)
    expected_eth = encode_gmx_price(3_000, 18)
    expected_usdm = encode_gmx_price(1, 6)

    assert prices[0] == (expected_btc, expected_btc)
    assert prices[1] == (expected_eth, expected_eth)
    assert prices[2] == (expected_usdm, expected_usdm)


@pytest.mark.asyncio
async def test_prices_for_market_default_decimals_18_18_6() -> None:
    aave = FakeAave({WBTC: Decimal(2_305), WETH: Decimal(2_305), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]

    prices = await adapter.prices_for_market(BTC_MARKET)
    # Default index=18 -> 2305 * 10^12 = 2_305_000_000_000_000
    assert prices[0][0] == 2_305 * 10**12
    # Default short=6 -> 1 * 10^24
    assert prices[2][0] == 10**24


@pytest.mark.asyncio
async def test_prices_for_market_raises_when_index_missing() -> None:
    # WBTC missing → returns 0 → raises KeyError
    aave = FakeAave({WETH: Decimal(3_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="index token"):
        await adapter.prices_for_market(BTC_MARKET)


@pytest.mark.asyncio
async def test_prices_for_market_raises_when_long_missing() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="long token"):
        await adapter.prices_for_market(BTC_MARKET)


@pytest.mark.asyncio
async def test_prices_for_market_raises_when_short_missing() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="short token"):
        await adapter.prices_for_market(BTC_MARKET)


@pytest.mark.asyncio
async def test_prices_for_market_calls_oracle_for_each_token() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]
    await adapter.prices_for_market(BTC_MARKET)
    # Three reads — one per token.
    assert len(aave.calls) == 3
    assert aave.calls[0] == WBTC.lower()
    assert aave.calls[1] == WETH.lower()
    assert aave.calls[2] == USDM.lower()


# ---------------------------------------------------------------------------
# prices_for_market_address
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prices_for_market_address_resolves_market_then_delegates() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000), USDM: Decimal(1)})
    gmx = FakeGmx([BTC_MARKET])
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=gmx)  # type: ignore[arg-type]

    prices = await adapter.prices_for_market_address(MARKET_TOKEN)
    assert len(prices) == 3
    assert gmx.list_calls == 1
    assert len(aave.calls) == 3


@pytest.mark.asyncio
async def test_prices_for_market_address_is_case_insensitive() -> None:
    aave = FakeAave({WBTC: Decimal(70_000), WETH: Decimal(3_000), USDM: Decimal(1)})
    gmx = FakeGmx([BTC_MARKET])
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=gmx)  # type: ignore[arg-type]

    upper = MARKET_TOKEN.upper()
    prices = await adapter.prices_for_market_address(upper)
    assert len(prices) == 3


@pytest.mark.asyncio
async def test_prices_for_market_address_raises_when_market_unknown() -> None:
    aave = FakeAave({})
    gmx = FakeGmx([BTC_MARKET])
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=gmx)  # type: ignore[arg-type]

    bogus = "0x" + "ab" * 20
    with pytest.raises(KeyError, match="not found"):
        await adapter.prices_for_market_address(bogus)


# ---------------------------------------------------------------------------
# Encoding sanity — roundtrip via the helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prices_for_market_roundtrip_decoding() -> None:
    """Sanity: decode_gmx_price(encoded) === input USD."""
    from lib.chains.megaeth.contracts.gmx_v2 import decode_gmx_price

    aave = FakeAave({WBTC: Decimal("70123.45"), WETH: Decimal(3_000), USDM: Decimal(1)})
    adapter = GmxPriceAdapter(aave_v3=aave, gmx=FakeGmx([BTC_MARKET]))  # type: ignore[arg-type]

    prices = await adapter.prices_for_market(
        BTC_MARKET,
        decimals=TokenDecimals(index=8, long=18, short=6),
    )
    btc_min, _ = prices[0]
    decoded = decode_gmx_price(btc_min, 8)
    assert decoded == Decimal("70123.45")
    assert GMX_PRICE_BASE == 30  # constant invariant
