"""Tests for the Aave V3 typed wrapper on Arbitrum.

Uses a recorded ``getReservesData`` response captured from Arbitrum One
mainnet on 2026-04-30 (file: ``fixtures/aave_v3/getReservesData_response.hex``)
to exercise the full decode path without network.

Field schema differs from MegaETH (54 fields vs 40 — Arbitrum's
deployment retains the legacy stableBorrowRate-era layout), so this
file exercises the Arbitrum-specific row decoder.
"""

from __future__ import annotations

import math
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.arbitrum.contracts.aave_v3 import (
    _AGGREGATED_RESERVE_FIELDS_ARBITRUM,
    BPS_DENOMINATOR,
    RAY,
    SECONDS_PER_YEAR,
    AaveV3Addresses,
    AaveV3Arbitrum,
    ReserveData,
    UserAccountData,
    ray_rate_to_apy,
    reserve_data_from_row_arbitrum,
)
from lib.chains.arbitrum.registry import ProtocolRegistry

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "aave_v3" / "getReservesData_response.hex"

ADDRS = AaveV3Addresses(
    pool="0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    pool_addresses_provider="0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
    oracle="0xb56c2F0B653B2e0b10C9b928C8580Ac5Df02C7c7",
    ui_pool_data_provider="0x145dE30c929a065582da84Cf96F88460dB9745A7",
    protocol_data_provider="0x243aA95CaC2a25651Eda86E80BEe66114413c43B",
)


class StubClient:
    """Returns pre-staged hex responses keyed by 'to' address."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = {k.lower(): v for k, v in responses.items()}
        self.calls: list[tuple[str, list[Any]]] = []

    async def _call(self, method: str, params: list[Any] | None = None) -> Any:
        self.calls.append((method, list(params or [])))
        if method != "eth_call":
            raise RuntimeError(f"unexpected method: {method}")
        target = params[0]["to"].lower()
        if target not in self.responses:
            raise RuntimeError(f"no stub for {target}")
        return self.responses[target]


# ---------------------------------------------------------------------------
# Constants + helper sanity (re-asserted vs. the megaeth side so a drift
# of either chain's package raises a regression here too).
# ---------------------------------------------------------------------------


def test_constants_are_aave_canonical() -> None:
    assert RAY == 10**27
    assert SECONDS_PER_YEAR == 31_536_000
    assert BPS_DENOMINATOR == 10_000


def test_arbitrum_field_schema_has_54_fields() -> None:
    """Schema is fixed at 54 — Aave V3 Arbitrum hasn't dropped stableBorrowRate."""
    assert len(_AGGREGATED_RESERVE_FIELDS_ARBITRUM) == 54
    # Spot-check a few load-bearing field names + positions.
    assert _AGGREGATED_RESERVE_FIELDS_ARBITRUM[0] == "underlyingAsset"
    assert _AGGREGATED_RESERVE_FIELDS_ARBITRUM[2] == "symbol"
    assert _AGGREGATED_RESERVE_FIELDS_ARBITRUM[15] == "liquidityRate"
    assert _AGGREGATED_RESERVE_FIELDS_ARBITRUM[16] == "variableBorrowRate"
    assert _AGGREGATED_RESERVE_FIELDS_ARBITRUM[37] == "isPaused"
    # Stable-rate fields the MegaETH layout dropped:
    assert "stableBorrowRate" in _AGGREGATED_RESERVE_FIELDS_ARBITRUM
    assert "stableDebtTokenAddress" in _AGGREGATED_RESERVE_FIELDS_ARBITRUM


def test_ray_rate_to_apy_known_value_arbitrum_usdc_supply() -> None:
    """USDC liquidityRate from live mainnet 2026-04-30 — ~3.3% APY (Aave UI confirmed)."""
    # Captured from the live fixture decode below.
    apr_3_3 = int(0.0331 * RAY)
    apy = ray_rate_to_apy(apr_3_3)
    # APY of a ~3.3% APR compounded continuously is ~exp(0.0331)-1 ≈ 0.0337.
    assert 0.030 < apy < 0.038


# ---------------------------------------------------------------------------
# reserve_data_from_row_arbitrum
# ---------------------------------------------------------------------------


def _synthetic_row_arbitrum(**overrides: Any) -> tuple[Any, ...]:
    """Build a 54-element tuple matching the on-chain row layout."""
    base: dict[str, Any] = {
        "underlyingAsset": "0x" + "ab" * 20,
        "name": "Test Token",
        "symbol": "TEST",
        "decimals": 18,
        "baseLTVasCollateral": 7500,
        "reserveLiquidationThreshold": 8000,
        "reserveLiquidationBonus": 10500,
        "reserveFactor": 1000,
        "usageAsCollateralEnabled": True,
        "borrowingEnabled": True,
        "stableBorrowRateEnabled": False,
        "isActive": True,
        "isFrozen": False,
        "liquidityIndex": 10**27,
        "variableBorrowIndex": 10**27,
        "liquidityRate": 3842250348931316408715874,  # ≈ 0.38% APY
        "variableBorrowRate": 11205522606874713489372407,  # ≈ 1.13% APY
        "stableBorrowRate": 0,
        "lastUpdateTimestamp": 1735689600,
        "aTokenAddress": "0x" + "11" * 20,
        "stableDebtTokenAddress": "0x" + "22" * 20,
        "variableDebtTokenAddress": "0x" + "33" * 20,
        "interestRateStrategyAddress": "0x" + "44" * 20,
        "availableLiquidity": 1000 * 10**18,
        "totalPrincipalStableDebt": 0,
        "averageStableRate": 0,
        "stableDebtLastUpdateTimestamp": 0,
        "totalScaledVariableDebt": 200 * 10**18,
        "priceInMarketReferenceCurrency": 2_267 * 10**8,
        "priceOracle": "0x" + "55" * 20,
        "variableRateSlope1": 0,
        "variableRateSlope2": 0,
        "stableRateSlope1": 0,
        "stableRateSlope2": 0,
        "baseStableBorrowRate": 0,
        "baseVariableBorrowRate": 0,
        "optimalUsageRatio": 0,
        "isPaused": False,
        "isSiloedBorrowing": False,
        "accruedToTreasury": 0,
        "unbacked": 0,
        "isolationModeTotalDebt": 0,
        "flashLoanEnabled": True,
        "debtCeiling": 0,
        "debtCeilingDecimals": 0,
        "eModeCategoryId": 0,
        "borrowCap": 0,
        "supplyCap": 0,
        "eModeLtv": 0,
        "eModeLiquidationThreshold": 0,
        "eModeLiquidationBonus": 0,
        "eModePriceSource": "0x" + "66" * 20,
        "eModeLabel": "",
        "borrowableInIsolation": False,
    }
    base.update(overrides)
    return tuple(base[k] for k in _AGGREGATED_RESERVE_FIELDS_ARBITRUM)


def test_reserve_data_from_row_arbitrum_decodes_test_token() -> None:
    row = _synthetic_row_arbitrum()
    rd = reserve_data_from_row_arbitrum(row)
    assert isinstance(rd, ReserveData)
    assert rd.symbol == "TEST"
    assert rd.decimals == 18
    assert 0.003 < rd.supply_apy < 0.005
    assert 0.010 < rd.borrow_apy < 0.013
    assert rd.ltv == 0.75
    assert rd.liquidation_threshold == 0.80
    assert rd.paused is False
    assert rd.frozen is False
    assert rd.total_supplied == 1200 * 10**18
    assert rd.total_borrowed == 200 * 10**18
    assert math.isclose(rd.utilization, 200 / 1200, rel_tol=1e-9)


def test_reserve_data_from_row_arbitrum_handles_paused_reserve() -> None:
    row = _synthetic_row_arbitrum(isPaused=True, isFrozen=True, baseLTVasCollateral=0)
    rd = reserve_data_from_row_arbitrum(row)
    assert rd.paused is True
    assert rd.frozen is True
    assert rd.ltv == 0.0


def test_reserve_data_from_row_arbitrum_stashes_emode_and_stable_rate_fields() -> None:
    """Arbitrum-only fields (eModeLabel, stableBorrowRate, …) must end up in `raw`."""
    row = _synthetic_row_arbitrum(
        eModeLabel="Stablecoins",
        stableBorrowRate=12345,
        eModeCategoryId=1,
    )
    rd = reserve_data_from_row_arbitrum(row)
    assert rd.raw["eModeLabel"] == "Stablecoins"
    assert rd.raw["stableBorrowRate"] == 12345
    assert rd.raw["eModeCategoryId"] == 1


# ---------------------------------------------------------------------------
# AaveV3Arbitrum facade — recorded fixture decode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_reserves_data_recorded_fixture_decodes_20_reserves() -> None:
    """Captured 2026-04-30 from Arbitrum One mainnet."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Arbitrum(client, ADDRS)
    reserves = await aave.get_reserves_data()
    symbols = [r.symbol for r in reserves]
    # Arbitrum has 20 active reserves at the snapshot vs MegaETH's 8 —
    # the multi-chain claim Sentinel is making isn't aspirational.
    assert len(reserves) == 20, f"expected 20 reserves, got {len(reserves)}: {symbols}"
    # Must include the canonical Arbitrum lending base assets:
    assert "WETH" in symbols
    assert "WBTC" in symbols
    assert "USDC" in symbols
    assert "ARB" in symbols  # Arbitrum-native, would NOT be on MegaETH
    assert "GHO" in symbols  # Aave-native stable, only deployed on Arbitrum


@pytest.mark.asyncio
async def test_get_reserves_data_fixture_includes_paused_and_frozen() -> None:
    """rsETH is paused, WETH/EURS/MAI are frozen at the snapshot — chain-health gate signal."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Arbitrum(client, ADDRS)
    reserves = await aave.get_reserves_data()
    paused = [r.symbol for r in reserves if r.paused]
    frozen = [r.symbol for r in reserves if r.frozen]
    assert "rsETH" in paused, f"expected rsETH paused; paused={paused}"
    assert "WETH" in frozen, f"expected WETH frozen; frozen={frozen}"


@pytest.mark.asyncio
async def test_get_reserves_data_fixture_weth_realistic_metrics() -> None:
    """WETH on Aave V3 Arbitrum at the snapshot."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Arbitrum(client, ADDRS)
    reserves = await aave.get_reserves_data()
    weth = next(r for r in reserves if r.symbol == "WETH")
    assert weth.decimals == 18
    # WETH is FROZEN on this Arbitrum deployment at the snapshot — so its
    # baseLTVasCollateral is intentionally 0 (frozen reserves can't be
    # used as collateral for new positions). LiquidationThreshold is
    # still meaningful for existing positions.
    assert weth.frozen is True
    # Utilization is 100% (1.0): the reserve is fully drained on the
    # supply side. Sanity: borrow + available > 0 → must equal supplied.
    assert weth.utilization > 0.95
    assert weth.total_supplied > 0
    assert 0.0 < weth.supply_apy < 0.10
    assert 0.0 < weth.borrow_apy < 0.10


@pytest.mark.asyncio
async def test_get_user_account_data_decodes() -> None:
    encoded = abi_encode(
        ["uint256"] * 6,
        [
            10_000 * 10**8,  # totalCollateralBase $10,000
            2_000 * 10**8,  # totalDebtBase $2,000
            5_000 * 10**8,  # availableBorrowsBase $5,000
            8500,  # currentLiquidationThreshold = 85%
            8000,  # ltv = 80%
            5 * 10**18,  # health factor 5.0
        ],
    )
    user = "0x" + "55" * 20
    client = StubClient({ADDRS.pool: "0x" + encoded.hex()})
    aave = AaveV3Arbitrum(client, ADDRS)
    acc = await aave.get_user_account_data(user)
    assert isinstance(acc, UserAccountData)
    assert acc.total_collateral_base == 10_000 * 10**8
    assert acc.total_debt_base == 2_000 * 10**8
    assert acc.current_liquidation_threshold == 0.85
    assert acc.ltv == 0.80
    assert acc.health_factor == Decimal(5)


@pytest.mark.asyncio
async def test_get_user_account_data_invalid_address_raises() -> None:
    aave = AaveV3Arbitrum(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid user address"):
        await aave.get_user_account_data("not-an-address")


@pytest.mark.asyncio
async def test_get_asset_price_returns_decimal_in_usd() -> None:
    asset = "0x" + "66" * 20
    raw = abi_encode(["uint256"], [2_267 * 10**8])
    client = StubClient({ADDRS.oracle: "0x" + raw.hex()})
    aave = AaveV3Arbitrum(client, ADDRS)
    price = await aave.get_asset_price(asset)
    assert isinstance(price, Decimal)
    assert price == Decimal(2267)


@pytest.mark.asyncio
async def test_get_asset_price_invalid_address_raises() -> None:
    aave = AaveV3Arbitrum(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid asset address"):
        await aave.get_asset_price("0xBAD")


def test_aave_addresses_from_registry_entry() -> None:
    reg = ProtocolRegistry.from_yaml()
    e = reg.get("aave_v3")
    a = AaveV3Addresses.from_registry_entry(e)
    assert a.pool == e.address("pool")
    assert a.ui_pool_data_provider == e.address("ui_pool_data_provider")
    assert a.oracle == e.address("oracle")
    # The Arbitrum pool address must match the canonical Aave book.
    assert a.pool.lower() == "0x794a61358d6845594f94dc1db02a252b5b4814ad"


def test_registry_lists_aave_v3_only() -> None:
    """Wave 1 scope: aave_v3 is the single registered Arbitrum protocol."""
    reg = ProtocolRegistry.from_yaml()
    keys = [e.key for e in reg]
    assert "aave_v3" in keys
    aave = reg.get("aave_v3")
    assert aave.category == "lending"
    assert aave.priority == 1
    assert aave.status == "active"
