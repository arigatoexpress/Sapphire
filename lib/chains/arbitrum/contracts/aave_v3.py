"""Aave V3 (Arbitrum One) typed read wrapper.

Mirror of :mod:`lib.chains.megaeth.contracts.aave_v3`. The encode/decode
plumbing, the ``ReserveData`` dataclass, and the ``ray_rate_to_apy``
helper are all chain-agnostic — re-exported from the MegaETH package so
callers don't have to reach across packages.

The ``UiPoolDataProvider`` row SCHEMA is chain-specific: Aave's
deployment on Arbitrum still uses the older 54-field layout with
``stableBorrowRate``-era fields, while the MegaETH deployment uses the
post-stable-rate-removal 40-field layout. This module pins Arbitrum's
schema and provides its own row decoder; field semantics that matter
to ``ReserveData`` (LTV, rates, supply/borrow totals, paused/frozen)
are unchanged across the two layouts so the decoded dataclass is
chain-portable.

Read-only. Write paths (supply / borrow / withdraw / repay) land in a
separate gated executor — they are deliberately NOT in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Re-use the chain-agnostic encode/decode + dataclasses + helpers from
# the MegaETH wrapper. Only the row schema differs (see below).
from lib.chains.megaeth.contracts.aave_v3 import (  # noqa: F401 — re-export
    BPS_DENOMINATOR,
    RAY,
    SECONDS_PER_YEAR,
    ReserveData,
    UserAccountData,
    ray_rate_to_apy,
)

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _ChainCallable

# ---------------------------------------------------------------------------
# Arbitrum-specific UiPoolDataProvider row schema (54 fields).
#
# Field order MUST match the on-chain ABI exactly. Sourced from the verified
# UiPoolDataProviderV3 contract at 0x145dE30c929a065582da84Cf96F88460dB9745A7
# (see abis/aave_v3/ui_pool_data_provider.json, full-match Sourcify).
# ---------------------------------------------------------------------------

_AGGREGATED_RESERVE_FIELDS_ARBITRUM: tuple[str, ...] = (
    "underlyingAsset",
    "name",
    "symbol",
    "decimals",
    "baseLTVasCollateral",
    "reserveLiquidationThreshold",
    "reserveLiquidationBonus",
    "reserveFactor",
    "usageAsCollateralEnabled",
    "borrowingEnabled",
    "stableBorrowRateEnabled",
    "isActive",
    "isFrozen",
    "liquidityIndex",
    "variableBorrowIndex",
    "liquidityRate",
    "variableBorrowRate",
    "stableBorrowRate",
    "lastUpdateTimestamp",
    "aTokenAddress",
    "stableDebtTokenAddress",
    "variableDebtTokenAddress",
    "interestRateStrategyAddress",
    "availableLiquidity",
    "totalPrincipalStableDebt",
    "averageStableRate",
    "stableDebtLastUpdateTimestamp",
    "totalScaledVariableDebt",
    "priceInMarketReferenceCurrency",
    "priceOracle",
    "variableRateSlope1",
    "variableRateSlope2",
    "stableRateSlope1",
    "stableRateSlope2",
    "baseStableBorrowRate",
    "baseVariableBorrowRate",
    "optimalUsageRatio",
    "isPaused",
    "isSiloedBorrowing",
    "accruedToTreasury",
    "unbacked",
    "isolationModeTotalDebt",
    "flashLoanEnabled",
    "debtCeiling",
    "debtCeilingDecimals",
    "eModeCategoryId",
    "borrowCap",
    "supplyCap",
    "eModeLtv",
    "eModeLiquidationThreshold",
    "eModeLiquidationBonus",
    "eModePriceSource",
    "eModeLabel",
    "borrowableInIsolation",
)


def _row_to_dict_arbitrum(row: tuple[Any, ...]) -> dict[str, Any]:
    """Pair an Arbitrum-shaped reserve tuple with the field names above.

    If the on-chain layout adds fields in a future upgrade we zip up to
    the shorter side and stash the surplus in ``_extra``.
    """
    n = min(len(row), len(_AGGREGATED_RESERVE_FIELDS_ARBITRUM))
    out = {_AGGREGATED_RESERVE_FIELDS_ARBITRUM[i]: row[i] for i in range(n)}
    if len(row) > n:
        out["_extra"] = list(row[n:])
    return out


def _to_checksum_lower(addr: Any) -> str:
    if isinstance(addr, bytes):
        return "0x" + addr.hex()
    if isinstance(addr, str):
        return addr.lower()
    return str(addr)


def reserve_data_from_row_arbitrum(row: tuple[Any, ...]) -> ReserveData:
    """Decode an Arbitrum UiPoolDataProvider row into :class:`ReserveData`.

    Same output dataclass as the MegaETH decoder — the chain-portable
    fields (LTV, rates, totals, paused/frozen) are derived identically;
    Arbitrum-only fields (stable-rate, eMode, isolation-mode) are stashed
    in ``raw`` for any consumer that wants them.
    """
    d = _row_to_dict_arbitrum(row)

    liquidity_rate = int(d.get("liquidityRate", 0))
    variable_borrow_rate = int(d.get("variableBorrowRate", 0))
    available = int(d.get("availableLiquidity", 0))
    total_borrowed = int(d.get("totalScaledVariableDebt", 0))
    total_supplied = available + total_borrowed
    utilization = (total_borrowed / total_supplied) if total_supplied else 0.0

    return ReserveData(
        underlying_asset=_to_checksum_lower(d.get("underlyingAsset", "")),
        symbol=str(d.get("symbol", "")),
        name=str(d.get("name", "")),
        decimals=int(d.get("decimals", 0)),
        supply_apy=ray_rate_to_apy(liquidity_rate),
        borrow_apy=ray_rate_to_apy(variable_borrow_rate),
        total_supplied=total_supplied,
        total_borrowed=total_borrowed,
        available_liquidity=available,
        utilization=float(utilization),
        ltv=int(d.get("baseLTVasCollateral", 0)) / BPS_DENOMINATOR,
        liquidation_threshold=int(d.get("reserveLiquidationThreshold", 0)) / BPS_DENOMINATOR,
        paused=bool(d.get("isPaused", False)),
        frozen=bool(d.get("isFrozen", False)),
        raw=d,
    )


@dataclass(frozen=True)
class AaveV3Addresses:
    """Address bundle for the Aave V3 deployment on Arbitrum One."""

    pool: str
    pool_addresses_provider: str
    oracle: str
    ui_pool_data_provider: str
    protocol_data_provider: str

    @classmethod
    def from_registry_entry(cls, entry: ProtocolEntry) -> AaveV3Addresses:
        return cls(
            pool=entry.address("pool"),
            pool_addresses_provider=entry.address("pool_addresses_provider"),
            oracle=entry.address("oracle"),
            ui_pool_data_provider=entry.address("ui_pool_data_provider"),
            protocol_data_provider=entry.address("protocol_data_provider"),
        )


class AaveV3Arbitrum:
    """Read-only typed wrapper around the Aave V3 deployment on Arbitrum One.

    Constructed with an :class:`ArbitrumClient`-shaped object (anything
    satisfying the structural ``_call(method, params)`` Protocol) and
    a bundle of addresses (typically pulled from the registry).

    All methods are async because the underlying ``eth_call`` is async.

    The shape is identical to ``lib.chains.megaeth.contracts.aave_v3.AaveV3``
    on purpose — Sentinel and other multi-chain code can ``isinstance`` /
    duck-type either wrapper interchangeably.
    """

    def __init__(self, client: _ChainCallable, addresses: AaveV3Addresses) -> None:
        self._client = client
        self.addresses = addresses

        self._ui = TypedContract(
            client,
            addresses.ui_pool_data_provider,
            load_pinned_abi("aave_v3/ui_pool_data_provider.json"),
        )
        self._oracle = TypedContract(
            client,
            addresses.oracle,
            load_pinned_abi("aave_v3/oracle.json"),
        )
        self._pool = TypedContract(
            client,
            addresses.pool,
            load_pinned_abi("aave_v3/pool_min.json"),
        )

    async def get_reserves_data(self) -> list[ReserveData]:
        """One call → every reserve on the deployment.

        Calls ``UiPoolDataProvider.getReservesData(provider)`` and maps
        the aggregated tuple rows to :class:`ReserveData`.
        """
        result = await self._ui.call(
            "getReservesData",
            self.addresses.pool_addresses_provider,
        )
        if isinstance(result, tuple) and len(result) == 2:
            reserves_array = result[0]
        else:
            reserves_array = result
        out: list[ReserveData] = []
        for row in reserves_array or ():
            try:
                out.append(reserve_data_from_row_arbitrum(row))
            except Exception:
                # Skip malformed rows but keep going — production safety.
                continue
        return out

    async def get_user_account_data(self, user: str) -> UserAccountData:
        """Per-user account snapshot (collateral, debt, HF, etc.)."""
        if not isinstance(user, str) or not user.startswith("0x") or len(user) != 42:
            raise ValueError(f"invalid user address: {user!r}")
        raw = await self._pool.call("getUserAccountData", user)
        (
            total_collateral_base,
            total_debt_base,
            available_borrows_base,
            current_lt_bps,
            ltv_bps,
            health_factor_wad,
        ) = raw
        return UserAccountData(
            total_collateral_base=int(total_collateral_base),
            total_debt_base=int(total_debt_base),
            available_borrows_base=int(available_borrows_base),
            current_liquidation_threshold=int(current_lt_bps) / BPS_DENOMINATOR,
            ltv=int(ltv_bps) / BPS_DENOMINATOR,
            health_factor=Decimal(int(health_factor_wad)) / Decimal(10**18),
        )

    async def get_asset_price(self, asset: str) -> Decimal:
        """Oracle price for ``asset`` in BASE_CURRENCY units (USD * 1e8 on Aave V3 Arbitrum)."""
        if not isinstance(asset, str) or not asset.startswith("0x") or len(asset) != 42:
            raise ValueError(f"invalid asset address: {asset!r}")
        raw = await self._oracle.call("getAssetPrice", asset)
        return Decimal(int(raw)) / Decimal(10**8)


__all__ = (
    "AaveV3Arbitrum",
    "AaveV3Addresses",
    "ReserveData",
    "UserAccountData",
    "ray_rate_to_apy",
    "reserve_data_from_row_arbitrum",
    "BPS_DENOMINATOR",
    "RAY",
    "SECONDS_PER_YEAR",
    "_AGGREGATED_RESERVE_FIELDS_ARBITRUM",
)
