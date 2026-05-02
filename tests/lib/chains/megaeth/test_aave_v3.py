"""Tests for the Aave V3 typed wrapper.

Uses a recorded ``getReservesData`` response captured from MegaETH
mainnet on 2026-04-30 (file: ``fixtures/getReservesData_response.hex``)
to exercise the full decode path without network.
"""

from __future__ import annotations

import math
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.megaeth.contracts.aave_v3 import (
    BPS_DENOMINATOR,
    RAY,
    SECONDS_PER_YEAR,
    AaveV3,
    AaveV3Addresses,
    ReserveData,
    UserAccountData,
    ray_rate_to_apy,
    reserve_data_from_row,
)
from lib.chains.megaeth.registry import ProtocolRegistry

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "getReservesData_response.hex"

ADDRS = AaveV3Addresses(
    pool="0x7e324AbC5De01d112AfC03a584966ff199741C28",
    pool_addresses_provider="0x46Dcd5F4600319b02649Fd76B55aA6c1035CA478",
    oracle="0x421117D7319E96d831972b3F7e970bbfe29C4F21",
    ui_pool_data_provider="0x1aB55bBdD5DF0782BBCf73553Af93BC6B29A286B",
    protocol_data_provider="0x9588b453A4EE24a420830CB3302195cA7aA3b403",
)


class StubClient:
    """Returns pre-staged hex responses keyed by 'to' address."""

    def __init__(self, responses: dict[str, str]) -> None:
        # responses keyed by lowercased address
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
# ray_rate_to_apy unit tests — the documented footgun
# ---------------------------------------------------------------------------


def test_ray_rate_to_apy_zero() -> None:
    assert ray_rate_to_apy(0) == 0.0
    assert ray_rate_to_apy(-100) == 0.0


def test_ray_rate_to_apy_known_value_weth_supply() -> None:
    # WETH liquidityRate from live mainnet 2026-04-30 — 0.385% APY (Aave UI confirmed).
    weth_rate = 3842250348931316408715874
    apy = ray_rate_to_apy(weth_rate)
    assert 0.003 < apy < 0.005, f"WETH supply APY out of range: {apy}"


def test_ray_rate_to_apy_known_value_usdt_borrow() -> None:
    # USDT0 variableBorrowRate — should be ~2.9% APY.
    usdt_rate = 28455460445029675069065752
    apy = ray_rate_to_apy(usdt_rate)
    assert 0.025 < apy < 0.035


def test_ray_rate_to_apy_extreme_rate_doesnt_overflow() -> None:
    """Even on a heavily-utilized reserve with APR ~30%, no overflow."""
    apr_30pct_in_ray = int(0.30 * RAY)
    apy = ray_rate_to_apy(apr_30pct_in_ray)
    # APY of a 30% APR compounded continuously is ~exp(0.3) - 1 ≈ 0.3499
    assert 0.34 < apy < 0.36


def test_ray_rate_to_apy_matches_compound_formula() -> None:
    """Sanity: APY = (1 + APR/n)^n - 1 where n = SECONDS_PER_YEAR."""
    apr = 0.05  # 5% APR
    rate_ray = int(apr * RAY)
    expected = (1 + apr / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1
    # rel_tol=1e-7 — float math limit at this magnitude (expm1+log1p path
    # has tiny ULP difference vs **).
    assert math.isclose(ray_rate_to_apy(rate_ray), expected, rel_tol=1e-7)


# ---------------------------------------------------------------------------
# reserve_data_from_row
# ---------------------------------------------------------------------------


def _synthetic_row(**overrides: Any) -> tuple[Any, ...]:
    """Build a 41-element tuple in the schema we expect from getReservesData."""
    base = {
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
        "isActive": True,
        "isFrozen": False,
        "liquidityIndex": 10**27,
        "variableBorrowIndex": 10**27,
        "liquidityRate": 3842250348931316408715874,  # ≈ 0.38% APY
        "variableBorrowRate": 11205522606874713489372407,  # ≈ 1.13% APY
        "lastUpdateTimestamp": 1735689600,
        "aTokenAddress": "0x" + "11" * 20,
        "variableDebtTokenAddress": "0x" + "22" * 20,
        "interestRateStrategyAddress": "0x" + "33" * 20,
        "availableLiquidity": 1000 * 10**18,
        "totalScaledVariableDebt": 200 * 10**18,
        "priceInMarketReferenceCurrency": 2_267 * 10**8,
        "priceOracle": "0x" + "44" * 20,
        "variableRateSlope1": 0,
        "variableRateSlope2": 0,
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
        "borrowCap": 0,
        "supplyCap": 0,
        "borrowableInIsolation": False,
        "virtualAccActive": True,
        "virtualUnderlyingBalance": 0,
    }
    base.update(overrides)
    from lib.chains.megaeth.contracts.aave_v3 import _AGGREGATED_RESERVE_FIELDS

    return tuple(base[k] for k in _AGGREGATED_RESERVE_FIELDS)


def test_reserve_data_from_row_decodes_known_weth_shape() -> None:
    row = _synthetic_row()
    rd = reserve_data_from_row(row)
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
    # utilization = 200 / 1200
    assert math.isclose(rd.utilization, 200 / 1200, rel_tol=1e-9)


def test_reserve_data_from_row_handles_paused_reserve() -> None:
    row = _synthetic_row(isPaused=True, isFrozen=True, baseLTVasCollateral=0)
    rd = reserve_data_from_row(row)
    assert rd.paused is True
    assert rd.frozen is True
    assert rd.ltv == 0.0


def test_reserve_data_from_row_handles_zero_liquidity() -> None:
    row = _synthetic_row(availableLiquidity=0, totalScaledVariableDebt=0, liquidityRate=0)
    rd = reserve_data_from_row(row)
    assert rd.utilization == 0.0
    assert rd.supply_apy == 0.0


# ---------------------------------------------------------------------------
# AaveV3 facade — recorded fixture decode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_reserves_data_recorded_fixture_decodes_8_reserves() -> None:
    """Captured 2026-04-30 from MegaETH mainnet."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3(client, ADDRS)
    reserves = await aave.get_reserves_data()
    symbols = [r.symbol for r in reserves]
    assert len(reserves) == 8, f"expected 8 reserves, got {len(reserves)}: {symbols}"
    assert "WETH" in symbols
    assert "USDm" in symbols
    assert "USDT0" in symbols
    weth = next(r for r in reserves if r.symbol == "WETH")
    # WETH on Aave V3 MegaETH at the snapshot:
    # - 78% LTV, 81% liq-threshold, ~40% utilization, ~0.4% supply / ~1.1% borrow
    assert weth.ltv == 0.78
    assert weth.liquidation_threshold == 0.81
    assert 0.30 < weth.utilization < 0.50
    assert 0.003 < weth.supply_apy < 0.005
    assert 0.010 < weth.borrow_apy < 0.013


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
    aave = AaveV3(client, ADDRS)
    acc = await aave.get_user_account_data(user)
    assert isinstance(acc, UserAccountData)
    assert acc.total_collateral_base == 10_000 * 10**8
    assert acc.total_debt_base == 2_000 * 10**8
    assert acc.available_borrows_base == 5_000 * 10**8
    assert acc.current_liquidation_threshold == 0.85
    assert acc.ltv == 0.80
    assert acc.health_factor == Decimal(5)


@pytest.mark.asyncio
async def test_get_user_account_data_invalid_address_raises() -> None:
    aave = AaveV3(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid user address"):
        await aave.get_user_account_data("not-an-address")


@pytest.mark.asyncio
async def test_get_asset_price_returns_decimal_in_usd() -> None:
    asset = "0x" + "66" * 20
    # Oracle returns $2,267 in BASE_CURRENCY units (USD * 1e8)
    raw = abi_encode(["uint256"], [2_267 * 10**8])
    client = StubClient({ADDRS.oracle: "0x" + raw.hex()})
    aave = AaveV3(client, ADDRS)
    price = await aave.get_asset_price(asset)
    assert isinstance(price, Decimal)
    assert price == Decimal(2267)


@pytest.mark.asyncio
async def test_get_asset_price_invalid_address_raises() -> None:
    aave = AaveV3(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid asset address"):
        await aave.get_asset_price("0xBAD")


def test_aave_addresses_from_registry_entry() -> None:
    reg = ProtocolRegistry.from_yaml()
    e = reg.get("aave_v3")
    a = AaveV3Addresses.from_registry_entry(e)
    assert a.pool == e.address("pool")
    assert a.ui_pool_data_provider == e.address("ui_pool_data_provider")
    assert a.oracle == e.address("oracle")


def test_constants_are_aave_canonical() -> None:
    assert RAY == 10**27
    assert SECONDS_PER_YEAR == 31_536_000
    assert BPS_DENOMINATOR == 10_000
