"""Tests for the Aave V3 typed wrapper on Optimism mainnet.

Uses a recorded ``getReservesData`` response captured from Optimism
mainnet on 2026-05-02 (file:
``fixtures/aave_v3/getReservesData_response.hex``) to exercise the full
decode path without network.

Field schema is the same 54-field layout as Arbitrum (both deployments
predate Aave's stable-rate removal upgrade), and a regression test pins
the field-tuple equality so a future Arbitrum-side refactor that touches
the layout shows up here too.
"""

from __future__ import annotations

import math
import os
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from eth_abi import encode as abi_encode

from lib.chains.arbitrum.contracts.aave_v3 import (
    _AGGREGATED_RESERVE_FIELDS_ARBITRUM,
)
from lib.chains.optimism.contracts.aave_v3 import (
    _AGGREGATED_RESERVE_FIELDS_OPTIMISM,
    BPS_DENOMINATOR,
    RAY,
    SECONDS_PER_YEAR,
    AaveV3Addresses,
    AaveV3Optimism,
    ReserveData,
    UserAccountData,
    ray_rate_to_apy,
    reserve_data_from_row_optimism,
)
from lib.chains.optimism.registry import ProtocolRegistry

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "aave_v3" / "getReservesData_response.hex"

ADDRS = AaveV3Addresses(
    pool="0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    pool_addresses_provider="0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
    oracle="0xD81eb3728a631871a7eBBaD631b5f424909f0c77",
    ui_pool_data_provider="0xbd83DdBE37fc91923d59C8c1E0bDe0CccCa332d5",
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
# Constants + helper sanity (re-asserted vs. the megaeth/arbitrum sides
# so a drift of any chain's package raises a regression here too).
# ---------------------------------------------------------------------------


def test_constants_are_aave_canonical() -> None:
    assert RAY == 10**27
    assert SECONDS_PER_YEAR == 31_536_000
    assert BPS_DENOMINATOR == 10_000


def test_optimism_field_schema_has_54_fields() -> None:
    """Schema is fixed at 54 — Aave V3 Optimism hasn't dropped stableBorrowRate."""
    assert len(_AGGREGATED_RESERVE_FIELDS_OPTIMISM) == 54
    # Spot-check a few load-bearing field names + positions.
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM[0] == "underlyingAsset"
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM[2] == "symbol"
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM[15] == "liquidityRate"
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM[16] == "variableBorrowRate"
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM[37] == "isPaused"
    # Stable-rate fields the MegaETH layout dropped:
    assert "stableBorrowRate" in _AGGREGATED_RESERVE_FIELDS_OPTIMISM
    assert "stableDebtTokenAddress" in _AGGREGATED_RESERVE_FIELDS_OPTIMISM


def test_optimism_field_schema_matches_arbitrum() -> None:
    """Pinned sync: Optimism + Arbitrum row schemas must match exactly.

    Both deployments predate Aave's stable-rate-removal upgrade. If this
    ever drifts, the live fixture decode below will silently break — so
    we pin equality here to surface the drift early.
    """
    assert _AGGREGATED_RESERVE_FIELDS_OPTIMISM == _AGGREGATED_RESERVE_FIELDS_ARBITRUM


def test_ray_rate_to_apy_known_value_optimism_usdt_supply() -> None:
    """USDT liquidityRate from live mainnet 2026-05-02 — ~3.0% APY."""
    apr_3_0 = int(0.0299 * RAY)
    apy = ray_rate_to_apy(apr_3_0)
    # APY of a ~3.0% APR compounded continuously is ~exp(0.0299)-1 ≈ 0.0303.
    assert 0.027 < apy < 0.034


# ---------------------------------------------------------------------------
# reserve_data_from_row_optimism
# ---------------------------------------------------------------------------


def _synthetic_row_optimism(**overrides: Any) -> tuple[Any, ...]:
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
    return tuple(base[k] for k in _AGGREGATED_RESERVE_FIELDS_OPTIMISM)


def test_reserve_data_from_row_optimism_decodes_test_token() -> None:
    row = _synthetic_row_optimism()
    rd = reserve_data_from_row_optimism(row)
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


def test_reserve_data_from_row_optimism_handles_paused_reserve() -> None:
    row = _synthetic_row_optimism(isPaused=True, isFrozen=True, baseLTVasCollateral=0)
    rd = reserve_data_from_row_optimism(row)
    assert rd.paused is True
    assert rd.frozen is True
    assert rd.ltv == 0.0


def test_reserve_data_from_row_optimism_stashes_emode_and_stable_rate_fields() -> None:
    """Optimism-only fields (eModeLabel, stableBorrowRate, …) must end up in `raw`."""
    row = _synthetic_row_optimism(
        eModeLabel="Stablecoins",
        stableBorrowRate=12345,
        eModeCategoryId=1,
    )
    rd = reserve_data_from_row_optimism(row)
    assert rd.raw["eModeLabel"] == "Stablecoins"
    assert rd.raw["stableBorrowRate"] == 12345
    assert rd.raw["eModeCategoryId"] == 1


# ---------------------------------------------------------------------------
# AaveV3Optimism facade — recorded fixture decode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_reserves_data_recorded_fixture_decodes_14_reserves() -> None:
    """Captured 2026-05-02 from Optimism mainnet."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Optimism(client, ADDRS)
    reserves = await aave.get_reserves_data()
    symbols = [r.symbol for r in reserves]
    # Optimism has 14 active reserves at the snapshot vs Arbitrum's 20
    # and MegaETH's 8 — the multi-chain claim Sentinel is making isn't
    # aspirational.
    assert len(reserves) == 14, f"expected 14 reserves, got {len(reserves)}: {symbols}"
    # Must include the canonical Optimism lending base assets:
    assert "WETH" in symbols
    assert "WBTC" in symbols
    assert "USDC" in symbols
    assert "OP" in symbols  # Optimism-native, would NOT be on Arbitrum
    assert "sUSD" in symbols  # Synthetix USD — Optimism's native stable
    # USDC + USDC.e (bridged) coexist on Optimism, hence two USDC entries
    # in symbols (the second one is the bridged Circle USDC.e).
    assert symbols.count("USDC") == 2


@pytest.mark.asyncio
async def test_get_reserves_data_fixture_includes_frozen() -> None:
    """MAI is frozen on Optimism at the snapshot — chain-health gate signal."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Optimism(client, ADDRS)
    reserves = await aave.get_reserves_data()
    frozen = [r.symbol for r in reserves if r.frozen]
    assert "MAI" in frozen, f"expected MAI frozen; frozen={frozen}"


@pytest.mark.asyncio
async def test_get_reserves_data_fixture_op_realistic_metrics() -> None:
    """OP token on Aave V3 Optimism at the snapshot."""
    if not FIXTURE.exists():
        pytest.skip(f"fixture missing: {FIXTURE}")
    raw_hex = FIXTURE.read_text().strip()
    client = StubClient({ADDRS.ui_pool_data_provider: raw_hex})
    aave = AaveV3Optimism(client, ADDRS)
    reserves = await aave.get_reserves_data()
    op = next(r for r in reserves if r.symbol == "OP")
    assert op.decimals == 18
    # OP is active on this Optimism deployment at the snapshot.
    assert op.frozen is False
    assert op.paused is False
    # Sanity: APYs are non-negative and bounded.
    assert op.supply_apy >= 0.0
    assert op.borrow_apy >= 0.0
    assert op.borrow_apy < 1.0  # not in a death-spiral
    # OP has very low utilization (~8% at snapshot — supply >> borrow).
    assert op.total_supplied > 0
    assert op.utilization < 0.5


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
    aave = AaveV3Optimism(client, ADDRS)
    acc = await aave.get_user_account_data(user)
    assert isinstance(acc, UserAccountData)
    assert acc.total_collateral_base == 10_000 * 10**8
    assert acc.total_debt_base == 2_000 * 10**8
    assert acc.current_liquidation_threshold == 0.85
    assert acc.ltv == 0.80
    assert acc.health_factor == Decimal(5)


@pytest.mark.asyncio
async def test_get_user_account_data_invalid_address_raises() -> None:
    aave = AaveV3Optimism(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid user address"):
        await aave.get_user_account_data("not-an-address")


@pytest.mark.asyncio
async def test_get_asset_price_returns_decimal_in_usd() -> None:
    asset = "0x" + "66" * 20
    raw = abi_encode(["uint256"], [2_267 * 10**8])
    client = StubClient({ADDRS.oracle: "0x" + raw.hex()})
    aave = AaveV3Optimism(client, ADDRS)
    price = await aave.get_asset_price(asset)
    assert isinstance(price, Decimal)
    assert price == Decimal(2267)


@pytest.mark.asyncio
async def test_get_asset_price_invalid_address_raises() -> None:
    aave = AaveV3Optimism(StubClient({}), ADDRS)
    with pytest.raises(ValueError, match="invalid asset address"):
        await aave.get_asset_price("0xBAD")


def test_aave_addresses_from_registry_entry() -> None:
    reg = ProtocolRegistry.from_yaml()
    e = reg.get("aave_v3")
    a = AaveV3Addresses.from_registry_entry(e)
    assert a.pool == e.address("pool")
    assert a.ui_pool_data_provider == e.address("ui_pool_data_provider")
    assert a.oracle == e.address("oracle")
    # The Optimism pool address must match the canonical Aave book.
    assert a.pool.lower() == "0x794a61358d6845594f94dc1db02a252b5b4814ad"
    # And the Optimism-specific UiPoolDataProvider:
    assert a.ui_pool_data_provider.lower() == "0xbd83ddbe37fc91923d59c8c1e0bde0cccca332d5"


def test_registry_lists_aave_v3_only() -> None:
    """Wave 1 scope: aave_v3 is the single registered Optimism protocol."""
    reg = ProtocolRegistry.from_yaml()
    keys = [e.key for e in reg]
    assert "aave_v3" in keys
    aave = reg.get("aave_v3")
    assert aave.category == "lending"
    assert aave.priority == 1
    assert aave.status == "active"


# ---------------------------------------------------------------------------
# Live integration test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_OPTIMISM_INTEGRATION") != "1",
    reason="set SAPPHIRE_OPTIMISM_INTEGRATION=1 to run live RPC test",
)
async def test_live_lend_overview_returns_real_reserves() -> None:
    """Live: fetch lend_overview() against Optimism mainnet.

    Asserts the deployment is meaningful (>=3 reserves and >$100M
    supplied — Optimism's Aave is much larger than MegaETH's). Network
    flake => skip via the env gate; this is not run in CI.
    """
    from lib.chains.optimism.client import OptimismClient
    from lib.chains.optimism.protocols import OptimismProtocols

    async with OptimismClient() as client:
        proto = OptimismProtocols(client)
        overview = await proto.lend_overview()
    assert overview.reserve_count >= 3
    assert overview.total_supplied_usd > Decimal(100_000_000)
