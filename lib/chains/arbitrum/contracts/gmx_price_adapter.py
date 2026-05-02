"""GMX V2 price adapter — bridge Aave V3 oracle prices into GMX ``Price.Props``.

GMX V2 ``Reader.getMarketInfo`` requires a ``MarketPrices`` tuple of
(index, long, short) prices already encoded into GMX's 1e30-scaled
``Price.Props`` shape. The on-chain reader does NOT fetch prices itself —
GMX expects callers to source prices off-chain (Chainlink, GMX's own
keeper signed prices, an oracle aggregator, etc.) and pass them in.

This adapter composes :class:`~lib.chains.arbitrum.contracts.aave_v3.AaveV3Arbitrum`
(specifically its oracle, which exposes Chainlink-aggregated USD prices
scaled to 1e8) with :func:`~lib.chains.arbitrum.contracts.gmx_v2.encode_gmx_price`
to produce the right MarketPrices tuple. It's the cross-chain
composition payoff: the same Aave oracle that backs lending readouts
also feeds GMX perps state.

Why this is a self-contained module (not a shim)
================================================

The MegaETH chain package is expected to ship a parallel
``gmx_price_adapter`` module on its own branch. We deliberately do NOT
import from it here so this branch lands independently. The module
shape mirrors what megaeth's will look like, so multi-chain code can
duck-type either.

Coverage on Arbitrum vs MegaETH
===============================

Arbitrum's Aave V3 has ~20 reserves vs MegaETH's 8, so MORE GMX markets
on Arbitrum will have Aave-priced index tokens out of the box (ETH,
WBTC, ARB, USDC, USDT, LINK, etc.). Markets whose index_token is NOT in
Aave (long-tail synthetics, alt-L2 tokens) need a fallback price source —
this adapter raises :class:`PriceUnavailable` rather than silently
substituting, so callers know to drop or quarantine those markets.

Footgun: Aave oracle is **base-currency-scaled** (1e8 on Arbitrum),
GMX is **decimal-scaled** (10^(30-decimals)). Get the conversion wrong
and the resulting price is off by ~22 orders of magnitude. The
``aave_price_to_gmx`` helper handles this; never hand-roll it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .aave_v3 import AaveV3Arbitrum
from .gmx_v2 import GMX_PRICE_BASE, Market, encode_gmx_price

#: Aave V3 oracle base-currency exponent on Arbitrum One.
#: ``getAssetPrice`` returns USD * 1e8 (verified against
#: ``AaveOracle.BASE_CURRENCY_UNIT()`` = ``100000000``).
AAVE_PRICE_DECIMALS = 8


class PriceUnavailable(LookupError):
    """Raised when an Aave oracle has no price for the requested token.

    Distinct from a generic ``LookupError`` so callers can quarantine
    affected markets without swallowing real bugs.
    """


@dataclass(frozen=True)
class TokenPrice:
    """A single token's USD price in both Aave and GMX scales.

    ``aave_raw`` is what Aave's oracle returned (USD * 10**8).
    ``gmx_min`` / ``gmx_max`` are the encoded ``Price.Props`` fields —
    we use the same value for both sides since Aave doesn't expose a
    bid/ask spread; if a future caller wants min<max, they can override
    by widening here.
    """

    address: str
    decimals: int
    usd: Decimal
    aave_raw: int
    gmx_min: int
    gmx_max: int

    def as_gmx_props(self) -> tuple[int, int]:
        """Return ``(min, max)`` as GMX expects in MarketPrices."""
        return (self.gmx_min, self.gmx_max)


def aave_price_to_gmx(usd: Decimal, decimals: int) -> int:
    """Convert a USD price (Decimal) into GMX's 1e30-scaled ``Price.Props`` field.

    Thin wrapper that delegates to :func:`encode_gmx_price`. Kept as a
    named function so test code reads more naturally
    (``aave_price_to_gmx(price, 18)`` vs ``encode_gmx_price(price, 18)``).
    """
    return encode_gmx_price(usd, decimals)


class GmxPriceAdapter:
    """Compose Aave V3 oracle reads into GMX ``MarketPrices`` tuples.

    Construction is cheap — pass in an existing :class:`AaveV3Arbitrum`
    instance plus a token-decimals map. The adapter doesn't open any new
    transports of its own.

    Token decimals must be supplied explicitly (rather than fetched
    on-the-fly from each ERC-20) because:

    * Reader calls happen in tight loops where we don't want N extra
      ``decimals()`` round-trips.
    * For unknown tokens we want to fail loudly, not silently default
      to 18 (a wrong assumption for USDC=6, WBTC=8, etc.).

    Default :attr:`COMMON_DECIMALS` covers the majors that overlap with
    Arbitrum's Aave reserves (ETH, WBTC, ARB, USDC, USDT, LINK, DAI,
    GMX, FRAX, wstETH, rETH). Callers with more exotic markets
    extend the dict.
    """

    #: Default decimals for tokens that overlap Arbitrum Aave reserves
    #: + GMX perp index tokens. Keys are lowercased addresses.
    #:
    #: References (verified 2026-04-30 against Arbiscan):
    #:   ETH/WETH:    0x82af49447d8a07e3bd95bd0d56f35241523fbab1   (18)
    #:   WBTC:        0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f   (8)
    #:   ARB:         0x912ce59144191c1204e64559fe8253a0e49e6548   (18)
    #:   USDC.e:      0xff970a61a04b1ca14834a43f5de4533ebddb5cc8   (6)
    #:   USDC:        0xaf88d065e77c8cc2239327c5edb3a432268e5831   (6)
    #:   USDT:        0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9   (6)
    #:   LINK:        0xf97f4df75117a78c1a5a0dbb814af92458539fb4   (18)
    #:   DAI:         0xda10009cbd5d07dd0cecc66161fc93d7c9000da1   (18)
    #:   GMX:         0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a   (18)
    #:   FRAX:        0x17fc002b466eec40dae837fc4be5c67993ddbd6f   (18)
    #:   wstETH:      0x5979d7b546e38e414f7e9822514be443a4800529   (18)
    #:   rETH:        0xec70dcb4a1efa46b8f2d97c310c9c4790ba5ffa8   (18)
    COMMON_DECIMALS: dict[str, int] = {
        "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": 18,
        "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": 8,
        "0x912ce59144191c1204e64559fe8253a0e49e6548": 18,
        "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": 6,
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831": 6,
        "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": 6,
        "0xf97f4df75117a78c1a5a0dbb814af92458539fb4": 18,
        "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": 18,
        "0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a": 18,
        "0x17fc002b466eec40dae837fc4be5c67993ddbd6f": 18,
        "0x5979d7b546e38e414f7e9822514be443a4800529": 18,
        "0xec70dcb4a1efa46b8f2d97c310c9c4790ba5ffa8": 18,
    }

    def __init__(
        self,
        aave: AaveV3Arbitrum,
        token_decimals: dict[str, int] | None = None,
    ) -> None:
        self._aave = aave
        # Defensive copy + lowercase keys — ERC-20 addresses are
        # case-insensitive but the registry sometimes has checksummed.
        merged = dict(self.COMMON_DECIMALS)
        if token_decimals:
            for k, v in token_decimals.items():
                merged[k.lower()] = int(v)
        self._decimals = merged

    def register_token(self, address: str, decimals: int) -> None:
        """Allow callers to extend the decimals map at runtime.

        Useful when the registry adds a new market and we don't want to
        bump the hard-coded :attr:`COMMON_DECIMALS` until a release.
        """
        if not isinstance(address, str) or not address.startswith("0x"):
            raise ValueError(f"invalid token address: {address!r}")
        if decimals < 0 or decimals > GMX_PRICE_BASE:
            raise ValueError(f"decimals must be in [0, {GMX_PRICE_BASE}], got {decimals}")
        self._decimals[address.lower()] = int(decimals)

    def known_tokens(self) -> list[str]:
        """Return the lowercased addresses we have decimals for, sorted."""
        return sorted(self._decimals)

    def decimals_for(self, address: str) -> int:
        """Return decimals for ``address`` or raise :class:`PriceUnavailable`."""
        try:
            return self._decimals[address.lower()]
        except KeyError as exc:
            raise PriceUnavailable(
                f"no decimals registered for token {address!r}; "
                f"register via GmxPriceAdapter.register_token()"
            ) from exc

    async def fetch_token_price(self, address: str) -> TokenPrice:
        """Read one token's price from Aave + return both scales.

        Two failure modes are normalized to :class:`PriceUnavailable` so
        callers (perps_overview, can_price_market) only have one
        exception type to catch:

        1. Aave returns 0 — the soft-failure mode (some Aave deployments
           silently return zero for unknown assets rather than reverting).
        2. The Aave oracle reverts — the hard-failure mode on Arbitrum,
           where ``getAssetPrice`` will revert with no data for any
           asset that doesn't have an oracle source registered. Live
           Arbitrum behaviour as of 2026-04-30.
        """
        decimals = self.decimals_for(address)
        try:
            usd = await self._aave.get_asset_price(address)
        except Exception as exc:  # noqa: BLE001 — broad on purpose
            # Re-raise as PriceUnavailable so the caller's try/except
            # surface stays narrow. Don't swallow PriceUnavailable
            # itself (would be redundant) and don't swallow KeyboardInterrupt
            # (BaseException, not Exception, so already filtered).
            raise PriceUnavailable(
                f"Aave oracle reverted for {address!r}: {type(exc).__name__}: {exc}"
            ) from exc
        if usd <= 0:
            # Aave returns 0 for tokens it has no oracle feed for.
            # Treat that as unavailable rather than $0 — a $0 GMX price
            # would revert downstream (and silently pricing a perp at $0
            # is a far worse failure mode than raising here).
            raise PriceUnavailable(
                f"Aave oracle returned non-positive price for {address!r}: {usd}"
            )
        # Aave oracle returns USD as Decimal already (raw / 1e8). We
        # rescale to GMX's 10^(30-decimals) shape.
        gmx_scaled = encode_gmx_price(usd, decimals)
        # Aave gives a single point estimate; GMX wants min/max. Use the
        # same value for both — callers wanting a spread can post-process.
        aave_raw = int(usd * (Decimal(10) ** AAVE_PRICE_DECIMALS))
        return TokenPrice(
            address=address.lower(),
            decimals=decimals,
            usd=usd,
            aave_raw=aave_raw,
            gmx_min=gmx_scaled,
            gmx_max=gmx_scaled,
        )

    async def market_prices(
        self,
        market: Market,
    ) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        """Build the GMX ``MarketPrices`` tuple for one market.

        Returns ``((idx_min, idx_max), (long_min, long_max), (short_min, short_max))``
        ready to pass to :meth:`GmxV2Arbitrum.market_info`. Raises
        :class:`PriceUnavailable` if any of the three tokens has no Aave
        feed — caller should drop or quarantine that market.
        """
        idx = await self.fetch_token_price(market.index_token)
        long = await self.fetch_token_price(market.long_token)
        short = await self.fetch_token_price(market.short_token)
        return (idx.as_gmx_props(), long.as_gmx_props(), short.as_gmx_props())

    async def can_price_market(self, market: Market) -> bool:
        """Return ``True`` if every token in ``market`` has a usable Aave price.

        Useful for filtering ``list_markets()`` output before calling
        ``market_info`` in a loop — saves the cost of a failed RPC.
        """
        try:
            await self.market_prices(market)
        except PriceUnavailable:
            return False
        return True


__all__ = (
    "GmxPriceAdapter",
    "TokenPrice",
    "PriceUnavailable",
    "aave_price_to_gmx",
    "AAVE_PRICE_DECIMALS",
)
