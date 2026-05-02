"""Intent-level facade over Arbitrum protocol wrappers.

Mirror of :class:`lib.chains.megaeth.protocols.MegaETHProtocols`. Composes
the registry + ``ArbitrumClient`` + per-protocol typed wrappers. Callers
do not touch addresses or ABIs directly.

Read-only. Write intents (``swap``, ``supply``, ``borrow``, ...) raise
``NotImplementedError`` so the facade's surface is shaped for future
wiring without leaking writeable methods today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contracts.aave_v3 import (
    AaveV3Addresses,
    AaveV3Arbitrum,
    ReserveData,
    UserAccountData,
)
from .contracts.gmx_price_adapter import GmxPriceAdapter, PriceUnavailable
from .contracts.gmx_v2 import (
    GmxV2Addresses,
    GmxV2Arbitrum,
    Market,
    MarketInfo,
)
from .registry import ProtocolEntry, ProtocolRegistry


@dataclass(frozen=True)
class LendOverview:
    """Aggregate lend-side snapshot composed from one or more lending venues.

    Field shape mirrors :class:`lib.chains.megaeth.protocols.LendOverview`
    so multi-chain consumers (e.g. Sentinel chain-health gate) can treat
    either chain's overview interchangeably.
    """

    venue: str  # "aave_v3" — wave 1 is single-venue
    reserve_count: int
    total_supplied_usd: Decimal  # USD-equivalent (base currency = USD * 1e8)
    total_borrowed_usd: Decimal
    avg_supply_apy: float  # weighted by total_supplied_usd
    avg_borrow_apy: float  # weighted by total_borrowed_usd
    top_supply_apy: list[dict[str, Any]] = field(default_factory=list)
    top_borrow_apy: list[dict[str, Any]] = field(default_factory=list)
    reserves: list[ReserveData] = field(default_factory=list, compare=False, repr=False)


@dataclass(frozen=True)
class UserLendPosition:
    """User-level position summary; thin wrapper around UserAccountData."""

    venue: str
    user: str
    account: UserAccountData


@dataclass(frozen=True)
class PerpsMarketState:
    """One GMX V2 market's snapshot — priced, error, or unpriced.

    ``state`` is one of:
        * ``"ok"``       — fully priced + read; ``info`` populated
        * ``"disabled"`` — read succeeded but ``info.is_disabled``
        * ``"unpriced"`` — Aave has no oracle for one of the tokens
        * ``"error"``    — RPC raised; ``reason`` carries detail

    ``info`` is ``None`` for the unpriced/error cases. ``funding_apr``,
    ``oi_skew``, and ``oi_total_usd`` are populated only when ``info``
    is present.
    """

    market: Market
    state: str
    info: MarketInfo | None
    funding_apr: Decimal | None
    oi_skew: Decimal | None
    oi_total_usd: Decimal | None
    reason: str | None = None


@dataclass(frozen=True)
class PerpsOverview:
    """Aggregate perps snapshot composed from one venue (GMX V2 in wave 1).

    Field shape mirrors :class:`LendOverview` so multi-protocol
    consumers (Sentinel chain-health gate) can treat lend/perps blocks
    uniformly.
    """

    venue: str
    market_count: int
    priced_count: int
    unpriced_count: int
    avg_funding_apr: Decimal
    markets: list[PerpsMarketState] = field(default_factory=list, compare=False, repr=False)


class ArbitrumProtocols:
    """Intent facade for Arbitrum One protocols.

    Construct with a client + (optional) registry override.
    All read intents return frozen dataclasses. All write intents raise
    ``NotImplementedError`` — write paths land in their own gated
    executor (mirror of the MegaETH wave-C pattern).
    """

    def __init__(
        self,
        client: Any,
        registry: ProtocolRegistry | None = None,
    ) -> None:
        self._client = client
        self.registry = registry or ProtocolRegistry.from_yaml()

    # -- read --------------------------------------------------------------

    def list_protocols(self) -> list[ProtocolEntry]:
        return self.registry.list_protocols()

    def _aave(self, venue: str = "aave_v3") -> AaveV3Arbitrum:
        entry = self.registry.get(venue)
        if entry.category != "lending":
            raise ValueError(
                f"protocol {venue!r} is not a lending venue (category={entry.category})"
            )
        return AaveV3Arbitrum(self._client, AaveV3Addresses.from_registry_entry(entry))

    async def lend_overview(self, venue: str = "aave_v3") -> LendOverview:
        """Aggregate lending stats for one venue.

        Wave 1 wires Aave V3 only; multi-venue composition can land
        once additional Arbitrum lending wrappers exist.
        """
        aave = self._aave(venue)
        reserves = await aave.get_reserves_data()

        # USD-equivalent supplied/borrowed using each reserve's reported
        # `priceInMarketReferenceCurrency` (1e8-scaled). Stored in raw.
        total_supplied_usd = Decimal(0)
        total_borrowed_usd = Decimal(0)
        weighted_supply = Decimal(0)
        weighted_borrow = Decimal(0)

        for r in reserves:
            price = Decimal(int(r.raw.get("priceInMarketReferenceCurrency", 0)))
            scale = Decimal(10) ** Decimal(r.decimals)
            base_unit = Decimal(10**8)  # AaveOracle base currency (USD * 1e8)
            sup_usd = (
                (Decimal(r.total_supplied) * price) / (scale * base_unit)
                if r.decimals
                else Decimal(0)
            )
            bor_usd = (
                (Decimal(r.total_borrowed) * price) / (scale * base_unit)
                if r.decimals
                else Decimal(0)
            )
            total_supplied_usd += sup_usd
            total_borrowed_usd += bor_usd
            weighted_supply += sup_usd * Decimal(str(r.supply_apy))
            weighted_borrow += bor_usd * Decimal(str(r.borrow_apy))

        avg_supply_apy = float(weighted_supply / total_supplied_usd) if total_supplied_usd else 0.0
        avg_borrow_apy = float(weighted_borrow / total_borrowed_usd) if total_borrowed_usd else 0.0

        top_supply = sorted(
            [
                {"symbol": r.symbol, "supply_apy": r.supply_apy, "asset": r.underlying_asset}
                for r in reserves
                if not r.paused
            ],
            key=lambda x: -x["supply_apy"],
        )[:5]
        top_borrow = sorted(
            [
                {"symbol": r.symbol, "borrow_apy": r.borrow_apy, "asset": r.underlying_asset}
                for r in reserves
                if not r.paused
            ],
            key=lambda x: -x["borrow_apy"],
        )[:5]

        return LendOverview(
            venue=venue,
            reserve_count=len(reserves),
            total_supplied_usd=total_supplied_usd,
            total_borrowed_usd=total_borrowed_usd,
            avg_supply_apy=avg_supply_apy,
            avg_borrow_apy=avg_borrow_apy,
            top_supply_apy=top_supply,
            top_borrow_apy=top_borrow,
            reserves=reserves,
        )

    async def lend_user_position(self, user: str, venue: str = "aave_v3") -> UserLendPosition:
        aave = self._aave(venue)
        account = await aave.get_user_account_data(user)
        return UserLendPosition(venue=venue, user=user, account=account)

    async def oracle_price(self, asset: str, venue: str = "aave_v3") -> Decimal:
        aave = self._aave(venue)
        return await aave.get_asset_price(asset)

    # -- perps (GMX V2, append-only extension) -----------------------------

    def _gmx(self, venue: str = "gmx_v2") -> GmxV2Arbitrum:
        """Build a typed GMX V2 wrapper for the requested venue.

        Mirror of :meth:`_aave` — looks up the registry entry, validates
        the category, and constructs the wrapper. Cheap to call (no
        RPC), so we don't memoize.
        """
        entry = self.registry.get(venue)
        if entry.category != "perps":
            raise ValueError(
                f"protocol {venue!r} is not a perps venue (category={entry.category})"
            )
        return GmxV2Arbitrum(self._client, GmxV2Addresses.from_registry_entry(entry))

    def _price_adapter(self, lend_venue: str = "aave_v3") -> GmxPriceAdapter:
        """Build a GmxPriceAdapter composed over our Aave wrapper."""
        return GmxPriceAdapter(self._aave(lend_venue))

    async def perps_overview(
        self,
        venue: str = "gmx_v2",
        *,
        max_markets: int = 50,
    ) -> "PerpsOverview":
        """Aggregate perps snapshot — markets enumerated, priced where possible.

        Returns a :class:`PerpsOverview` with a per-market state list.
        Markets whose tokens lack Aave prices are surfaced as
        ``PerpsMarketState(state="unpriced", ...)`` rather than dropped —
        the caller (chain-health gate, dashboard) needs to know they
        exist, not just that they were skipped.
        """
        gmx = self._gmx(venue)
        adapter = self._price_adapter()

        markets = await gmx.list_markets(start=0, end=int(max_markets))
        priced: list[PerpsMarketState] = []
        unpriced_count = 0
        funding_aprs: list[Decimal] = []

        for m in markets:
            try:
                prices = await adapter.market_prices(m)
            except PriceUnavailable as exc:
                unpriced_count += 1
                priced.append(
                    PerpsMarketState(
                        market=m,
                        state="unpriced",
                        info=None,
                        funding_apr=None,
                        oi_skew=None,
                        oi_total_usd=None,
                        reason=str(exc),
                    )
                )
                continue
            try:
                info = await gmx.market_info(m.market_token, prices)
            except Exception as exc:  # noqa: BLE001 — surface, don't break loop
                priced.append(
                    PerpsMarketState(
                        market=m,
                        state="error",
                        info=None,
                        funding_apr=None,
                        oi_skew=None,
                        oi_total_usd=None,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            apr = GmxV2Arbitrum._funding_apr_from_info(info)
            skew = GmxV2Arbitrum._oi_skew_from_info(info)
            total_oi = (Decimal(info.open_interest_long) + Decimal(info.open_interest_short))
            # Convert 1e30-scaled USD to plain USD Decimal for callers.
            oi_total_usd = total_oi / (Decimal(10) ** 30)

            funding_aprs.append(apr)
            priced.append(
                PerpsMarketState(
                    market=m,
                    state="ok" if not info.is_disabled else "disabled",
                    info=info,
                    funding_apr=apr,
                    oi_skew=skew,
                    oi_total_usd=oi_total_usd,
                    reason=None,
                )
            )

        priced_count = sum(1 for s in priced if s.state == "ok")
        avg_apr = (
            sum((Decimal(0) + a for a in funding_aprs), Decimal(0)) / Decimal(len(funding_aprs))
            if funding_aprs
            else Decimal(0)
        )

        return PerpsOverview(
            venue=venue,
            market_count=len(markets),
            priced_count=priced_count,
            unpriced_count=unpriced_count,
            avg_funding_apr=avg_apr,
            markets=priced,
        )

    async def perps_market_info(
        self,
        market: str,
        venue: str = "gmx_v2",
    ) -> MarketInfo:
        """Read one market's full state, sourcing prices from Aave on the fly."""
        gmx = self._gmx(venue)
        adapter = self._price_adapter()
        m = await gmx.get_market(market)
        prices = await adapter.market_prices(m)
        return await gmx.market_info(market, prices)

    async def perps_funding_rate_apr(
        self,
        market: str,
        venue: str = "gmx_v2",
    ) -> Decimal:
        """Signed annualized funding fraction for one market.

        Positive → longs pay shorts. Negative → shorts pay longs.
        See :meth:`GmxV2Arbitrum.funding_rate_apr` for the math.
        """
        gmx = self._gmx(venue)
        adapter = self._price_adapter()
        m = await gmx.get_market(market)
        prices = await adapter.market_prices(m)
        return await gmx.funding_rate_apr(market, prices)

    async def perps_oi_skew(
        self,
        market: str,
        venue: str = "gmx_v2",
    ) -> Decimal:
        """Long share of open interest (0..1, 0.5 = balanced/empty)."""
        gmx = self._gmx(venue)
        adapter = self._price_adapter()
        m = await gmx.get_market(market)
        prices = await adapter.market_prices(m)
        return await gmx.oi_skew(market, prices)

    # -- write (deferred) --------------------------------------------------

    async def swap(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "write paths route through a gated arbitrum_executor (not in this PR)"
        )

    async def supply(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def borrow(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def withdraw(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def repay(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")
