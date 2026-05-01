"""GMX V2 (MegaETH) typed read-only wrapper.

Wave B.3 scope: read-only. Targets the GMX V2 ``Reader`` aggregator —
the GMX equivalent of Aave's ``UiPoolDataProvider``. From a single
typed wrapper bound to the verified Reader contract we can:

* enumerate every active market (``list_markets``)
* pull per-market state (``market_info``)
* derive funding-rate APR and OI skew (the two signals the strategy
  layer actually wants)

Write paths (``createOrder`` / ``cancelOrder`` via ``ExchangeRouter``)
land in Wave C and route through ``plugins/claw-sapphire/tools/internal/
megaeth_executor.py``, NOT here. The Reader itself has no state-mutating
functions.

Why no ``mark_price`` / ``pool_value`` field on :class:`MarketInfo`
=================================================================

The original Wave B.3 scoping prompt asked for ``mark_price`` and
``pool_value`` on ``MarketInfo``. After fetching the verified ABI from
Blockscout (`Reader` at 0x0f038EB4… , compiled v0.8.29, 29 functions)
we discovered:

1. The on-chain ``Reader.getMarketInfo(...)`` does NOT return either
   field. Its return tuple holds: ``Market.Props``, two
   ``borrowingFactorPerSecond`` uints, ``BaseFundingValues``,
   ``GetNextFundingAmountPerSizeResult``, ``VirtualInventory``, and
   ``isDisabled``. Mark price is computed by GMX off-chain or via a
   separate ``getMarketTokenPrice(...)`` call that *also* requires the
   off-chain price input.
2. ``Reader.getMarketInfo`` itself takes a ``MarketUtils.MarketPrices``
   tuple as input — meaning callers must pre-fetch index/long/short
   prices from an oracle (Aave, Chainlink, etc.) before calling.
   This is documented by GMX itself; their off-chain keeper bots are
   the canonical price source.
3. Calling ``getMarketInfo`` with zero prices reverts with custom
   error ``0x6afad778``. Verified live on chain 4326 on 2026-04-30.

So this wrapper exposes what the Reader actually returns. ``mark_price``
and ``pool_value`` would require either (a) a separate price-feed
adapter (Wave B.4 or later) or (b) wiring to GMX's hosted Reader off-
chain endpoint. Both belong in the follow-up integration lane.

GMX price encoding (footgun)
============================

GMX V2 ``Price.Props`` are NOT scaled to 1e8 like Aave / Chainlink —
they're scaled to ``10^(30 - tokenDecimals)``. Callers passing prices
to :meth:`market_info` must use :func:`encode_gmx_price` or the math
is wrong by ~22 orders of magnitude. We provide that helper here so
strategy code doesn't have to reinvent it.

Reference: `gmx-io/gmx-synthetics/contracts/price/Price.sol`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _MegaETHCallable

#: Seconds per Julian year. GMX funding rate is "per second"; we annualize it.
SECONDS_PER_YEAR = 365 * 24 * 60 * 60  # 31_536_000

#: GMX-internal price scaling exponent. ``Price.Props`` is stored as
#: ``USD_value * 10**(GMX_PRICE_BASE - decimals)``.
GMX_PRICE_BASE = 30


def encode_gmx_price(usd: Decimal | int | float | str, decimals: int) -> int:
    """Encode a USD price into GMX's ``Price.Props`` scale.

    GMX V2 expects token prices scaled to ``10**(30 - decimals)``. For
    BTC (8 decimals, $70_000) this is ``70000 * 10**22 = 7e26``. For
    USDM (6 decimals, $1) it's ``1 * 10**24 = 1e24``.

    This is the inverse of `priceUsd = props.min / 10**(30 - decimals)`
    that strategy code computes after the call.

    Returns an integer suitable for the ``min``/``max`` field of a
    ``Price.Props`` tuple.
    """
    if decimals < 0 or decimals > GMX_PRICE_BASE:
        raise ValueError(f"decimals must be in [0, {GMX_PRICE_BASE}], got {decimals}")
    usd_d = Decimal(str(usd))
    if usd_d < 0:
        raise ValueError(f"price must be non-negative, got {usd}")
    scaled = usd_d * (Decimal(10) ** (GMX_PRICE_BASE - decimals))
    return int(scaled)


def decode_gmx_price(raw: int, decimals: int) -> Decimal:
    """Inverse of :func:`encode_gmx_price` — turn a ``Price.Props`` field into USD.

    Returns USD as :class:`~decimal.Decimal` for full precision.
    """
    if decimals < 0 or decimals > GMX_PRICE_BASE:
        raise ValueError(f"decimals must be in [0, {GMX_PRICE_BASE}], got {decimals}")
    return Decimal(int(raw)) / (Decimal(10) ** (GMX_PRICE_BASE - decimals))


@dataclass(frozen=True)
class GmxV2Addresses:
    """Address bundle for one GMX V2 deployment.

    Wave B.3 only needs ``reader`` (the read aggregator). ``data_store``
    is the canonical key/value store every read targets — GMX expects
    callers to pass it as the first argument to nearly every Reader
    method, so we keep it on the bundle for ergonomics.

    Other diamond contracts (``ExchangeRouter``, ``OrderHandler``,
    ``EventEmitter``, ...) are intentionally NOT included here — they're
    write-side or event-stream surfaces that belong in Wave C.
    """

    reader: str
    data_store: str

    @classmethod
    def from_registry_entry(cls, entry: ProtocolEntry) -> GmxV2Addresses:
        return cls(
            reader=entry.address("reader"),
            data_store=entry.address("data_store"),
        )


@dataclass(frozen=True)
class Market:
    """One GMX V2 market — the four-address tuple the protocol calls ``Market.Props``.

    On GMX V2, a market is a synthetic order book backed by two
    collateral pools (long_token, short_token) tracking an underlying
    (index_token). The ``market_token`` is the LP receipt for the GLV
    pool that backs this market. ``name`` is a derived display string —
    GMX itself doesn't store names on chain; we render
    ``"<index>/<long>-<short>"`` using the bare addresses (callers can
    override after the fact via ERC-20 ``symbol()`` lookups).
    """

    market_token: str
    index_token: str
    long_token: str
    short_token: str
    name: str


@dataclass(frozen=True)
class MarketInfo:
    """Per-market state read out of ``Reader.getMarketInfo(...)``.

    All ``*_factor`` fields are GMX's native ``per-second`` representation
    in ``1e30`` fixed-point (a value of ``1e30`` is "100% per second").
    Use :meth:`GmxV2.funding_rate_apr` for the convenience APR conversion.

    ``open_interest_long`` / ``open_interest_short`` come from a
    separate ``Reader.getOpenInterestWithPnl(...)`` call and are in USD
    scaled to ``1e30``. Callers needing fraction or float should divide
    by ``1e30``.

    Notes
    -----
    * ``mark_price`` and ``pool_value`` (asked for in the original Wave
      B.3 prompt) are NOT exposed: ``Reader.getMarketInfo`` doesn't
      return them, and the price input we'd have to pass to derive them
      lives off-chain in the Aave / Chainlink oracle layer. See the
      module docstring for the full rationale.
    * ``longs_pay_shorts`` is the funding-direction flag from
      ``nextFunding`` — when ``True``, longs pay shorts (i.e. funding
      is positive); when ``False``, shorts pay longs.
    """

    market: Market
    funding_factor_per_second: int           # 1e30-scaled, abs value
    longs_pay_shorts: bool                   # direction flag
    borrowing_factor_long: int               # 1e30-scaled per-second
    borrowing_factor_short: int              # 1e30-scaled per-second
    open_interest_long: int                  # 1e30-scaled USD (call-time)
    open_interest_short: int                 # 1e30-scaled USD (call-time)
    is_disabled: bool


# ---------------------------------------------------------------------------
# Reader output ABI types — kept as module-level strings so we don't re-derive
# them in every method. These mirror the verified ABI exactly.
# ---------------------------------------------------------------------------

# Market.Props (Reader.getMarket / getMarkets)
_MARKET_PROPS_TYPE = "(address,address,address,address)"

# Price.Props
_PRICE_PROPS_TYPE = "(uint256,uint256)"

# MarketUtils.MarketPrices = (Price idx, Price long, Price short)
_MARKET_PRICES_TYPE = (
    f"({_PRICE_PROPS_TYPE},{_PRICE_PROPS_TYPE},{_PRICE_PROPS_TYPE})"
)

# CollateralType = (uint256 longToken, uint256 shortToken)
_COLLATERAL_TYPE = "(uint256,uint256)"

# PositionType = (CollateralType long, CollateralType short)
_POSITION_TYPE = f"({_COLLATERAL_TYPE},{_COLLATERAL_TYPE})"

# BaseFundingValues = (PositionType fundingFeeAmountPerSize, PositionType claimableFundingAmountPerSize)
_BASE_FUNDING_TYPE = f"({_POSITION_TYPE},{_POSITION_TYPE})"

# GetNextFundingAmountPerSizeResult
#   = (bool, uint256, int256, PositionType, PositionType)
_NEXT_FUNDING_TYPE = f"(bool,uint256,int256,{_POSITION_TYPE},{_POSITION_TYPE})"

# VirtualInventory = (uint256, uint256, int256)
_VIRTUAL_INVENTORY_TYPE = "(uint256,uint256,int256)"

# Full MarketInfo return — must mirror the ABI struct order exactly.
_MARKET_INFO_TYPE = (
    "("
    f"{_MARKET_PROPS_TYPE},"
    "uint256,uint256,"  # borrowingFactorPerSecondForLongs / Shorts
    f"{_BASE_FUNDING_TYPE},"
    f"{_NEXT_FUNDING_TYPE},"
    f"{_VIRTUAL_INVENTORY_TYPE},"
    "bool"
    ")"
)


def _market_from_tuple(row: tuple[Any, ...]) -> Market:
    """Convert a Market.Props tuple into our typed dataclass."""
    if len(row) < 4:
        raise ValueError(f"Market.Props expected 4 fields, got {len(row)}: {row!r}")
    market_token, index_token, long_token, short_token = (
        _addr(row[0]), _addr(row[1]), _addr(row[2]), _addr(row[3])
    )
    # Display name: GMX doesn't store names; we derive a deterministic
    # placeholder. Callers wanting human names should resolve via
    # ERC-20 symbol() lookups separately.
    name = f"{_short_addr(index_token)}/{_short_addr(long_token)}-{_short_addr(short_token)}"
    return Market(
        market_token=market_token,
        index_token=index_token,
        long_token=long_token,
        short_token=short_token,
        name=name,
    )


def _addr(raw: Any) -> str:
    if isinstance(raw, bytes):
        return "0x" + raw.hex()
    if isinstance(raw, str):
        return raw.lower()
    return str(raw)


def _short_addr(addr: str) -> str:
    if not isinstance(addr, str) or len(addr) < 6:
        return str(addr)
    return addr[:6].lower()


# ---------------------------------------------------------------------------
# GmxV2 facade
# ---------------------------------------------------------------------------


class GmxV2:
    """Read-only typed wrapper around a GMX V2 deployment on MegaETH.

    Constructed with a ``MegaETHClient``-shaped object and a bundle of
    addresses (typically pulled from the registry).

    All public methods are async — they bottom out in ``eth_call``.
    """

    def __init__(self, client: _MegaETHCallable, addresses: GmxV2Addresses) -> None:
        self._client = client
        self.addresses = addresses

        self._reader = TypedContract(
            client,
            addresses.reader,
            load_pinned_abi("gmx_v2/reader.json"),
        )

    # ------------------------------------------------------------------
    # Markets enumeration
    # ------------------------------------------------------------------

    async def list_markets(self, *, start: int = 0, end: int = 200) -> list[Market]:
        """Enumerate active markets via ``Reader.getMarkets(dataStore, start, end)``.

        Returns at most ``end - start`` markets. The default upper bound
        of 200 is generous — live mainnet has 6 markets as of TGE day,
        Arbitrum's mature deployment has ~50.
        """
        if start < 0 or end <= start:
            raise ValueError(f"invalid range start={start}, end={end}")
        rows = await self._reader.call(
            "getMarkets",
            self.addresses.data_store,
            int(start),
            int(end),
        )
        out: list[Market] = []
        for row in rows or ():
            try:
                out.append(_market_from_tuple(row))
            except (ValueError, TypeError):
                # Skip malformed rows — production safety, mirrors
                # AaveV3.get_reserves_data behaviour.
                continue
        return out

    async def get_market(self, market_key: str) -> Market:
        """Fetch one market struct by its market-token key."""
        _validate_address(market_key, "market_key")
        row = await self._reader.call(
            "getMarket",
            self.addresses.data_store,
            market_key,
        )
        return _market_from_tuple(row)

    # ------------------------------------------------------------------
    # Per-market state
    # ------------------------------------------------------------------

    async def market_info(
        self,
        market: str,
        prices: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    ) -> MarketInfo:
        """Read funding / borrowing / OI / disabled state for one market.

        ``prices`` is GMX's ``MarketPrices`` struct in tuple form:
        ``((idx_min, idx_max), (long_min, long_max), (short_min, short_max))``.
        Each value MUST be encoded with :func:`encode_gmx_price` —
        passing 1e8-scaled Aave/Chainlink prices directly will revert
        with custom error ``0x6afad778``.

        OI fields ``open_interest_long`` / ``_short`` come from a
        separate ``getOpenInterestWithPnl`` call against the same
        market, using the supplied ``indexTokenPrice`` (the first
        component of ``prices``). This is one extra round-trip;
        GMX doesn't include OI in ``getMarketInfo`` itself.
        """
        _validate_address(market, "market")
        _validate_prices(prices)

        # Step 1 — getMarketInfo. Returns the big ReaderUtils.MarketInfo struct.
        raw = await self._reader.call(
            "getMarketInfo",
            self.addresses.data_store,
            prices,
            market,
        )
        if not isinstance(raw, tuple) or len(raw) < 7:
            raise ValueError(f"unexpected getMarketInfo shape: {type(raw).__name__}")
        market_struct = raw[0]
        borrowing_factor_long = int(raw[1])
        borrowing_factor_short = int(raw[2])
        # raw[3] = baseFunding (we don't surface it — historical accumulators)
        next_funding = raw[4]
        # raw[5] = virtualInventory (not surfaced — internal AMM state)
        is_disabled = bool(raw[6])

        if not isinstance(next_funding, tuple) or len(next_funding) < 2:
            raise ValueError(f"unexpected nextFunding shape: {next_funding!r}")
        longs_pay_shorts = bool(next_funding[0])
        funding_factor = int(next_funding[1])

        # Step 2 — open interest, both sides. getOpenInterestWithPnl
        # takes the Market struct (not just the key) and the index price.
        index_price = prices[0]
        market_props = (
            market_struct[0], market_struct[1], market_struct[2], market_struct[3],
        )
        oi_long = await self._reader.call(
            "getOpenInterestWithPnl",
            self.addresses.data_store,
            market_props,
            index_price,
            True,   # isLong
            False,  # maximize
        )
        oi_short = await self._reader.call(
            "getOpenInterestWithPnl",
            self.addresses.data_store,
            market_props,
            index_price,
            False,  # isLong
            False,  # maximize
        )

        return MarketInfo(
            market=_market_from_tuple(market_struct),
            funding_factor_per_second=funding_factor,
            longs_pay_shorts=longs_pay_shorts,
            borrowing_factor_long=borrowing_factor_long,
            borrowing_factor_short=borrowing_factor_short,
            open_interest_long=int(oi_long),
            open_interest_short=int(oi_short),
            is_disabled=is_disabled,
        )

    # ------------------------------------------------------------------
    # Convenience derivations
    # ------------------------------------------------------------------

    async def funding_rate_apr(
        self,
        market: str,
        prices: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    ) -> Decimal:
        """Convert ``fundingFactorPerSecond`` into a signed annualized rate.

        GMX stores funding as a 1e30-scaled "factor per second". The
        annualized fraction is::

            apr = (factor / 1e30) * SECONDS_PER_YEAR

        Sign convention here follows ``longs_pay_shorts``:
            * positive APR → longs pay shorts (longs are paying funding)
            * negative APR → shorts pay longs

        Returns a :class:`~decimal.Decimal` in fraction form (0.05 == 5%).
        Note: this is APR, not APY — GMX funding doesn't compound;
        positions are settled continuously.
        """
        info = await self.market_info(market, prices)
        return self._funding_apr_from_info(info)

    @staticmethod
    def _funding_apr_from_info(info: MarketInfo) -> Decimal:
        factor = Decimal(int(info.funding_factor_per_second))
        # Per-second fraction, then scale to a year.
        per_sec = factor / Decimal(10) ** GMX_PRICE_BASE
        apr_abs = per_sec * Decimal(SECONDS_PER_YEAR)
        return apr_abs if info.longs_pay_shorts else -apr_abs

    async def oi_skew(
        self,
        market: str,
        prices: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    ) -> Decimal:
        """Long share of total open interest.

        Returns ``Decimal('0.5')`` when the book is balanced or empty.
        Returns ``Decimal('1')`` when the book is 100% long (no shorts),
        ``Decimal('0')`` when 100% short. Uses USD-denominated OI from
        ``getOpenInterestWithPnl``.
        """
        info = await self.market_info(market, prices)
        return self._oi_skew_from_info(info)

    @staticmethod
    def _oi_skew_from_info(info: MarketInfo) -> Decimal:
        long_oi = Decimal(int(info.open_interest_long))
        short_oi = Decimal(int(info.open_interest_short))
        total = long_oi + short_oi
        if total <= 0:
            return Decimal("0.5")
        return long_oi / total


def _validate_address(addr: str, name: str) -> None:
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        raise ValueError(f"invalid {name} address: {addr!r}")


def _validate_prices(prices: Any) -> None:
    """Sanity-check the MarketPrices tuple before encoding."""
    if not isinstance(prices, (tuple, list)) or len(prices) != 3:
        raise ValueError(
            f"prices must be 3-tuple of (min,max) pairs, got {prices!r}"
        )
    for i, p in enumerate(prices):
        if not isinstance(p, (tuple, list)) or len(p) != 2:
            raise ValueError(f"prices[{i}] must be (min,max) pair, got {p!r}")
        mn, mx = p
        if int(mn) < 0 or int(mx) < 0:
            raise ValueError(f"prices[{i}] must be non-negative, got {p!r}")
        if int(mn) > int(mx):
            raise ValueError(f"prices[{i}].min > .max: {p!r}")
