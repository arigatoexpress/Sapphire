"""Aave-oracle → GMX price-feed adapter, with optional Pyth fallback.

Wave B.3 follow-up. Bridges :class:`AaveV3` (which exposes USD-scaled
prices via the on-chain :class:`AaveOracle`) with :func:`encode_gmx_price`
so callers don't have to reinvent the GMX ``MarketPrices`` encoding
every time they want to call :meth:`GmxV2.market_info`.

GMX V2 ``Reader.getMarketInfo`` requires a pre-fetched
``MarketUtils.MarketPrices`` tuple — see ``gmx_v2.py`` module docstring
for the full rationale. We pull each token's USD price out of Aave's
oracle (which is already wired into the facade for ``lend_overview`` and
``stable_health``), encode each into the GMX scale, and hand back a tuple
ready to feed into the wrapper.

Pyth fallback (Wave B.3 follow-up #2)
=====================================

If a token does NOT have an Aave oracle entry (Aave's price feed
covers the lending venue's reserves; GMX's index/long/short tokens
are typically a SUPERSET of that), the adapter previously raised
:class:`KeyError` and the caller skipped the market. On MegaETH this
left every GMX V2 market unpriced — Aave's coverage is essentially
disjoint from GMX's index tokens (BTC, ETH, SOL).

The optional ``pyth`` constructor kwarg adds Pyth Network as the
secondary price source. When Aave returns no price for a token,
the adapter consults the :class:`PythRegistry` via the
``address_to_symbol`` mapping. If Pyth has a live priceId for the
resolved symbol, we use that price instead — and tag the result with
``stale=True`` if the Pyth feed hasn't updated within ``max_pyth_age_s``
seconds (default 1h).

If both Aave AND Pyth fail to price a token, :meth:`prices_for_market`
still raises :class:`KeyError` so the caller can mark the market
``state="unpriced"``. Both-source-failure is a real signal —
the market genuinely cannot be priced from on-chain data right now.

Why this is its own module
==========================

Lives next to ``gmx_v2.py`` rather than inside it because it has hard
dependencies on :class:`AaveV3` and :class:`PythRegistry` — keeping it
separate means the GMX wrapper itself stays oracle-agnostic and other
callers (Wave C order placement; future Synthetix-based price source)
can swap a different adapter in.

The adapter is async because all three reads (Aave, Pyth, GMX) are
async. The full price fetch for a 3-token market is up to 3 sequential
``getAssetPrice`` calls + up to 3 sequential ``getPriceUnsafe`` calls
(only on Aave miss). On a healthy MegaETH RPC, that's ~150-300 ms.
Hot loops should cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .aave_v3 import AaveV3
from .gmx_v2 import GmxV2, Market, encode_gmx_price
from .pyth_oracle import (
    DEFAULT_MAX_AGE_S as PYTH_DEFAULT_MAX_AGE_S,
    PythRegistry,
)


@dataclass(frozen=True)
class TokenDecimals:
    """Per-token decimals lookup. Most strategy code knows decimals up-front."""

    index: int = 18
    long: int = 18
    short: int = 6


#: GMX ``MarketPrices`` tuple shape. Each Price.Props is ``(min, max)``.
MarketPrices = tuple[tuple[int, int], tuple[int, int], tuple[int, int]]


#: Default address→symbol map for the MegaETH GMX V2 markets.
#:
#: Every entry here is a checksum-cased EVM address resolved on the
#: live MegaETH chain (chain id 4326). When the adapter falls back to
#: Pyth on an Aave miss, we look the raw GMX token address up in this
#: map to find the symbol Pyth knows.
#:
#: Empty by default — callers must populate this explicitly via the
#: ``address_to_symbol`` constructor kwarg or by passing a populated
#: map at facade construction. Reason: token addresses on MegaETH
#: are still moving as the chain matures; hard-coding stale addresses
#: would silently break the fallback.
DEFAULT_ADDRESS_TO_SYMBOL: dict[str, str] = {}


@dataclass(frozen=True)
class TokenPriceSource:
    """Per-token price-source tag (debug + observability).

    Surfaced via :meth:`GmxPriceAdapter.last_sources` after a successful
    :meth:`prices_for_market` call so callers (dashboards, Sentinel
    health checks) can see which oracle priced each leg of the market.
    """

    token: str
    source: str  # "aave" | "pyth" | "missing"
    stale: bool = False


class GmxPriceAdapter:
    """Pulls Aave-oracle USD prices and encodes them for GMX, with Pyth fallback.

    Construct with an :class:`AaveV3` and a :class:`GmxV2` instance
    (both already bound to the same client). The adapter is stateless
    beyond its constructor inputs and the per-call ``last_sources``
    tracker — call :meth:`prices_for_market` or
    :meth:`prices_for_market_address` from anywhere.

    Pyth fallback wiring
    --------------------

    Pass ``pyth=PythRegistry(client)`` to enable the secondary price
    source. The ``address_to_symbol`` map (defaults to
    :data:`DEFAULT_ADDRESS_TO_SYMBOL`, empty) tells the adapter how to
    translate a raw GMX token address (which has no symbol info on
    chain) into a symbol the Pyth registry knows. Wrapped → underlying
    resolution happens inside the Pyth registry, so this map can use
    either form (``"WBTC"`` or ``"BTC"``).

    Without ``pyth``, the adapter behaves exactly as the original Wave
    B.3 implementation: Aave-only, raises :class:`KeyError` on miss.
    """

    def __init__(
        self,
        aave_v3: AaveV3,
        gmx: GmxV2,
        *,
        pyth: PythRegistry | None = None,
        address_to_symbol: dict[str, str] | None = None,
        max_pyth_age_s: int = PYTH_DEFAULT_MAX_AGE_S,
    ) -> None:
        self._aave = aave_v3
        self._gmx = gmx
        self._pyth = pyth
        # Defensive copy + lower-case keys — address comparison is case-insensitive.
        merged = {k.lower(): v for k, v in DEFAULT_ADDRESS_TO_SYMBOL.items()}
        if address_to_symbol:
            for k, v in address_to_symbol.items():
                merged[k.lower()] = v
        self._addr_to_sym = merged
        self._max_pyth_age_s = int(max_pyth_age_s)
        # Per-call observability — populated by prices_for_market.
        self._last_sources: tuple[TokenPriceSource, ...] = ()

    @property
    def has_pyth_fallback(self) -> bool:
        """Whether a Pyth registry was wired in at construction."""
        return self._pyth is not None

    @property
    def last_sources(self) -> tuple[TokenPriceSource, ...]:
        """Per-token price-source tags from the most recent successful call.

        Empty tuple before any call. Each call replaces the entry.
        Callers that need per-call history should snapshot this
        immediately after each :meth:`prices_for_market` call.
        """
        return self._last_sources

    def register_token_symbol(self, address: str, symbol: str) -> None:
        """Add or override an address→symbol mapping at runtime.

        Useful when a new GMX market lists and we don't want to bump
        :data:`DEFAULT_ADDRESS_TO_SYMBOL` until a release.
        """
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise ValueError(f"invalid token address: {address!r}")
        self._addr_to_sym[address.lower()] = symbol

    def _resolve_symbol(self, address: str) -> str | None:
        """Return the registered symbol for ``address`` (case-insensitive)."""
        return self._addr_to_sym.get(address.lower())

    async def _price_one_token(
        self, token_address: str, *, role: str
    ) -> tuple[Decimal, TokenPriceSource]:
        """Fetch one token's USD price, trying Aave first then Pyth.

        Returns ``(usd_price, source_tag)``. Raises :class:`KeyError`
        only when BOTH price sources fail (or when the Aave path fails
        and no Pyth fallback is wired).

        ``role`` is just a label for the source tag ("index", "long",
        "short") so the observability tuple stays human-readable.

        Aave failure modes covered:
          * Returns 0  → token unknown to the oracle (typical case).
          * Reverts    → on some deployments, ``getAssetPrice`` reverts
                         instead of returning 0 (caught + treated as
                         "Aave miss" so we fall through to Pyth).
        """
        # Primary: Aave oracle. Wrap in try/except — some MegaETH Aave
        # deployments revert on unknown assets instead of returning 0.
        aave_usd = Decimal(0)
        try:
            aave_usd = await self._aave.get_asset_price(token_address)
        except Exception:  # noqa: BLE001 — any Aave failure → fall through
            aave_usd = Decimal(0)
        if aave_usd > 0:
            return aave_usd, TokenPriceSource(token=token_address, source="aave", stale=False)

        # Fallback: Pyth.
        if self._pyth is not None:
            symbol = self._resolve_symbol(token_address)
            if symbol is not None:
                resolved = self._pyth.oracle_for(symbol)
                if resolved is not None:
                    aggregator, price_id = resolved
                    try:
                        pyth_price = await aggregator.get_price_unsafe(price_id)
                    except Exception:  # noqa: BLE001 — Pyth revert is a fallthrough condition
                        pass
                    else:
                        try:
                            usd = pyth_price.as_decimal_usd()
                        except ValueError:
                            # Non-positive Pyth answer → treat as miss.
                            pass
                        else:
                            stale = pyth_price.is_stale(self._max_pyth_age_s)
                            return usd, TokenPriceSource(
                                token=token_address, source="pyth", stale=stale
                            )

        # Both sources failed — the caller should mark the market unpriced.
        raise KeyError(
            f"no price source available for {role} token {token_address} "
            f"(aave_usd={aave_usd}; pyth={'wired' if self._pyth else 'absent'})"
        )

    async def prices_for_market(
        self,
        market: Market,
        *,
        decimals: TokenDecimals | None = None,
    ) -> MarketPrices:
        """Encode a 3-tuple of ``Price.Props`` for ``market``.

        Reads the index/long/short token prices in sequence — Aave
        first, Pyth fallback if wired and Aave returns 0 — then
        encodes each via :func:`encode_gmx_price`. The ``min`` and
        ``max`` Price.Props fields are set equal: GMX uses the spread
        between them for slippage calc, but for read-only
        ``getMarketInfo`` we want the on-the-nose price.

        ``decimals`` defaults to the typical GMX deployment shape
        (index=18 e.g. WETH/WBTC, long=18 e.g. WETH, short=6 e.g.
        USDM/USDC). Callers querying markets where this differs (e.g.
        an 8-decimal index like a WBTC adapter) should pass an explicit
        :class:`TokenDecimals`.

        Side-effect: updates :attr:`last_sources` with one
        :class:`TokenPriceSource` per token, in (index, long, short)
        order. Callers wanting to detect stale-Pyth or both-source
        failures can inspect this immediately after the call.

        Raises :class:`KeyError` if any of the three tokens has no
        price source (Aave returned 0 AND either Pyth is absent or
        Pyth doesn't know the symbol). Callers wanting to mark the
        market ``state="unpriced"`` should catch this.
        """
        d = decimals or TokenDecimals()

        idx_usd, idx_src = await self._price_one_token(market.index_token, role="index")
        long_usd, long_src = await self._price_one_token(market.long_token, role="long")
        short_usd, short_src = await self._price_one_token(market.short_token, role="short")

        self._last_sources = (idx_src, long_src, short_src)

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

    def any_stale(self) -> bool:
        """Whether any token in the most recent call used a stale Pyth price.

        Returns ``False`` when no call has been made yet, OR when all
        sources were Aave (Aave doesn't surface staleness — it relies
        on lender-grade keepers). Sentinel can refuse to act on
        markets where this returns ``True``.
        """
        return any(s.stale for s in self._last_sources)


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
    "TokenPriceSource",
    "DEFAULT_ADDRESS_TO_SYMBOL",
]


# Tiny guard so the module raises on import if someone accidentally
# breaks the AaveV3 / GmxV2 import paths during a refactor.
assert AaveV3 is not None
assert GmxV2 is not None
assert encode_gmx_price is not None
assert isinstance(Market, type)
assert PythRegistry is not None
