"""Aave V3 (Arbitrum One) typed read wrapper.

Mirror of :mod:`lib.chains.megaeth.contracts.aave_v3`. The encode/decode
plumbing, the ``ReserveData`` dataclass, the ``ray_rate_to_apy`` helper,
and the ``UiPoolDataProvider`` row schema are all chain-agnostic — we
re-export them here so callers depending on this module don't have to
reach into the MegaETH package.

Read-only. Write paths (supply / borrow / withdraw / repay) land in a
separate gated executor — they are deliberately NOT in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# Re-use the chain-agnostic encode/decode + dataclasses + helpers from
# the MegaETH wrapper. Aave V3 is the same protocol on both chains; the
# only chain-specific bit is the address bundle and the RPC transport.
from lib.chains.megaeth.contracts.aave_v3 import (  # noqa: F401 — re-export
    BPS_DENOMINATOR,
    RAY,
    SECONDS_PER_YEAR,
    ReserveData,
    UserAccountData,
    _AGGREGATED_RESERVE_FIELDS,
    ray_rate_to_apy,
    reserve_data_from_row,
)

from ..abis.fetcher import load_pinned_abi
from ..registry import ProtocolEntry
from .base import TypedContract, _ChainCallable


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
    "reserve_data_from_row",
    "BPS_DENOMINATOR",
    "RAY",
    "SECONDS_PER_YEAR",
    "_AGGREGATED_RESERVE_FIELDS",
)
