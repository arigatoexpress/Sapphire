"""Unit tests for the GMX V2 price adapter (Arbitrum side).

Stubs out the AaveV3Arbitrum.get_asset_price method so the adapter is
exercised without any RPC. Covers happy-path market pricing, the
unpriced-market fail-loud path, decimals registration, and the
``can_price_market`` filter.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from lib.chains.arbitrum.contracts.gmx_price_adapter import (
    AAVE_PRICE_DECIMALS,
    GmxPriceAdapter,
    PriceUnavailable,
    TokenPrice,
    aave_price_to_gmx,
)
from lib.chains.arbitrum.contracts.gmx_v2 import GMX_PRICE_BASE, Market

# ---------- Fake AaveV3Arbitrum ---------------------------------------------


class FakeAave:
    """Stand-in for AaveV3Arbitrum.get_asset_price (the only method we touch)."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        # Lowercase the keys so callers can pass checksummed addresses.
        self._prices = {k.lower(): v for k, v in prices.items()}
        self.calls: list[str] = []

    async def get_asset_price(self, asset: str) -> Decimal:
        self.calls.append(asset)
        return self._prices.get(asset.lower(), Decimal(0))


# ---------- conversion helper ------------------------------------------------


def test_aave_price_to_gmx_eth_18_decimals() -> None:
    # ETH ($3500, 18 decimals) → 3.5e15
    assert aave_price_to_gmx(Decimal("3500"), 18) == 35 * 10**14


def test_aave_price_to_gmx_btc_8_decimals() -> None:
    # WBTC ($70_000, 8 decimals) → 7e26
    assert aave_price_to_gmx(Decimal("70000"), 8) == 7 * 10**26


# ---------- decimals_for / register_token -----------------------------------


def test_decimals_for_known_token_returns_18_for_weth() -> None:
    aave = FakeAave({})
    adapter = GmxPriceAdapter(aave)
    weth = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    assert adapter.decimals_for(weth) == 18


def test_decimals_for_unknown_token_raises_price_unavailable() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    with pytest.raises(PriceUnavailable, match="no decimals registered"):
        adapter.decimals_for("0x" + "9" * 40)


def test_register_token_extends_decimals_map() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    new_addr = "0x" + "9" * 40
    adapter.register_token(new_addr, 8)
    assert adapter.decimals_for(new_addr) == 8


def test_register_token_rejects_invalid_address() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    with pytest.raises(ValueError, match="invalid token"):
        adapter.register_token("nope", 18)


def test_register_token_rejects_out_of_range_decimals() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    with pytest.raises(ValueError, match="decimals must be"):
        adapter.register_token("0x" + "1" * 40, GMX_PRICE_BASE + 1)


def test_known_tokens_returns_sorted_list_with_majors() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    known = adapter.known_tokens()
    weth = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    assert weth in known
    assert wbtc in known
    assert known == sorted(known)


# ---------- fetch_token_price ------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_token_price_returns_both_scales() -> None:
    weth = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    aave = FakeAave({weth: Decimal("3500")})
    adapter = GmxPriceAdapter(aave)
    p = await adapter.fetch_token_price(weth)
    assert isinstance(p, TokenPrice)
    assert p.usd == Decimal("3500")
    assert p.aave_raw == 3500 * 10**AAVE_PRICE_DECIMALS
    assert p.gmx_min == 35 * 10**14
    assert p.gmx_min == p.gmx_max


@pytest.mark.asyncio
async def test_fetch_token_price_zero_price_raises_unavailable() -> None:
    weth = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    adapter = GmxPriceAdapter(FakeAave({}))  # not registered → 0
    with pytest.raises(PriceUnavailable, match="non-positive"):
        await adapter.fetch_token_price(weth)


@pytest.mark.asyncio
async def test_fetch_token_price_unknown_token_raises_unavailable() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    with pytest.raises(PriceUnavailable, match="no decimals"):
        await adapter.fetch_token_price("0x" + "f" * 40)


# ---------- market_prices / can_price_market --------------------------------


def _eth_btc_market() -> Market:
    return Market(
        market_token="0x" + "0" * 40,
        index_token="0x82af49447d8a07e3bd95bd0d56f35241523fbab1",  # WETH
        long_token="0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f",  # WBTC
        short_token="0xaf88d065e77c8cc2239327c5edb3a432268e5831",  # USDC
        name="ETH/WBTC-USDC",
    )


@pytest.mark.asyncio
async def test_market_prices_builds_three_tuple_with_aave_inputs() -> None:
    aave = FakeAave(
        {
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": Decimal("3500"),
            "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": Decimal("70000"),
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831": Decimal("1"),
        }
    )
    adapter = GmxPriceAdapter(aave)
    prices = await adapter.market_prices(_eth_btc_market())
    assert len(prices) == 3
    idx, long, short = prices
    # ETH index — 18 decimals → 3.5e15
    assert idx == (35 * 10**14, 35 * 10**14)
    # WBTC long — 8 decimals → 7e26
    assert long == (7 * 10**26, 7 * 10**26)
    # USDC short — 6 decimals → 1e24
    assert short == (10**24, 10**24)


@pytest.mark.asyncio
async def test_market_prices_propagates_unavailable_when_one_token_missing() -> None:
    # ETH + WBTC priced, USDC oracle returns 0 → unavailable.
    aave = FakeAave(
        {
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": Decimal("3500"),
            "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": Decimal("70000"),
        }
    )
    adapter = GmxPriceAdapter(aave)
    with pytest.raises(PriceUnavailable):
        await adapter.market_prices(_eth_btc_market())


@pytest.mark.asyncio
async def test_can_price_market_true_when_all_priced() -> None:
    aave = FakeAave(
        {
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": Decimal("3500"),
            "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": Decimal("70000"),
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831": Decimal("1"),
        }
    )
    adapter = GmxPriceAdapter(aave)
    assert await adapter.can_price_market(_eth_btc_market()) is True


@pytest.mark.asyncio
async def test_can_price_market_false_on_missing_oracle() -> None:
    aave = FakeAave({})
    adapter = GmxPriceAdapter(aave)
    assert await adapter.can_price_market(_eth_btc_market()) is False
