"""Aave V3 (MegaETH) typed read wrapper.

Wave A scope: read-only. ``get_reserves_data`` (one call → every reserve),
``get_user_account_data`` (per-user position summary), ``get_asset_price``.
APY conversion from Aave's per-second ray-encoded rates is centralized
here — that conversion is a known footgun (see :func:`ray_rate_to_apy`).

Write paths (supply/borrow/withdraw/repay) land in Wave C and route
through ``plugins/claw-sapphire/tools/internal/megaeth_executor.py``,
not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _MegaETHCallable

# Constants from Aave's WadRayMath.sol — these are protocol invariants.
RAY = 10**27
SECONDS_PER_YEAR = 365 * 24 * 60 * 60  # 31_536_000

#: BPS denominator used by Aave config fields (LTV, liquidation threshold, etc.).
#: e.g. an LTV of 7500 means 75.00%.
BPS_DENOMINATOR = 10_000


def ray_rate_to_apy(rate_ray_apr: int) -> float:
    """Convert an Aave-style ray-encoded APR to annualized APY.

    KNOWN FOOTGUN: Aave V3's ``liquidityRate`` and ``variableBorrowRate``
    are **ray-encoded annual percentage rates (APR)**, NOT per-second
    rates. The Aave whitepaper writes these as "interest per second"
    but the on-chain field stores the rate already multiplied by
    ``SECONDS_PER_YEAR``, so dividing by 1e27 directly gives the APR.

    Conversion (matches the official Aave UI):

        APR = rate_ray_apr / 1e27
        APY = (1 + APR / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1

    Sanity check: WETH ``liquidityRate=3842250348931316408715874`` gives
    APR ≈ 0.003842 → APY ≈ 0.385%. WETH on the live deployment shows
    0.38% supply APY in the Aave UI — match.

    Reference: aave-v3-origin/src/contracts/protocol/libraries/math/
    MathUtils.sol::calculateCompoundedInterest divides ``rate`` by
    ``SECONDS_PER_YEAR`` before each per-second compounding.

    Returns the APY as a fraction (0.05 == 5%).
    """
    if rate_ray_apr <= 0:
        return 0.0
    apr = rate_ray_apr / RAY
    rate_per_second = apr / SECONDS_PER_YEAR
    # math.expm1(N * log1p(r)) is more accurate than (1+r)**N - 1 for
    # the small-rate regime that Aave operates in.
    return math.expm1(SECONDS_PER_YEAR * math.log1p(rate_per_second))


@dataclass(frozen=True)
class AaveV3Addresses:
    """Address bundle for one Aave V3 deployment."""

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


@dataclass(frozen=True)
class ReserveData:
    """Per-asset Aave V3 reserve snapshot.

    ``supply_apy`` and ``borrow_apy`` are floats in fraction form
    (0.05 == 5% APY), converted from ray-encoded per-second rates by
    :func:`ray_rate_to_apy`.
    ``ltv`` and ``liquidation_threshold`` are floats in fraction form
    too (0.75 == 75%), normalized from Aave's BPS encoding.
    Decimal-ish "amount" fields stay as ``int`` in raw token units —
    callers convert using ``decimals``.
    """

    underlying_asset: str
    symbol: str
    name: str
    decimals: int
    supply_apy: float
    borrow_apy: float
    total_supplied: int           # aTokenSupply, raw token units
    total_borrowed: int           # totalScaledVariableDebt, raw token units (already wad-converted)
    available_liquidity: int      # raw token units in the pool
    utilization: float            # 0.0..1.0
    ltv: float                    # 0.0..1.0
    liquidation_threshold: float  # 0.0..1.0
    paused: bool
    frozen: bool
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class UserAccountData:
    """Aave Pool.getUserAccountData() return — values in BASE units (USD-equiv * 1e8)."""

    total_collateral_base: int
    total_debt_base: int
    available_borrows_base: int
    current_liquidation_threshold: float  # fraction
    ltv: float                            # fraction
    health_factor: Decimal                # ray-encoded; we convert to Decimal for precision


# ---------------------------------------------------------------------------
# Helpers — turn the raw (tuple) UiPoolDataProvider output into ReserveData
# ---------------------------------------------------------------------------

# UiPoolDataProvider.getReservesData() returns
#   (AggregatedReserveData[] reserves, BaseCurrencyInfo baseCurrency)
#
# AggregatedReserveData has ~30 fields. The ones we surface are listed
# below; the rest are stashed in `raw` for any consumer that needs them.
# Index map sourced from the Aave v3 UiPoolDataProviderV3 ABI we have
# pinned at abis/aave_v3/ui_pool_data_provider.json.

_AGGREGATED_RESERVE_FIELDS: tuple[str, ...] = (
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
    "isActive",
    "isFrozen",
    "liquidityIndex",
    "variableBorrowIndex",
    "liquidityRate",
    "variableBorrowRate",
    "lastUpdateTimestamp",
    "aTokenAddress",
    "variableDebtTokenAddress",
    "interestRateStrategyAddress",
    "availableLiquidity",
    "totalScaledVariableDebt",
    "priceInMarketReferenceCurrency",
    "priceOracle",
    "variableRateSlope1",
    "variableRateSlope2",
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
    "borrowCap",
    "supplyCap",
    "borrowableInIsolation",
    "virtualAccActive",
    "virtualUnderlyingBalance",
)


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    """Pair a positional tuple with the field names above.

    The ABI may add fields over time. We safely zip up to whichever
    is shorter and stash the surplus in ``_extra``.
    """
    n = min(len(row), len(_AGGREGATED_RESERVE_FIELDS))
    out = {_AGGREGATED_RESERVE_FIELDS[i]: row[i] for i in range(n)}
    if len(row) > n:
        out["_extra"] = list(row[n:])
    return out


def _to_checksum_lower(addr: Any) -> str:
    if isinstance(addr, bytes):
        return "0x" + addr.hex()
    if isinstance(addr, str):
        return addr.lower()
    return str(addr)


def reserve_data_from_row(row: tuple[Any, ...]) -> ReserveData:
    d = _row_to_dict(row)

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


# ---------------------------------------------------------------------------
# AaveV3 facade
# ---------------------------------------------------------------------------


class AaveV3:
    """Read-only typed wrapper around an Aave V3 deployment on MegaETH.

    Constructed with a ``MegaETHClient``-shaped object and a bundle of
    addresses (typically pulled from the registry).

    All methods are async because the underlying ``eth_call`` is async.
    """

    def __init__(self, client: _MegaETHCallable, addresses: AaveV3Addresses) -> None:
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
        # result is (reserves_array, base_currency_struct)
        if isinstance(result, tuple) and len(result) == 2:
            reserves_array = result[0]
        else:
            reserves_array = result  # defensive — older ABI shapes
        out: list[ReserveData] = []
        for row in reserves_array or ():
            try:
                out.append(reserve_data_from_row(row))
            except Exception:
                # Skip malformed rows but keep going — production safety.
                continue
        return out

    async def get_user_account_data(self, user: str) -> UserAccountData:
        """Per-user account snapshot (collateral, debt, HF, etc.)."""
        if not isinstance(user, str) or not user.startswith("0x") or len(user) != 42:
            raise ValueError(f"invalid user address: {user!r}")
        raw = await self._pool.call("getUserAccountData", user)
        # raw is a 6-tuple of uint256.
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
            # Aave returns HF as a wad (1e18); a value of type(uint256).max
            # signifies "infinite" (no debt) — we pass it through as a Decimal
            # so callers can handle the sentinel however they prefer.
            health_factor=Decimal(int(health_factor_wad)) / Decimal(10**18),
        )

    async def get_asset_price(self, asset: str) -> Decimal:
        """Oracle price for ``asset`` in BASE_CURRENCY units (8 decimals).

        Returned as a :class:`~decimal.Decimal` already scaled by
        ``10**baseCurrencyDecimals`` (which is 1e8 on Aave V3 deployments
        using USD-pegged base). Callers wanting raw uint should reach
        through the lower-level :class:`TypedContract`.
        """
        if not isinstance(asset, str) or not asset.startswith("0x") or len(asset) != 42:
            raise ValueError(f"invalid asset address: {asset!r}")
        raw = await self._oracle.call("getAssetPrice", asset)
        # AaveOracle on Aave V3 reports prices in BASE_CURRENCY_UNIT == 1e8
        # for USD-pegged deployments. This conversion is a soft assumption;
        # callers needing exactness should query BASE_CURRENCY_UNIT.
        return Decimal(int(raw)) / Decimal(10**8)
