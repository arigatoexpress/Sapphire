"""Live mainnet integration test for the Aave V3 read path on Arbitrum One.

Skipped by default. Set ``SAPPHIRE_ARBITRUM_INTEGRATION=1`` to enable.

What this exercises end-to-end:
  * RPC connectivity to https://arb1.arbitrum.io/rpc (or override)
  * UiPoolDataProvider.getReservesData decoding (54-field Arbitrum schema)
  * AaveOracle.getAssetPrice decoding
  * ArbitrumProtocols.lend_overview composition

Failure modes that should surface here:
  * Aave deploys an upgrade and the implementation slot drifts.
  * The chain ID changes (it shouldn't — but we assert it == 42161).
  * UiPoolDataProvider is migrated / replaced.
  * Our pinned UiPoolDataProvider ABI drifts from the live deployment.
"""

from __future__ import annotations

import os

import pytest

INTEGRATION_ENABLED = os.getenv("SAPPHIRE_ARBITRUM_INTEGRATION") == "1"
pytestmark = [
    pytest.mark.arbitrum_integration,
    pytest.mark.skipif(
        not INTEGRATION_ENABLED,
        reason="set SAPPHIRE_ARBITRUM_INTEGRATION=1 to run live mainnet tests",
    ),
]


@pytest.mark.asyncio
async def test_lend_overview_against_live_arbitrum_mainnet() -> None:
    from lib.chains.arbitrum.client import ArbitrumClient, ArbitrumConfig
    from lib.chains.arbitrum.protocols import ArbitrumProtocols
    from lib.chains.arbitrum.registry import ProtocolRegistry

    cfg = ArbitrumConfig(
        http_rpc=os.getenv("SAPPHIRE_ARBITRUM_RPC_URL") or "https://arb1.arbitrum.io/rpc",
        chain_id=42161,
    )
    async with ArbitrumClient(cfg) as client:
        cid = await client.chain_id()
        assert cid == 42161, f"expected Arbitrum One (42161), got chain_id={cid}"

        proto = ArbitrumProtocols(client, registry=ProtocolRegistry.from_yaml())
        overview = await proto.lend_overview()

    # Arbitrum has materially more reserves than MegaETH — this is the
    # multi-chain proof point for Sentinel.
    assert overview.reserve_count >= 10, (
        f"Aave V3 on Arbitrum should expose ≥10 reserves, got {overview.reserve_count}"
    )
    assert overview.total_supplied_usd > 100_000_000, (
        f"Aave V3 Arbitrum TVL should be ≥ $100M; got ${overview.total_supplied_usd}"
    )
    for r in overview.reserves:
        assert -1.0 < r.supply_apy < 5.0, f"{r.symbol} supply_apy out of range: {r.supply_apy}"
        assert -1.0 < r.borrow_apy < 5.0, f"{r.symbol} borrow_apy out of range: {r.borrow_apy}"
        assert 0.0 <= r.utilization <= 1.001  # allow rounding above 1.0


@pytest.mark.asyncio
async def test_oracle_price_for_weth_returns_positive() -> None:
    from lib.chains.arbitrum.client import ArbitrumClient, ArbitrumConfig
    from lib.chains.arbitrum.protocols import ArbitrumProtocols
    from lib.chains.arbitrum.registry import ProtocolRegistry

    cfg = ArbitrumConfig(
        http_rpc=os.getenv("SAPPHIRE_ARBITRUM_RPC_URL") or "https://arb1.arbitrum.io/rpc",
        chain_id=42161,
    )
    async with ArbitrumClient(cfg) as client:
        proto = ArbitrumProtocols(client, registry=ProtocolRegistry.from_yaml())
        ov = await proto.lend_overview()
        weth = next((r for r in ov.reserves if r.symbol == "WETH"), None)
        if weth is None:
            pytest.skip("no WETH reserve found on live deployment")
        price = await proto.oracle_price(weth.underlying_asset)

    assert 500 < price < 20_000, f"WETH price out of plausible range: {price}"
