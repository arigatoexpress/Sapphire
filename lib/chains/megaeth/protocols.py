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
from .contracts.gmx_price_adapter import GmxPriceAdapter, MarketPrices, TokenDecimals
from .contracts.gmx_v2 import (
    GMX_PRICE_BASE,
    GmxV2,
    GmxV2Addresses,
    MarketInfo,
)
from .contracts.kumbaya import (
    Kumbaya,
    KumbayaAddresses,
    PoolInfo,
)
from .contracts.peg_monitor import PegBreak, PegMonitor, PegSnapshot
from .contracts.usdm import USDM, USDMAddresses
from .dex_router import DexRoutingTable, SwapQuote, best_quote, quote_kumbaya
from .registry import ProtocolEntry, ProtocolRegistry


@dataclass(frozen=True)
class LendOverview:
    """Aggregate lend-side snapshot composed from one or more lending venues."""

    venue: str  # "aave_v3" — Wave A is single-venue
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


@dataclass(frozen=True)
class StableHealth:
    """Composite stable-health snapshot — peg + supply + auth state.

    The single object Wave C strategy code consumes when deciding
    whether USDM is safe collateral / safe quote leg right now.

    Notes on the optional fields:

    * ``collateral_ratio`` is ``None`` for the live USDm — collateral
      is off-chain at the LayerZero source. See :meth:`USDM.collateral_ratio`.
    * ``mint_paused`` / ``redeem_paused`` are ``None`` for the live
      USDm — the OFT does not expose a global pause flag. The
      actionable signal lives in :meth:`USDM.recent_mints` /
      ``recent_redeems`` instead.
    * ``should_block_leverage`` is the bool the caller usually wants:
      ``True`` means refuse new exposure right now.
    """

    venue: str  # "usdm" — single-stable Wave B.2
    peg_snapshot: PegSnapshot
    collateral_ratio: Decimal | None
    mint_open: bool | None
    redeem_open: bool | None
    circulating_supply: Decimal
    severity: PegBreak
    should_block_leverage: bool
    block_reason: str


@dataclass(frozen=True)
class MarketSummary:
    """Compact summary of one GMX V2 market — the slice the LLM consumes.

    Surfaces only what the agent layer / dashboard needs (display name +
    the four-address tuple). Use :meth:`MegaETHProtocols.perps_market_info`
    for funding/OI/borrowing detail on a single market.
    """

    name: str
    market_token: str
    index_token: str
    long_token: str
    short_token: str
    is_disabled: bool


@dataclass(frozen=True)
class PerpsOverview:
    """Aggregate perps-side snapshot composed from one venue (GMX V2 in B.3)."""

    venue: str  # "gmx_v2" — Wave B.3 is single-venue
    market_count: int
    markets: list[MarketSummary] = field(default_factory=list)
    # Total open interest across markets, USD-denominated. ``Decimal(0)`` if
    # ``include_funding=False`` was passed (the default — the OI fetch costs
    # 2 RPC reads per market).
    total_oi_usd: Decimal = Decimal(0)
    # Top-3 markets by abs(funding APR), keyed by market_token. Empty when
    # ``include_funding=False`` to keep the lightweight call lightweight.
    funding_extremes: dict[str, Decimal] = field(default_factory=dict)


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
        # NOTE — must use ``is None`` not ``or`` here. ProtocolRegistry
        # implements ``__len__`` so an empty registry (used in tests)
        # is *falsy* under truthy-coercion. The ``or`` form would
        # silently swap a deliberately-empty registry for the on-disk
        # default — exactly the kind of footgun that hides registry
        # injection in tests. Caught by Wave B.2's
        # test_build_kumbaya_quote_fn_returns_none_when_kumbaya_absent.
        self.registry = registry if registry is not None else ProtocolRegistry.from_yaml()

    # -- read --------------------------------------------------------------

    def list_protocols(self) -> list[ProtocolEntry]:
        return self.registry.list_protocols()

    def _aave(self, venue: str = "aave_v3") -> AaveV3:
        entry = self.registry.get(venue)
        if entry.category != "lending":
            raise ValueError(
                f"protocol {venue!r} is not a lending venue (category={entry.category})"
            )
        return AaveV3(self._client, AaveV3Addresses.from_registry_entry(entry))

    def _kumbaya(self, venue: str = "kumbaya") -> Kumbaya:
        entry = self.registry.get(venue)
        if entry.category != "dex_spot":
            raise ValueError(
                f"protocol {venue!r} is not a DEX-spot venue (category={entry.category})"
            )
        return Kumbaya(self._client, KumbayaAddresses.from_registry_entry(entry))

    def _usdm(self, venue: str = "usdm") -> USDM:
        entry = self.registry.get(venue)
        if entry.category != "stable":
            raise ValueError(
                f"protocol {venue!r} is not a stable venue (category={entry.category})"
            )
        return USDM(self._client, USDMAddresses.from_registry_entry(entry))

    def _gmx(self, venue: str = "gmx_v2") -> GmxV2:
        entry = self.registry.get(venue)
        if entry.category != "dex_perps":
            raise ValueError(
                f"protocol {venue!r} is not a perps venue (category={entry.category})"
            )
        return GmxV2(self._client, GmxV2Addresses.from_registry_entry(entry))

    def _price_adapter(
        self,
        *,
        gmx_venue: str = "gmx_v2",
        aave_venue: str = "aave_v3",
    ) -> GmxPriceAdapter:
        """Build a fresh price adapter wired to the registered venues."""
        return GmxPriceAdapter(
            aave_v3=self._aave(aave_venue),
            gmx=self._gmx(gmx_venue),
        )

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

    # -- Stable peg health (Wave B step 2) ---------------------------------

    def _build_kumbaya_usdm_quote_fn(self, usdm_addr: str) -> Any | None:
        """Return an async callable that quotes 1 USDM in USDT0 via Kumbaya.

        Returns ``None`` when no Kumbaya venue is registered. The
        callable is bound to the canonical USDM/USDT0 0.01% pool —
        the same pool the protocol map cites as the venue-priced
        USDM peg source.

        Lifted to a method so :meth:`stable_health` and
        :meth:`peg_status` share one implementation, and so unit
        tests can stub it.
        """
        try:
            kb_entry = self.registry.get("kumbaya")
        except KeyError:
            return None

        try:
            usdt0_addr = self.registry.get("usdt0").address("token")
        except KeyError:
            # No USDT0 entry registered — the AaveOracle and TWAP60
            # paths still work, so we degrade gracefully rather than
            # erroring the whole peg quote.
            return None

        kb = Kumbaya(self._client, KumbayaAddresses.from_registry_entry(kb_entry))
        # 1 USDM at 18 decimals = 10**18 raw units. USDT0 is 6 decimals,
        # so the quote returns a 6-decimal amount that we divide by 1e6
        # to land on a USDT0-per-USDM ratio (close to 1.0 at peg).
        usdm = usdm_addr
        usdt0 = usdt0_addr

        async def _quote() -> Decimal:
            quote = await kb.quote_exact_input_single(
                token_in=usdm,
                token_out=usdt0,
                fee=100,
                amount_in=10**18,
            )
            return Decimal(quote.amount_out) / Decimal(10**6)

        return _quote

    def _build_aave_oracle_call_fn(self, usdm_addr: str) -> Any | None:
        """Return an async callable that fetches USDM USD price from AaveOracle.

        Returns ``None`` when no Aave V3 venue is registered.
        Reuses :meth:`AaveV3.get_asset_price`, which already
        returns a USD-scaled :class:`Decimal`.
        """
        try:
            self.registry.get("aave_v3")
        except KeyError:
            return None
        aave = self._aave("aave_v3")

        async def _call() -> Decimal:
            return await aave.get_asset_price(usdm_addr)

        return _call

    async def stable_health(self, venue: str = "usdm") -> StableHealth:
        """Composite peg + supply + auth-state snapshot for a stable.

        Composes:
          * :meth:`USDM.peg_quote` across all three available sources,
          * :meth:`PegMonitor.evaluate` for severity classification,
          * :meth:`USDM.collateral_ratio` (returns ``None`` for live USDm —
            see the wrapper docstring for why),
          * :meth:`USDM.mint_paused` / ``redeem_paused`` (also ``None``
            for the OFT — same reason),
          * :meth:`USDM.circulating_supply`,
          * :meth:`PegMonitor.should_block_trade` for the bool gate.

        Wave B.2 single-stable: ``venue`` is always ``"usdm"``.
        Future bridged stables (USDT0 has its own peg-health path,
        ditto USDe) get added by registering them in the yaml and
        extending this method's dispatch.
        """
        usdm = self._usdm(venue)
        kumbaya_fn = self._build_kumbaya_usdm_quote_fn(usdm.addresses.token)
        aave_fn = self._build_aave_oracle_call_fn(usdm.addresses.token)

        monitor = PegMonitor()
        snapshot = await monitor.evaluate(
            usdm,
            kumbaya_quote_fn=kumbaya_fn,
            aave_oracle_call_fn=aave_fn,
        )

        circulating = await usdm.circulating_supply()
        col_ratio = await usdm.collateral_ratio()
        mint_p = await usdm.mint_paused()
        redeem_p = await usdm.redeem_paused()
        should_block, reason = monitor.should_block_trade(snapshot)

        return StableHealth(
            venue=venue,
            peg_snapshot=snapshot,
            collateral_ratio=col_ratio,
            # When the underlying read is None (off-chain managed), surface
            # None up rather than guessing. Callers must treat None as
            # "unknown — gate on peg-snapshot severity instead".
            mint_open=None if mint_p is None else not mint_p,
            redeem_open=None if redeem_p is None else not redeem_p,
            circulating_supply=circulating,
            severity=snapshot.severity,
            should_block_leverage=should_block,
            block_reason=reason,
        )

    async def peg_status(self, venue: str = "usdm") -> PegBreak:
        """Quick severity-only check.

        Composes the same three peg sources as :meth:`stable_health`
        but skips the supply read and the dataclass packaging for
        hot loops that just need the severity classification.

        Strategy code that polls every block should prefer this;
        anything calling once per minute should use
        :meth:`stable_health` for the richer dataclass.
        """
        usdm = self._usdm(venue)
        kumbaya_fn = self._build_kumbaya_usdm_quote_fn(usdm.addresses.token)
        aave_fn = self._build_aave_oracle_call_fn(usdm.addresses.token)
        snapshot = await PegMonitor().evaluate(
            usdm,
            kumbaya_quote_fn=kumbaya_fn,
            aave_oracle_call_fn=aave_fn,
        )
        return snapshot.severity

    async def is_safe_for_leverage(
        self,
        venue: str = "usdm",
        *,
        min_severity_to_block: PegBreak = PegBreak.BREAK_100BP,
        require_sources: int = 2,
    ) -> tuple[bool, str]:
        """Convenience wrapper: ``(True, "")`` when safe, ``(False, reason)`` when not.

        Returns the **inverse** of :meth:`PegMonitor.should_block_trade`
        with the same defaults — the reason string is empty on the
        safe path and human-readable on the unsafe path.

        Strategy code shape::

            ok, reason = await proto.is_safe_for_leverage()
            if not ok:
                logger.warning("USDM leverage blocked: %s", reason)
                return
        """
        usdm = self._usdm(venue)
        kumbaya_fn = self._build_kumbaya_usdm_quote_fn(usdm.addresses.token)
        aave_fn = self._build_aave_oracle_call_fn(usdm.addresses.token)
        snapshot = await PegMonitor().evaluate(
            usdm,
            kumbaya_quote_fn=kumbaya_fn,
            aave_oracle_call_fn=aave_fn,
        )
        block, reason = PegMonitor.should_block_trade(
            snapshot,
            min_severity_to_block=min_severity_to_block,
            require_sources=require_sources,
        )
        if block:
            return (False, reason)
        return (True, "")

    # -- Perps read paths (Wave B.3 follow-up) -----------------------------

    async def perps_overview(
        self,
        venue: str = "gmx_v2",
        *,
        include_funding: bool = False,
        token_decimals: TokenDecimals | None = None,
    ) -> PerpsOverview:
        """Enumerate active GMX V2 markets with optional funding overlay.

        Default ``include_funding=False`` does ONE RPC call (``getMarkets``)
        and returns a thin summary list — cheap enough for dashboard polling.
        Setting ``include_funding=True`` triggers a per-market price fetch +
        ``getMarketInfo`` + 2x ``getOpenInterestWithPnl`` (cost = N * 4 reads,
        currently ~24 reads for the 6-market mainnet).

        Markets flagged ``isDisabled`` are skipped from ``markets`` but counted
        in ``market_count`` so callers see the gap. ``funding_extremes`` ranks
        markets by absolute funding APR.
        """
        gmx = self._gmx(venue)
        markets = await gmx.list_markets()
        active = [m for m in markets if m.market_token]  # all entries from list_markets

        # Build summaries — we don't yet know is_disabled without
        # getMarketInfo, so we pass False; if include_funding=True we
        # patch them up below.
        summaries = [
            MarketSummary(
                name=m.name,
                market_token=m.market_token,
                index_token=m.index_token,
                long_token=m.long_token,
                short_token=m.short_token,
                is_disabled=False,
            )
            for m in active
        ]

        if not include_funding:
            return PerpsOverview(
                venue=venue,
                market_count=len(active),
                markets=summaries,
                total_oi_usd=Decimal(0),
                funding_extremes={},
            )

        # Heavyweight path — fetch funding + OI for every market.
        adapter = self._price_adapter(gmx_venue=venue)
        funding_apr: dict[str, Decimal] = {}
        total_oi = Decimal(0)
        patched_summaries: list[MarketSummary] = []

        for i, m in enumerate(active):
            try:
                prices = await adapter.prices_for_market(m, decimals=token_decimals)
                info = await gmx.market_info(m.market_token, prices)
            except (KeyError, ValueError):
                # Token has no Aave oracle entry, or revert. Skip funding +
                # OI for this market but keep the summary.
                patched_summaries.append(summaries[i])
                continue

            apr = GmxV2._funding_apr_from_info(info)
            funding_apr[m.market_token] = apr
            # OI is 1e30-scaled USD per the GMX wrapper docstring.
            scale = Decimal(10) ** GMX_PRICE_BASE
            total_oi += (Decimal(info.open_interest_long) + Decimal(info.open_interest_short)) / scale
            patched_summaries.append(
                MarketSummary(
                    name=m.name,
                    market_token=m.market_token,
                    index_token=m.index_token,
                    long_token=m.long_token,
                    short_token=m.short_token,
                    is_disabled=info.is_disabled,
                )
            )

        # Top-3 markets by abs(APR) — sorted so the strongest signal wins.
        ordered = sorted(funding_apr.items(), key=lambda kv: -abs(kv[1]))
        top_funding = dict(ordered[:3])

        return PerpsOverview(
            venue=venue,
            market_count=len(active),
            markets=patched_summaries,
            total_oi_usd=total_oi,
            funding_extremes=top_funding,
        )

    async def perps_market_info(
        self,
        market_addr: str,
        venue: str = "gmx_v2",
        *,
        token_decimals: TokenDecimals | None = None,
    ) -> MarketInfo:
        """Full per-market state (funding + OI + borrowing) for ``market_addr``.

        Pulls prices via :class:`GmxPriceAdapter` (Aave oracle → GMX scale)
        then calls :meth:`GmxV2.market_info`. Total RPC cost: 1 list +
        3 oracle reads + 1 getMarketInfo + 2 getOpenInterestWithPnl = 7.
        """
        adapter = self._price_adapter(gmx_venue=venue)
        prices: MarketPrices = await adapter.prices_for_market_address(
            market_addr,
            decimals=token_decimals,
        )
        gmx = self._gmx(venue)
        return await gmx.market_info(market_addr, prices)

    async def perps_funding_rate_apr(
        self,
        market_addr: str,
        venue: str = "gmx_v2",
        *,
        token_decimals: TokenDecimals | None = None,
    ) -> Decimal:
        """Annualized funding rate for one market (signed Decimal fraction).

        Convenience around :meth:`perps_market_info`. Sign convention
        matches :meth:`GmxV2.funding_rate_apr`: positive → longs pay shorts.
        """
        info = await self.perps_market_info(
            market_addr, venue=venue, token_decimals=token_decimals
        )
        # Reuse the static helper so the math lives in exactly one place.
        return GmxV2._funding_apr_from_info(info)

    async def perps_oi_skew(
        self,
        market_addr: str,
        venue: str = "gmx_v2",
        *,
        token_decimals: TokenDecimals | None = None,
    ) -> Decimal:
        """Long share of open interest for one market: ``long / (long + short)``.

        Returns ``Decimal('0.5')`` when the book is balanced or empty,
        ``Decimal('1')`` when 100% long, ``Decimal('0')`` when 100% short.
        """
        info = await self.perps_market_info(
            market_addr, venue=venue, token_decimals=token_decimals
        )
        return GmxV2._oi_skew_from_info(info)

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
