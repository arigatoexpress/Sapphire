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


# ---------- Chainlink fallback (added with the Chainlink fallback PR) -------


class _StaticChainlinkRegistry:
    """Stand-in for ChainlinkRegistry that maps known symbols to fixed prices."""

    def __init__(self, prices_by_symbol: dict[str, Decimal], stale: bool = False) -> None:
        self._prices = {k.upper(): v for k, v in prices_by_symbol.items()}
        self._stale = stale

    def oracle_for(self, symbol: str):  # type: ignore[no-untyped-def]
        return self if symbol.upper() in self._prices else None

    async def fetch_price(self, symbol: str, *, now: float | None = None):  # type: ignore[no-untyped-def]
        from lib.chains.arbitrum.contracts.chainlink_oracle import ChainlinkPrice

        usd = self._prices[symbol.upper()]
        return ChainlinkPrice(
            symbol=symbol.upper(),
            feed_address="0x" + "f" * 40,
            usd=usd,
            updated_at=1,
            stale=self._stale,
        )


@pytest.mark.asyncio
async def test_fetch_token_price_falls_back_to_chainlink_when_aave_returns_zero() -> None:
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})  # Aave returns 0 for WBTC
    chainlink = _StaticChainlinkRegistry({"BTC": Decimal("76774.81")})
    adapter = GmxPriceAdapter(aave, chainlink=chainlink)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "chainlink"
    assert p.usd == Decimal("76774.81")


@pytest.mark.asyncio
async def test_market_prices_with_meta_returns_token_prices_with_source() -> None:
    """The new meta-bearing variant exposes per-leg source/stale fields."""
    aave = FakeAave(
        {
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": Decimal("3500"),  # WETH
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831": Decimal("1"),  # USDC
        }
    )
    # WBTC is unpriced by Aave but Chainlink can serve it.
    chainlink = _StaticChainlinkRegistry({"BTC": Decimal("70000")})
    adapter = GmxPriceAdapter(aave, chainlink=chainlink)
    triples = await adapter.market_prices_with_meta(_eth_btc_market())
    sources = tuple(t.source for t in triples)
    assert sources == ("aave", "chainlink", "aave")


# ---------- Pyth tertiary fallback ------------------------------------------


class _StaticPythRegistry:
    """Stand-in for PythRegistry that maps known symbols to fixed prices.

    Mirrors the shape of :class:`_StaticChainlinkRegistry` so the test
    surface stays uniform.
    """

    def __init__(
        self,
        prices_by_symbol: dict[str, Decimal],
        *,
        stale: bool = False,
        raise_on_fetch: bool = False,
    ) -> None:
        self._prices = {k.upper(): v for k, v in prices_by_symbol.items()}
        self._stale = stale
        self._raise = raise_on_fetch

    def oracle_for(self, symbol: str):  # type: ignore[no-untyped-def]
        if symbol.upper() not in self._prices:
            return None
        # Real PythRegistry returns (aggregator, priceId); stand-in
        # just needs a truthy non-None return — the adapter checks
        # truthiness then calls .fetch_price().
        return (self, "0x" + "ab" * 32)

    async def fetch_price(self, symbol: str, *, now: float | None = None):  # type: ignore[no-untyped-def]
        from lib.chains.arbitrum.contracts.pyth_oracle import PythRegistryPrice

        if self._raise:
            raise RuntimeError("simulated Pyth RPC failure")
        usd = self._prices[symbol.upper()]
        return PythRegistryPrice(
            symbol=symbol.upper(),
            price_id="0x" + "ab" * 32,
            usd=usd,
            publish_time=1,
            stale=self._stale,
        )


@pytest.mark.asyncio
async def test_fetch_token_price_falls_back_to_pyth_when_aave_and_chainlink_unavailable() -> None:
    """Aave returns 0 + Chainlink unconfigured for the symbol → Pyth wins."""
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})  # Aave returns 0 for WBTC
    # Chainlink registry exists but maps no symbols (won't price BTC).
    chainlink = _StaticChainlinkRegistry({})
    pyth = _StaticPythRegistry({"BTC": Decimal("76800.50")})
    adapter = GmxPriceAdapter(aave, chainlink=chainlink, pyth=pyth)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "pyth"
    assert p.usd == Decimal("76800.50")


@pytest.mark.asyncio
async def test_fetch_token_price_falls_back_to_pyth_when_chainlink_raises() -> None:
    """Aave reverts + Chainlink raises (RPC error) → Pyth saves the day.

    This is the headline scenario for the secondary→tertiary chain:
    the chain-side oracle layer (Aave + Chainlink, both gas-paid /
    on-chain) has a correlated failure but Pyth's pull-based
    architecture (off-chain publishers, anyone can refresh on-chain)
    still serves a price.
    """
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"

    class RevertingAave:
        async def get_asset_price(self, asset: str) -> Decimal:
            raise RuntimeError("execution reverted")

    chainlink = _StaticChainlinkRegistry({"BTC": Decimal("0")})  # placeholder
    chainlink._raise = True  # type: ignore[attr-defined]
    # Patch the static stub to also raise — easiest via subclass.

    class RaisingChainlink(_StaticChainlinkRegistry):
        async def fetch_price(self, symbol, *, now=None):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated Chainlink RPC error")

    cl = RaisingChainlink({"BTC": Decimal("0")})
    pyth = _StaticPythRegistry({"BTC": Decimal("76800")})
    adapter = GmxPriceAdapter(RevertingAave(), chainlink=cl, pyth=pyth)  # type: ignore[arg-type]
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "pyth"
    assert p.usd == Decimal("76800")


@pytest.mark.asyncio
async def test_fetch_token_price_chainlink_stale_still_used_pyth_not_consulted() -> None:
    """A stale Chainlink price still wins — Pyth is only the LAST resort.

    Stale is a soft policy signal (Sentinel can downweight) — the
    adapter doesn't drop a stale Chainlink result in favour of a
    fresh Pyth one. This keeps the resolution order strict and lets
    callers reason about which oracle answered without secondary
    re-ranking surprises.
    """
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})  # Aave returns 0
    chainlink = _StaticChainlinkRegistry({"BTC": Decimal("70000")}, stale=True)
    pyth = _StaticPythRegistry({"BTC": Decimal("76800")})
    adapter = GmxPriceAdapter(aave, chainlink=chainlink, pyth=pyth)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "chainlink"
    assert p.stale is True
    assert p.usd == Decimal("70000")


@pytest.mark.asyncio
async def test_fetch_token_price_propagates_pyth_staleness_flag() -> None:
    """When Pyth serves the answer, its stale flag is surfaced on TokenPrice."""
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})
    pyth = _StaticPythRegistry({"BTC": Decimal("76000")}, stale=True)
    adapter = GmxPriceAdapter(aave, pyth=pyth)
    p = await adapter.fetch_token_price(wbtc)
    assert p.source == "pyth"
    assert p.stale is True


@pytest.mark.asyncio
async def test_fetch_token_price_all_three_unavailable_raises_with_full_summary() -> None:
    """Every oracle either rejects or returns non-positive → PriceUnavailable."""
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})  # Aave returns 0
    chainlink = _StaticChainlinkRegistry({})  # symbol unknown
    pyth = _StaticPythRegistry({})  # symbol unknown
    adapter = GmxPriceAdapter(aave, chainlink=chainlink, pyth=pyth)
    with pytest.raises(PriceUnavailable) as excinfo:
        await adapter.fetch_token_price(wbtc)
    msg = str(excinfo.value)
    # Per-oracle summary: aave=, chainlink=, pyth= all present so the
    # live debug path can see exactly which leg failed and why.
    assert "aave=" in msg
    assert "chainlink=" in msg
    assert "pyth=" in msg


@pytest.mark.asyncio
async def test_fetch_token_price_pyth_failure_falls_through_to_unavailable() -> None:
    """Pyth raising on fetch is handled — no exception escape, just unavailable."""
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    aave = FakeAave({})
    pyth = _StaticPythRegistry({"BTC": Decimal("76000")}, raise_on_fetch=True)
    adapter = GmxPriceAdapter(aave, pyth=pyth)
    with pytest.raises(PriceUnavailable) as excinfo:
        await adapter.fetch_token_price(wbtc)
    msg = str(excinfo.value)
    assert "pyth=" in msg
    assert "RuntimeError" in msg


@pytest.mark.asyncio
async def test_market_prices_with_meta_tags_pyth_for_uncovered_token() -> None:
    """A market where one leg only Pyth can price tags that leg ``source=\"pyth\"``."""
    aave = FakeAave(
        {
            "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": Decimal("3500"),  # WETH
            "0xaf88d065e77c8cc2239327c5edb3a432268e5831": Decimal("1"),  # USDC
        }
    )
    # No Chainlink, only Pyth covers BTC.
    pyth = _StaticPythRegistry({"BTC": Decimal("76800")})
    adapter = GmxPriceAdapter(aave, pyth=pyth)
    triples = await adapter.market_prices_with_meta(_eth_btc_market())
    sources = tuple(t.source for t in triples)
    # WETH (Aave), WBTC (Pyth), USDC (Aave)
    assert sources == ("aave", "pyth", "aave")


def test_register_pyth_symbol_extends_runtime_map() -> None:
    """register_pyth_symbol mirrors register_chainlink_symbol."""
    adapter = GmxPriceAdapter(FakeAave({}))
    new_addr = "0x" + "9" * 40
    adapter.register_pyth_symbol(new_addr, "ARB")
    assert adapter.pyth_symbol_for(new_addr) == "ARB"


def test_register_pyth_symbol_rejects_invalid_address() -> None:
    adapter = GmxPriceAdapter(FakeAave({}))
    with pytest.raises(ValueError, match="invalid token"):
        adapter.register_pyth_symbol("nope", "BTC")


def test_token_to_pyth_symbol_kwarg_overrides_default() -> None:
    """Constructor kwarg can override the default Chainlink-derived map."""
    addr = "0x" + "1" * 40
    adapter = GmxPriceAdapter(
        FakeAave({}),
        token_to_pyth_symbol={addr: "PEPE"},
    )
    assert adapter.pyth_symbol_for(addr) == "PEPE"


def test_pyth_symbol_defaults_to_chainlink_map_when_unset() -> None:
    """Without a token_to_pyth_symbol kwarg, Pyth reuses the Chainlink mapping."""
    wbtc = "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"
    adapter = GmxPriceAdapter(FakeAave({}))
    assert adapter.chainlink_symbol_for(wbtc) == "BTC"
    assert adapter.pyth_symbol_for(wbtc) == "BTC"
