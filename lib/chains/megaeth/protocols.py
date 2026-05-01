"""Intent-level facade over MegaETH protocol wrappers.

Wave A scope: **read intents only.** Composes the registry +
`MegaETHClient` + per-protocol typed wrappers. Callers do not touch
addresses or ABIs directly.

Wave C will add write intents (``swap``, ``supply``, ``borrow``, ...);
they're stubbed here to ``NotImplementedError("Wave C")`` so the
facade's surface is shaped for future wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .contracts.aave_v3 import (
    AaveV3,
    AaveV3Addresses,
    ReserveData,
    UserAccountData,
)
from .contracts.kumbaya import (
    Kumbaya,
    KumbayaAddresses,
    PoolInfo,
)
from .dex_router import DexRoutingTable, SwapQuote, best_quote, quote_kumbaya
from .registry import ProtocolEntry, ProtocolRegistry


@dataclass(frozen=True)
class LendOverview:
    """Aggregate lend-side snapshot composed from one or more lending venues."""

    venue: str                    # "aave_v3" — Wave A is single-venue
    reserve_count: int
    total_supplied_usd: Decimal   # USD-equivalent (base currency = USD * 1e8)
    total_borrowed_usd: Decimal
    avg_supply_apy: float         # weighted by total_supplied_usd
    avg_borrow_apy: float         # weighted by total_borrowed_usd
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
class DexVenueOverview:
    """Per-DEX overview surfaced by :meth:`MegaETHProtocols.dex_overview`."""

    venue: str
    category: str
    pool_count: int
    top_pools: list[PoolInfo] = field(default_factory=list, compare=False)


@dataclass(frozen=True)
class DexOverview:
    """Aggregate DEX overview across all registered DEX-spot venues."""

    venues: list[DexVenueOverview] = field(default_factory=list)

    @property
    def venue_count(self) -> int:
        return len(self.venues)

    @property
    def total_pool_count(self) -> int:
        return sum(v.pool_count for v in self.venues)


class MegaETHProtocols:
    """Intent facade. Construct with a client + (optional) registry override.

    All read intents return frozen dataclasses. All write intents raise
    ``NotImplementedError("Wave C")``. The shape is fixed so future
    wiring just swaps the body.
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

    def _aave(self, venue: str = "aave_v3") -> AaveV3:
        entry = self.registry.get(venue)
        if entry.category != "lending":
            raise ValueError(f"protocol {venue!r} is not a lending venue (category={entry.category})")
        return AaveV3(self._client, AaveV3Addresses.from_registry_entry(entry))

    def _kumbaya(self, venue: str = "kumbaya") -> Kumbaya:
        entry = self.registry.get(venue)
        if entry.category != "dex_spot":
            raise ValueError(
                f"protocol {venue!r} is not a DEX-spot venue (category={entry.category})"
            )
        return Kumbaya(self._client, KumbayaAddresses.from_registry_entry(entry))

    def _dex_routing_table(self) -> DexRoutingTable:
        """Build a DexRoutingTable from every ``dex_spot`` registry entry.

        Wave B step 1: only Kumbaya is wired. Adding more DEXes is just
        another ``register(...)`` call here. Future steps may move this
        registration into the registry yaml itself once we have >1 DEX.
        """
        table = DexRoutingTable()
        for entry in self.registry.by_category("dex_spot"):
            if entry.key == "kumbaya":
                kb = Kumbaya(self._client, KumbayaAddresses.from_registry_entry(entry))

                async def _kb_quote(t_in: str, t_out: str, amt: int, _kb: Kumbaya = kb) -> Any:
                    return await quote_kumbaya(_kb, t_in, t_out, amt)

                table.register(entry.key, _kb_quote)
        return table

    async def lend_overview(self, venue: str = "aave_v3") -> LendOverview:
        """Aggregate lending stats for one venue.

        Wave A wires Aave V3 only; multi-venue composition lands in
        Wave B once Silo v2 + others have wrappers.
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
            sup_usd = (Decimal(r.total_supplied) * price) / (scale * base_unit) if r.decimals else Decimal(0)
            bor_usd = (Decimal(r.total_borrowed) * price) / (scale * base_unit) if r.decimals else Decimal(0)
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

    # -- DEX-spot read paths (Wave B) --------------------------------------

    async def quote_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        *,
        max_hops: int = 2,
    ) -> SwapQuote | None:
        """Best quote for ``amount_in`` of ``token_in`` swapped to ``token_out``.

        Wave B step 1 only routes through Kumbaya direct (single-hop)
        — ``max_hops`` is accepted for forward-compatibility (Wave B
        step 2 will add stable-bridge multi-hop routing through USDM).

        Returns ``None`` if no DEX has a viable pool for the pair, which
        callers should treat as "venue unsupported, fall back to a CEX
        or skip the trade." We deliberately do NOT raise here — empty
        quotes are a normal data condition for niche pairs.
        """
        if max_hops < 1:
            raise ValueError(f"max_hops must be >= 1, got {max_hops!r}")
        # max_hops is not yet used (only direct routes); accepted for
        # API compatibility with Wave B step 2's multi-hop router.
        _ = max_hops

        table = self._dex_routing_table()
        if len(table) == 0:
            return None
        return await best_quote(table, token_in, token_out, amount_in)

    async def dex_overview(self) -> DexOverview:
        """List registered DEXes with their top live pools."""
        venues: list[DexVenueOverview] = []
        for entry in self.registry.by_category("dex_spot"):
            if entry.key == "kumbaya":
                kb = Kumbaya(self._client, KumbayaAddresses.from_registry_entry(entry))
                pools = await kb.top_pools_by_tvl()
                venues.append(
                    DexVenueOverview(
                        venue=entry.key,
                        category=entry.category,
                        pool_count=len(pools),
                        top_pools=pools,
                    )
                )
        return DexOverview(venues=venues)

    # -- write (Wave C) ----------------------------------------------------

    async def swap(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "Wave C: write paths route through plugins/claw-sapphire/tools/internal/megaeth_executor.py"
        )

    async def supply(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Wave C")

    async def borrow(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Wave C")

    async def withdraw(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Wave C")

    async def repay(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Wave C")

    async def bridge(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Wave C")
