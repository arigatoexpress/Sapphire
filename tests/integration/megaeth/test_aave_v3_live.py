"""Live mainnet integration test for the Aave V3 read path.

Skipped by default. Set ``SAPPHIRE_MEGAETH_INTEGRATION=1`` to enable.

What this exercises end-to-end:
  * RPC connectivity to https://mainnet.megaeth.com/rpc
  * UiPoolDataProvider.getReservesData decoding
  * AaveOracle.getAssetPrice decoding
  * MegaETHProtocols.lend_overview composition

Failure modes that should surface here:
  * Aave deploys an upgrade and the implementation slot drifts (CI guard
    in Wave B will catch this earlier; this test catches it at runtime).
  * The chain ID changes (it shouldn't — but we assert it == 4326).
  * UiPoolDataProvider is paused / migrated / replaced.
"""

from __future__ import annotations

import os
import sys

import pytest

INTEGRATION_ENABLED = os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet tests",
)


def _build_megaeth_client():
    """Import MegaETHClient from PR #529 path or fall back to a local stub.

    Wave A merges before PR #529's `lib.chains.megaeth.client` lift, so
    this test is graceful: it imports from the plugin tool path that
    PR #529 ships, and skips if that's not present yet (e.g. running
    Wave A in isolation against origin/main).
    """
    import importlib.util
    import pathlib

    candidate_files = [
        pathlib.Path("plugins/claw-sapphire/tools/internal/megaeth.py"),
        # Allow running against PR #529's worktree directly while it's
        # still un-merged. Override via SAPPHIRE_MEGAETH_RPC_TOOL_PATH.
        pathlib.Path(os.getenv("SAPPHIRE_MEGAETH_RPC_TOOL_PATH", "")) / "internal" / "megaeth.py"
        if os.getenv("SAPPHIRE_MEGAETH_RPC_TOOL_PATH")
        else None,
        pathlib.Path(
            "/Users/aribs/Code/Sapphire-megaeth-rpc/plugins/claw-sapphire/tools/internal/megaeth.py"
        ),
    ]
    for p in candidate_files:
        if p is None or not p.exists():
            continue
        spec = importlib.util.spec_from_file_location("_megaeth_rpc_tool", p)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules BEFORE exec so frozen dataclass machinery
        # can resolve __module__ during class creation.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.MegaETHClient, module.MegaETHConfig
    pytest.skip(
        "MegaETHClient not available; PR #529 (feat/megaeth-rpc-tool) "
        "must be merged or its branch checked out for live integration."
    )


@pytest.mark.asyncio
async def test_lend_overview_against_live_mainnet() -> None:
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.protocols import MegaETHProtocols
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        cid = await client.chain_id()
        assert cid == 4326, f"expected MegaETH mainnet (4326), got chain_id={cid}"

        proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
        overview = await proto.lend_overview()

    assert overview.reserve_count >= 1
    assert overview.total_supplied_usd > 0
    # No reserve should produce a NaN/Inf rate now that ray_rate_to_apy is fixed.
    for r in overview.reserves:
        assert -1.0 < r.supply_apy < 5.0, f"{r.symbol} supply_apy out of range: {r.supply_apy}"
        assert -1.0 < r.borrow_apy < 5.0, f"{r.symbol} borrow_apy out of range: {r.borrow_apy}"
        assert 0.0 <= r.utilization <= 1.0


@pytest.mark.asyncio
async def test_oracle_price_for_weth_returns_positive() -> None:
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.protocols import MegaETHProtocols
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
        ov = await proto.lend_overview()
        weth = next((r for r in ov.reserves if r.symbol == "WETH"), None)
        if weth is None:
            pytest.skip("no WETH reserve found on live deployment")
        price = await proto.oracle_price(weth.underlying_asset)

    # ETH should be in [$500, $20,000] for the foreseeable future.
    assert 500 < price < 20_000, f"WETH price out of plausible range: {price}"
