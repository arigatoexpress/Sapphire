"""Intent-level facade over Optimism protocol wrappers.

Mirror of :class:`lib.chains.arbitrum.protocols.ArbitrumProtocols`.
Composes the registry + ``OptimismClient`` + per-protocol typed wrappers.
Callers do not touch addresses or ABIs directly.

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
    AaveV3Optimism,
    ReserveData,
    UserAccountData,
)
from .contracts.pyth_oracle import PythRegistry
from .registry import ProtocolEntry, ProtocolRegistry


@dataclass(frozen=True)
class LendOverview:
    """Aggregate lend-side snapshot composed from one or more lending venues.

    Field shape mirrors :class:`lib.chains.arbitrum.protocols.LendOverview`
    so multi-chain consumers (Sentinel chain-health gate) can treat any
    chain's overview interchangeably.
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


class OptimismProtocols:
    """Intent facade for Optimism mainnet protocols.

    Construct with a client + (optional) registry override. All read
    intents return frozen dataclasses. All write intents raise
    ``NotImplementedError`` — write paths land in their own gated
    executor (mirror of the MegaETH wave-C pattern).
    """

    def __init__(
        self,
        client: Any,
        registry: ProtocolRegistry | None = None,
        *,
        pyth: PythRegistry | None = None,
    ) -> None:
        self._client = client
        self.registry = registry or ProtocolRegistry.from_yaml()
        # PythRegistry is constructed eagerly with the same client so
        # callers don't have to wire it up themselves. The aggregator
        # contract handle inside is built lazily on first use. Tests can
        # override by passing ``pyth=`` (e.g. with a stub registry).
        self.pyth: PythRegistry = pyth if pyth is not None else PythRegistry(client)

    # -- read --------------------------------------------------------------

    def list_protocols(self) -> list[ProtocolEntry]:
        return self.registry.list_protocols()

    def _aave(self, venue: str = "aave_v3") -> AaveV3Optimism:
        entry = self.registry.get(venue)
        if entry.category != "lending":
            raise ValueError(
                f"protocol {venue!r} is not a lending venue (category={entry.category})"
            )
        return AaveV3Optimism(self._client, AaveV3Addresses.from_registry_entry(entry))

    async def lend_overview(self, venue: str = "aave_v3") -> LendOverview:
        """Aggregate lending stats for one venue.

        Wave 1 wires Aave V3 only; multi-venue composition can land once
        additional Optimism lending wrappers exist.
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

    async def pyth_price(self, symbol: str) -> Decimal | None:
        """Convenience: USD price from Pyth for ``symbol`` (or ``None``).

        Resolves the symbol through :data:`WRAPPED_TO_UNDERLYING`
        (so ``"WBTC"``, ``"BTC"``, and ``"WBtc"`` all work). Returns
        ``None`` for unknown symbols and for any error during the read
        (RPC failure, contract revert, non-positive price). Callers
        wanting the raw error or the staleness flag should drive
        :class:`PythRegistry` directly via ``self.pyth.fetch_price``.

        Soft-fail by design — this is the *fallback* path in the
        chain-health gate. Hard errors here would defeat the whole
        purpose of having a redundant oracle.
        """
        if self.pyth.price_id(symbol) is None:
            return None
        try:
            record = await self.pyth.fetch_price(symbol)
        except Exception:  # noqa: BLE001 — fallback path: never raise
            return None
        return record.usd

    # -- write (deferred) --------------------------------------------------

    async def swap(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "write paths route through a gated optimism_executor (not in this PR)"
        )

    async def supply(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def borrow(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def withdraw(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")

    async def repay(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("write deferred")
