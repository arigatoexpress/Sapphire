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
from .chainlink_oracle import ChainlinkPrice, ChainlinkRegistry
from .gmx_v2 import GMX_PRICE_BASE, Market, encode_gmx_price
from .pyth_oracle import PythRegistry, PythRegistryPrice

#: Aave V3 oracle base-currency exponent on Arbitrum One.
#: ``getAssetPrice`` returns USD * 1e8 (verified against
#: ``AaveOracle.BASE_CURRENCY_UNIT()`` = ``100000000``).
AAVE_PRICE_DECIMALS = 8

#: Token-address → symbol map for Chainlink fallback resolution.
#:
#: GMX index tokens are ERC-20 addresses (or synthetic placeholder
#: addresses with no on-chain ERC-20); Chainlink feeds are keyed by
#: human symbol. This map covers the Arbitrum-Aave-uncovered majors
#: that GMX V2 actually trades. Lowercased addresses; symbols use the
#: *underlying* asset (Chainlink convention) so WBTC → "BTC", not
#: "WBTC". The :class:`ChainlinkRegistry` itself owns wrapped→underlying
#: translation, so passing "WBTC" here would also work — we use the
#: underlying for clarity.
#:
#: Source for synthetic indices: live ``getMarkets()`` enumeration on
#: Arbitrum One mainnet (chain 42161) on 2026-05-02 + per-token
#: ``symbol()``/``decimals()`` probes. Markets with index_token=0x0
#: (swap-only markets) are deliberately omitted — they don't price
#: an underlying.
TOKEN_ADDRESS_TO_CHAINLINK_SYMBOL: dict[str, str] = {
    # --- ERC-20 wrapped majors ---
    "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": "BTC",  # WBTC
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": "ETH",  # WETH
    "0x6c84a8f1c29108f47a79964b5fe888d4f4d0de40": "BTC",  # tBTC (Threshold)
    "0x2bcc6d6cdbbdc0a4071e48bb3b969b06b3330c07": "SOL",  # SOL (Wormhole, 9 decimals)
    "0xb74da9fe2f96b9e0a5f4a3cf0b92dd2bec617124": "SOL",
    "0x565609faf65b92f7be02468acf86f8979423e514": "AVAX",  # WAVAX
    "0xc4da4c24fd591125c3f47b340b6f4f76111883d8": "DOGE",
    "0xf97f4df75117a78c1a5a0dbb814af92458539fb4": "LINK",
    # --- GMX V2 synthetic placeholder indices (no on-chain ERC-20) ---
    # BTC synthetic (the canonical BTC perp market index on Arbitrum)
    "0x47904963fc8b2340414262125af798b9655e58cd": "BTC",
}


class PriceUnavailable(LookupError):
    """Raised when an Aave oracle has no price for the requested token.

    Distinct from a generic ``LookupError`` so callers can quarantine
    affected markets without swallowing real bugs.
    """


@dataclass(frozen=True)
class TokenPrice:
    """A single token's USD price in both Aave and GMX scales.

    ``aave_raw`` is what Aave's oracle returned (USD * 10**8). When the
    price actually came from the Chainlink fallback (Aave had no
    feed), ``aave_raw`` carries the same USD value re-scaled to 1e8 so
    downstream code that expects a 1e8-scaled int still works.
    ``gmx_min`` / ``gmx_max`` are the encoded ``Price.Props`` fields —
    we use the same value for both sides since neither oracle exposes a
    bid/ask spread; if a future caller wants min<max, they can override
    by widening here.

    ``source`` is one of ``"aave"`` (primary), ``"chainlink"``
    (secondary), or ``"pyth"`` (tertiary) — whichever oracle answered.
    ``stale`` is only meaningful for ``source`` in ``{"chainlink",
    "pyth"}`` — Aave reads have no independent staleness signal at
    this layer (their freshness is enforced by Aave's own oracle
    gating). Sentinel / chain-health gate can downweight or refuse a
    result with ``stale=True`` regardless of which oracle served it.
    """

    address: str
    decimals: int
    usd: Decimal
    aave_raw: int
    gmx_min: int
    gmx_max: int
    source: str = "aave"
    stale: bool = False

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
        # Aave-overlapping reserves (verified against Arbiscan).
        "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": 18,  # WETH
        "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": 8,  # WBTC
        "0x912ce59144191c1204e64559fe8253a0e49e6548": 18,  # ARB
        "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": 6,  # USDC.e
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831": 6,  # USDC
        "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": 6,  # USDT
        "0xf97f4df75117a78c1a5a0dbb814af92458539fb4": 18,  # LINK
        "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": 18,  # DAI
        "0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a": 18,  # GMX
        "0x17fc002b466eec40dae837fc4be5c67993ddbd6f": 18,  # FRAX
        "0x5979d7b546e38e414f7e9822514be443a4800529": 18,  # wstETH
        "0xec70dcb4a1efa46b8f2d97c310c9c4790ba5ffa8": 18,  # rETH
        # Chainlink-fallback-priced GMX index tokens (added with the
        # Chainlink fallback PR). Verified live via ERC-20 ``decimals()``
        # probes on 2026-05-02; synthetic placeholders that have no
        # on-chain ``decimals()`` use the natural precision GMX V2
        # documents for that index (BTC=8 from the protocol spec).
        "0x6c84a8f1c29108f47a79964b5fe888d4f4d0de40": 18,  # tBTC
        "0x2bcc6d6cdbbdc0a4071e48bb3b969b06b3330c07": 9,  # SOL (Wormhole)
        "0xb74da9fe2f96b9e0a5f4a3cf0b92dd2bec617124": 9,  # SOL (alt)
        "0x565609faf65b92f7be02468acf86f8979423e514": 18,  # WAVAX
        "0xc4da4c24fd591125c3f47b340b6f4f76111883d8": 8,  # DOGE
        "0x47904963fc8b2340414262125af798b9655e58cd": 8,  # BTC synthetic
    }

    def __init__(
        self,
        aave: AaveV3Arbitrum,
        token_decimals: dict[str, int] | None = None,
        *,
        chainlink: ChainlinkRegistry | None = None,
        token_to_chainlink_symbol: dict[str, str] | None = None,
        pyth: PythRegistry | None = None,
        token_to_pyth_symbol: dict[str, str] | None = None,
    ) -> None:
        """Compose Aave V3 + Chainlink + Pyth oracle reads into GMX MarketPrices.

        Parameters
        ----------
        aave:
            Live :class:`AaveV3Arbitrum` instance — primary price source.
        token_decimals:
            Optional override / extension to :attr:`COMMON_DECIMALS`.
        chainlink:
            Optional :class:`ChainlinkRegistry` — when supplied, used as
            a SECONDARY fallback for tokens that Aave returns
            ``PriceUnavailable`` for. Lane I (PR #565) shipped this
            adapter without Chainlink; PR #570 wired it in.
            Backward-compatible: if not supplied, behaviour is
            identical to the pre-extension version.
        token_to_chainlink_symbol:
            Optional override / extension to
            :data:`TOKEN_ADDRESS_TO_CHAINLINK_SYMBOL`. Lowercased
            address keys, uppercase symbol values.
        pyth:
            Optional :class:`PythRegistry` — when supplied, used as a
            TERTIARY fallback after Chainlink. Independent oracle
            infrastructure (pull-based, off-chain publishers) so a
            chain-side oracle issue (Aave + Chainlink both stale) can
            still be served. Backward-compatible: if not supplied, the
            adapter still works exactly as the Chainlink-only build.
        token_to_pyth_symbol:
            Optional override / extension to the Pyth address→symbol
            map. By default this layer reuses the Chainlink address→symbol
            mapping (since Pyth and Chainlink both key by underlying
            asset symbol — ``"BTC"`` not ``"WBTC"``); pass this kwarg
            only when a token's Pyth symbol differs from its Chainlink
            symbol (rare). Lowercased address keys, uppercase symbol
            values.
        """
        self._aave = aave
        self._chainlink = chainlink
        self._pyth = pyth
        # Defensive copy + lowercase keys — ERC-20 addresses are
        # case-insensitive but the registry sometimes has checksummed.
        merged = dict(self.COMMON_DECIMALS)
        if token_decimals:
            for k, v in token_decimals.items():
                merged[k.lower()] = int(v)
        self._decimals = merged
        # Token-address → Chainlink symbol resolution.
        sym_map = {k.lower(): v.upper() for k, v in TOKEN_ADDRESS_TO_CHAINLINK_SYMBOL.items()}
        if token_to_chainlink_symbol:
            for k, v in token_to_chainlink_symbol.items():
                sym_map[k.lower()] = v.upper()
        self._token_symbols = sym_map
        # Token-address → Pyth symbol. Defaults to the Chainlink map
        # since Pyth and Chainlink both key on the underlying asset
        # symbol — this is the "happy path" and avoids forcing callers
        # to define the same mapping twice.
        pyth_sym_map = dict(sym_map)
        if token_to_pyth_symbol:
            for k, v in token_to_pyth_symbol.items():
                pyth_sym_map[k.lower()] = v.upper()
        self._token_pyth_symbols = pyth_sym_map

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

    def register_chainlink_symbol(self, address: str, symbol: str) -> None:
        """Map a token address to a Chainlink symbol for the fallback path.

        The :class:`ChainlinkRegistry` itself owns symbol→feed; this
        layer owns address→symbol. Useful when a new GMX market lists
        an exotic ``index_token`` that the bundled
        :data:`TOKEN_ADDRESS_TO_CHAINLINK_SYMBOL` doesn't cover.
        """
        if not isinstance(address, str) or not address.startswith("0x"):
            raise ValueError(f"invalid token address: {address!r}")
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"invalid symbol: {symbol!r}")
        self._token_symbols[address.lower()] = symbol.upper()

    def chainlink_symbol_for(self, address: str) -> str | None:
        """Return the Chainlink symbol mapped to ``address`` (or ``None``)."""
        return self._token_symbols.get(address.lower())

    def register_pyth_symbol(self, address: str, symbol: str) -> None:
        """Map a token address to a Pyth symbol for the tertiary fallback path.

        Mirrors :meth:`register_chainlink_symbol`. Useful when a
        token's Pyth symbol differs from its Chainlink symbol (rare —
        defaults to the Chainlink map at construction).
        """
        if not isinstance(address, str) or not address.startswith("0x"):
            raise ValueError(f"invalid token address: {address!r}")
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"invalid symbol: {symbol!r}")
        self._token_pyth_symbols[address.lower()] = symbol.upper()

    def pyth_symbol_for(self, address: str) -> str | None:
        """Return the Pyth symbol mapped to ``address`` (or ``None``)."""
        return self._token_pyth_symbols.get(address.lower())

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
        """Read one token's price, walking Aave → Chainlink → Pyth → unpriced.

        Resolution order (each step tried, falls through on revert / zero
        / unconfigured):

        1. **Aave V3 oracle (primary).** Two failure modes normalized:
           returns ``0`` (soft-fail mode some deployments use) OR reverts
           (live Arbitrum behaviour for assets not in the reserve list).
        2. **Chainlink Data Feed (secondary, optional).** Only tried if
           a :class:`ChainlinkRegistry` was supplied at construction
           AND the token address maps to a Chainlink symbol AND the
           registry has a feed for that symbol.
        3. **Pyth Network (tertiary, optional).** Only tried if a
           :class:`PythRegistry` was supplied at construction AND the
           token address maps to a Pyth symbol AND the registry has a
           priceId for that symbol. Pyth is independent of both Aave
           and Chainlink (different keepers, different incentive model)
           so it survives correlated chain-side oracle outages.

        On any fallback path we still need decimals from
        :attr:`COMMON_DECIMALS` (or a runtime registration) to encode
        the GMX ``Price.Props`` field — ``decimals_for`` is called
        first, before any oracle. A token without registered decimals
        will raise :class:`PriceUnavailable` regardless of whether
        another oracle could price it.

        Raises :class:`PriceUnavailable` if every configured oracle
        either rejected the asset or returned a non-positive value.
        The error message includes a per-oracle failure summary so the
        live debugging path is straightforward.
        """
        decimals = self.decimals_for(address)

        aave_failure: str | None = None
        usd: Decimal = Decimal(0)
        try:
            usd = await self._aave.get_asset_price(address)
        except Exception as exc:  # noqa: BLE001 — broad on purpose
            # Don't immediately re-raise — try fallback oracles before failing.
            aave_failure = f"{type(exc).__name__}: {exc}"

        if aave_failure is None and usd > 0:
            # Aave happy path — same shape as before this PR.
            gmx_scaled = encode_gmx_price(usd, decimals)
            aave_raw = int(usd * (Decimal(10) ** AAVE_PRICE_DECIMALS))
            return TokenPrice(
                address=address.lower(),
                decimals=decimals,
                usd=usd,
                aave_raw=aave_raw,
                gmx_min=gmx_scaled,
                gmx_max=gmx_scaled,
                source="aave",
                stale=False,
            )

        # Aave didn't price the token — try Chainlink fallback (secondary).
        chainlink_failure: str | None = None
        if self._chainlink is not None:
            symbol = self.chainlink_symbol_for(address)
            if symbol is not None:
                cl_oracle = self._chainlink.oracle_for(symbol)
                if cl_oracle is not None:
                    try:
                        cl: ChainlinkPrice = await self._chainlink.fetch_price(symbol)
                    except Exception as exc:  # noqa: BLE001 — Chainlink is best-effort
                        # DON'T re-raise — fall through to Pyth before failing.
                        chainlink_failure = f"{type(exc).__name__}: {exc}"
                    else:
                        if cl.usd > 0:
                            gmx_scaled = encode_gmx_price(cl.usd, decimals)
                            aave_raw = int(cl.usd * (Decimal(10) ** AAVE_PRICE_DECIMALS))
                            return TokenPrice(
                                address=address.lower(),
                                decimals=decimals,
                                usd=cl.usd,
                                aave_raw=aave_raw,
                                gmx_min=gmx_scaled,
                                gmx_max=gmx_scaled,
                                source="chainlink",
                                stale=cl.stale,
                            )
                        chainlink_failure = f"non-positive price: {cl.usd}"
                else:
                    chainlink_failure = f"no Chainlink feed registered for symbol {symbol!r}"
            else:
                chainlink_failure = "no Chainlink symbol mapped for this token"

        # Aave + Chainlink both failed — try Pyth fallback (tertiary).
        pyth_failure: str | None = None
        if self._pyth is not None:
            pyth_symbol = self.pyth_symbol_for(address)
            if pyth_symbol is not None:
                resolved = self._pyth.oracle_for(pyth_symbol)
                if resolved is not None:
                    try:
                        py: PythRegistryPrice = await self._pyth.fetch_price(pyth_symbol)
                    except Exception as exc:  # noqa: BLE001 — Pyth is best-effort
                        pyth_failure = f"{type(exc).__name__}: {exc}"
                    else:
                        if py.usd > 0:
                            gmx_scaled = encode_gmx_price(py.usd, decimals)
                            aave_raw = int(py.usd * (Decimal(10) ** AAVE_PRICE_DECIMALS))
                            return TokenPrice(
                                address=address.lower(),
                                decimals=decimals,
                                usd=py.usd,
                                aave_raw=aave_raw,
                                gmx_min=gmx_scaled,
                                gmx_max=gmx_scaled,
                                source="pyth",
                                stale=py.stale,
                            )
                        pyth_failure = f"non-positive price: {py.usd}"
                else:
                    pyth_failure = f"no Pyth priceId registered for symbol {pyth_symbol!r}"
            else:
                pyth_failure = "no Pyth symbol mapped for this token"

        # Every oracle either rejected or returned non-positive.
        # Compose a per-oracle summary for the live debug path. The
        # word "non-positive" is preserved in the message when Aave
        # returned <= 0 so the long-standing regex contract from the
        # Lane I tests (PR #565) keeps matching.
        if aave_failure is None:
            aave_summary = f"non-positive price {usd}"
        else:
            aave_summary = aave_failure
        cl_summary = (
            chainlink_failure if self._chainlink is not None else "no Chainlink registry configured"
        )
        py_summary = pyth_failure if self._pyth is not None else "no Pyth registry configured"
        raise PriceUnavailable(
            f"every oracle failed for {address!r}: "
            f"aave={aave_summary}; "
            f"chainlink={cl_summary}; "
            f"pyth={py_summary}"
        )

    async def market_prices(
        self,
        market: Market,
    ) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        """Build the GMX ``MarketPrices`` tuple for one market.

        Returns ``((idx_min, idx_max), (long_min, long_max), (short_min, short_max))``
        ready to pass to :meth:`GmxV2Arbitrum.market_info`. Raises
        :class:`PriceUnavailable` if no oracle (Aave primary, Chainlink
        fallback) can price one of the three tokens — caller should
        drop or quarantine that market.

        Per-token source / staleness metadata is dropped to keep the
        return type stable with Lane I (PR #565). Callers needing that
        metadata should use :meth:`market_prices_with_meta`.
        """
        idx, long, short = await self.market_prices_with_meta(market)
        return (idx.as_gmx_props(), long.as_gmx_props(), short.as_gmx_props())

    async def market_prices_with_meta(
        self,
        market: Market,
    ) -> tuple[TokenPrice, TokenPrice, TokenPrice]:
        """Like :meth:`market_prices` but returns the typed ``TokenPrice`` triple.

        Callers that need to know which oracle served each leg (and
        whether any leg was stale) should use this. The downstream
        chain-health gate inspects ``.source`` and ``.stale`` to
        decide whether to escalate severity.
        """
        idx = await self.fetch_token_price(market.index_token)
        long = await self.fetch_token_price(market.long_token)
        short = await self.fetch_token_price(market.short_token)
        return (idx, long, short)

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
    "TOKEN_ADDRESS_TO_CHAINLINK_SYMBOL",
)
