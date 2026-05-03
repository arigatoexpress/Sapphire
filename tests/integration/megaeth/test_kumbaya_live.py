"""Live mainnet integration test for the Kumbaya read path (Wave B step 1).

Skipped by default. Set ``SAPPHIRE_MEGAETH_INTEGRATION=1`` to enable.

What this exercises end-to-end:
  * RPC connectivity to https://mainnet.megaeth.com/rpc
  * Factory.getPool decoding (existing pool case)
  * QuoterV2.quoteExactInputSingle decoding — the stateMutability:nonpayable
    footgun. eth_call should still work.
  * UniswapV3Pool.slot0 + liquidity + fee on a real CREATE2 pool clone.
  * MegaETHProtocols.quote_swap composition through the dex_router.

Failure modes that should surface here:
  * Kumbaya redeploys with a new factory or quoter — registry yaml drift.
  * The pool we probe is migrated / deprecated / drained.
  * The Pool ABI workaround drifts (UniV3 forks rarely change pool ABI
    but it's worth catching).
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


WETH = "0x4200000000000000000000000000000000000006"
USDM = "0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7"


def _build_megaeth_client():
    """Same client-resolution shim as the Aave V3 live test."""
    import importlib.util
    import pathlib

    candidate_files = [
        pathlib.Path("plugins/claw-sapphire/tools/internal/megaeth.py"),
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
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.MegaETHClient, module.MegaETHConfig
    pytest.skip(
        "MegaETHClient not available; PR #529 (feat/megaeth-rpc-tool) "
        "must be merged or its branch checked out for live integration."
    )


@pytest.mark.asyncio
async def test_quote_swap_weth_to_usdm_against_live_mainnet() -> None:
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.protocols import MegaETHProtocols
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        cid = await client.chain_id()
        assert cid == 4326, f"expected MegaETH mainnet (4326), got {cid}"

        proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
        # 1 WETH = 1e18 raw units.
        quote = await proto.quote_swap(WETH, USDM, 10**18)

    assert quote is not None, "Kumbaya should have a WETH/USDM pool"
    assert quote.venue == "kumbaya"
    assert quote.amount_out > 0, "amount_out should be > 0 for a known liquid pair"
    # Both tokens are 18-decimal — amount_out / 1e18 = USDM per 1 WETH.
    # WETH/USDM should be in [$500, $20,000] range; we use a generous band.
    human_price = quote.amount_out / 10**18
    assert 500 < human_price < 20_000, f"WETH/USDM price out of plausible range: {human_price}"
    assert quote.fee_pips in (100, 500, 3000, 10000), f"unexpected fee_pips: {quote.fee_pips}"
    assert quote.gas_estimate > 0
    assert quote.raw is not None
    assert quote.raw.sqrt_price_x96_after > 0


@pytest.mark.asyncio
async def test_pool_state_for_weth_usdm_3000_returns_live_data() -> None:
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.contracts.kumbaya import Kumbaya, KumbayaAddresses
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        reg = ProtocolRegistry.from_yaml()
        kb = Kumbaya(client, KumbayaAddresses.from_registry_entry(reg.get("kumbaya")))
        pool = await kb.get_pool(WETH, USDM, 3000)
        assert pool != "0x" + "0" * 40, "WETH/USDM @ 0.3% should exist"
        state = await kb.pool_state(pool)

    assert state.fee_pips == 3000
    assert state.sqrt_price_x96 > 0
    assert state.liquidity > 0, "WETH/USDM @ 0.3% should have non-zero in-range liquidity"
    assert state.unlocked is True
    # Both 18-decimal tokens → raw and human prices match.
    p = float(state.price_token1_per_token0())
    assert 500 < p < 20_000, f"price out of plausible range: {p}"
