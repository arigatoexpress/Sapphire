"""Aave-oracle → GMX price-feed adapter.

Wave B.3 follow-up. Bridges :class:`AaveV3` (which exposes USD-scaled
prices via the on-chain :class:`AaveOracle`) with :func:`encode_gmx_price`
so callers don't have to reinvent the GMX ``MarketPrices`` encoding
every time they want to call :meth:`GmxV2.market_info`.

GMX V2 ``Reader.getMarketInfo`` requires a pre-fetched
``MarketUtils.MarketPrices`` tuple — see ``gmx_v2.py`` module docstring
for the full rationale. We pull each token's USD price out of Aave's
oracle (which is already wired into the facade for `lend_overview` and
`stable_health`), encode each into the GMX scale, and hand back a tuple
ready to feed into the wrapper.

If a token does NOT have an Aave oracle entry (Aave's price feed
covers the lending venue's reserves; GMX's index/long/short tokens
are usually a SUPERSET of that), :meth:`prices_for_market` raises
:class:`KeyError` so the caller can decide whether to (a) fall back
to a different price source (Chainlink, GMX's own off-chain keeper,
TWAP from a Kumbaya pool) or (b) skip the market.

Why this is its own module
==========================

Lives next to ``gmx_v2.py`` rather than inside it because it has a
hard dependency on :class:`AaveV3` — keeping it separate means the
GMX wrapper itself stays oracle-agnostic and other callers (Wave C
order placement; future Chainlink-based price source) can swap a
different adapter in.

The adapter is async because both Aave reads and GMX reads are
async. The full price fetch for a 3-token market is 3 sequential
``getAssetPrice`` calls — that's ~150 ms on a healthy RPC. Hot loops
should cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .aave_v3 import AaveV3
from .gmx_v2 import GmxV2, Market, encode_gmx_price


@dataclass(frozen=True)
class TokenDecimals:
    """Per-token decimals lookup. Most strategy code knows decimals up-front."""

    index: int = 18
    long: int = 18
    short: int = 6


#: GMX ``MarketPrices`` tuple shape. Each Price.Props is ``(min, max)``.
MarketPrices = tuple[tuple[int, int], tuple[int, int], tuple[int, int]]


class GmxPriceAdapter:
    """Pulls Aave-oracle USD prices and encodes them for GMX.

    Construct with an :class:`AaveV3` and a :class:`GmxV2` instance
    (both already bound to the same client). The adapter is stateless
    beyond its constructor inputs — call :meth:`prices_for_market` or
    :meth:`prices_for_market_address` from anywhere.
    """

    def __init__(self, aave_v3: AaveV3, gmx: GmxV2) -> None:
        self._aave = aave_v3
        self._gmx = gmx

    async def prices_for_market(
        self,
        market: Market,
        *,
        decimals: TokenDecimals | None = None,
    ) -> MarketPrices:
        """Encode a 3-tuple of ``Price.Props`` for ``market``.

        Reads the index/long/short token prices via the Aave oracle in
        sequence, then encodes each via :func:`encode_gmx_price`. The
        ``min`` and ``max`` Price.Props fields are set equal — GMX uses
        the spread between them for slippage calc, but for read-only
        ``getMarketInfo`` we want the on-the-nose price, no manipulated
        band.

        ``decimals`` defaults to the typical GMX deployment shape
        (index=18 e.g. WETH/WBTC, long=18 e.g. WETH, short=6 e.g.
        USDM/USDC). Callers querying markets where this differs (e.g.
        an 8-decimal index like a WBTC adapter) should pass an explicit
        :class:`TokenDecimals`.

        Raises :class:`KeyError` if any of the three tokens is not
        registered with the Aave oracle (the read returns 0). Callers
        that need fallback price sources should catch this.
        """
        d = decimals or TokenDecimals()

        idx_usd = await self._aave.get_asset_price(market.index_token)
        long_usd = await self._aave.get_asset_price(market.long_token)
        short_usd = await self._aave.get_asset_price(market.short_token)

        if idx_usd <= 0:
            raise KeyError(f"Aave oracle has no price for index token {market.index_token}")
        if long_usd <= 0:
            raise KeyError(f"Aave oracle has no price for long token {market.long_token}")
        if short_usd <= 0:
            raise KeyError(f"Aave oracle has no price for short token {market.short_token}")

        idx_props = _to_props(idx_usd, d.index)
        long_props = _to_props(long_usd, d.long)
        short_props = _to_props(short_usd, d.short)
        return (idx_props, long_props, short_props)

    async def prices_for_market_address(
        self,
        market_addr: str,
        *,
        decimals: TokenDecimals | None = None,
    ) -> MarketPrices:
        """Convenience: look up the :class:`Market` via ``list_markets`` then delegate.

        Walks ``GmxV2.list_markets()`` to find the market with the
        matching ``market_token`` (case-insensitive). Raises
        :class:`KeyError` if not found.

        For hot loops, prefer holding the :class:`Market` and calling
        :meth:`prices_for_market` directly — this method does an extra
        round-trip per call.
        """
        markets = await self._gmx.list_markets()
        target = market_addr.lower()
        for m in markets:
            if m.market_token.lower() == target:
                return await self.prices_for_market(m, decimals=decimals)
        raise KeyError(
            f"market {market_addr!r} not found in GMX V2 list_markets() "
            f"(checked {len(markets)} markets)"
        )


def _to_props(usd: Decimal | int | float, decimals: int) -> tuple[int, int]:
    """Encode one USD price into a Price.Props tuple ``(min, max)``.

    Both fields are set to the same value — read-only callers don't
    care about GMX's slippage band; that matters only for write paths
    (Wave C).
    """
    encoded: int = encode_gmx_price(usd, decimals)
    return (encoded, encoded)


__all__ = [
    "GmxPriceAdapter",
    "MarketPrices",
    "TokenDecimals",
]


# Tiny guard so the module raises on import if someone accidentally
# breaks the AaveV3 / GmxV2 import paths during a refactor.
assert AaveV3 is not None
assert GmxV2 is not None
assert encode_gmx_price is not None
assert isinstance(Market, type)
