"""Live mainnet integration tests for the USDM read path (Wave B step 2).

Skipped by default. Set ``SAPPHIRE_MEGAETH_INTEGRATION=1`` to enable.

What these tests exercise end-to-end:

* RPC connectivity to ``https://mainnet.megaeth.com/rpc``.
* USDM ERC20 ``totalSupply`` decoding through the LayerZero OFT proxy
  + impl. Asserts > $300M (the protocol map said $360M at TGE day).
* ``peg_quote`` composition across all three sources (Kumbaya 0.01%
  pool + AaveOracle + USDM TWAP60). Asserts spread < 50 bps.
* ``stable_health`` end-to-end composition — peg + circulating supply
  + severity classification + leverage-block decision.

Failure modes that surface here:

* USDM token contract redeploys to a new address — registry yaml drift.
* AaveOracle drops USDM from its feed list.
* The TWAP60 oracle goes stale (updatedAt timestamp very old).
* The peg actually moves > 100 bps (a real depeg event — these tests
  would correctly turn red and need to wait out the event before
  reasserting health).
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

INTEGRATION_ENABLED = os.getenv("SAPPHIRE_MEGAETH_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet tests",
)


def _build_megaeth_client():
    """Same client-resolution shim as the Aave V3 + Kumbaya live tests."""
    import importlib.util
    import pathlib

    candidate_files = [
        pathlib.Path("plugins/claw-sapphire/tools/internal/megaeth.py"),
        (
            pathlib.Path(os.getenv("SAPPHIRE_MEGAETH_RPC_TOOL_PATH", ""))
            / "internal"
            / "megaeth.py"
            if os.getenv("SAPPHIRE_MEGAETH_RPC_TOOL_PATH")
            else None
        ),
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
async def test_usdm_total_supply_live() -> None:
    """USDM total supply on mainnet should be > $300M.

    Live read at TGE day (2026-04-30) was 360,753,853 USDm. We assert
    a generous lower bound so the test stays green through normal
    bridging activity.
    """
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.contracts.usdm import USDM, USDMAddresses
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        cid = await client.chain_id()
        assert cid == 4326, f"expected MegaETH mainnet (4326), got {cid}"

        reg = ProtocolRegistry.from_yaml()
        usdm = USDM(client, USDMAddresses.from_registry_entry(reg.get("usdm")))
        total = await usdm.total_supply()
        symbol = await usdm.symbol()
        decimals = await usdm.decimals()

    assert symbol in ("USDm", "USDM"), f"unexpected symbol: {symbol!r}"
    assert decimals == 18
    assert total > Decimal(300_000_000), (
        f"USDM total supply {total} is below $300M lower bound — has the "
        f"deployment redeployed or has the bridge drained?"
    )


@pytest.mark.asyncio
async def test_usdm_peg_within_50bp() -> None:
    """All three peg sources should agree within 50 bps under normal conditions.

    Live readings at TGE day (2026-04-30):
      AaveOracle: $1.000000   →  0 bps from peg
      TWAP60:     $0.999264   →  7.4 bps from peg
      Kumbaya:    $0.999506   →  4.9 bps from peg
      → max divergence ~7.4 bps. Comfortably HEALTHY.

    Asserting < 50 bps gives us a 6x cushion above the live noise floor
    and is still well below the BREAK_100BP threshold the breaker uses
    for blocking leverage.

    If this assertion fires red, USDM is actually depegging — that's
    a real signal, not a test bug.
    """
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.protocols import MegaETHProtocols
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
        health = await proto.stable_health()

    snap = health.peg_snapshot
    assert snap.sources_present >= 3, (
        f"expected at least 3 of 4 peg sources live, got {snap.sources_present}: "
        f"kumbaya={snap.usdm_kumbaya_usdt0}, aave={snap.usdm_aave_oracle}, "
        f"twap60={snap.usdm_twap60}, eth={snap.usdm_implied_via_eth_oracle}"
    )
    assert snap.divergence_bps < Decimal(50), (
        f"USDM peg divergence {snap.divergence_bps:.2f} bps exceeds 50 bps — "
        f"prices: kumbaya={snap.usdm_kumbaya_usdt0}, "
        f"aave={snap.usdm_aave_oracle}, twap60={snap.usdm_twap60}, "
        f"eth={snap.usdm_implied_via_eth_oracle}"
    )


@pytest.mark.asyncio
async def test_usdm_stable_health_composition_returns_healthy() -> None:
    """End-to-end ``stable_health`` composition against live mainnet.

    Asserts the composed dataclass has the expected shape AND
    classifies HEALTHY at TGE-day spreads. ``is_safe_for_leverage``
    should also return ``(True, "")``.
    """
    MegaETHClient, MegaETHConfig = _build_megaeth_client()

    from lib.chains.megaeth.contracts.peg_monitor import PegBreak
    from lib.chains.megaeth.protocols import MegaETHProtocols
    from lib.chains.megaeth.registry import ProtocolRegistry

    cfg = MegaETHConfig(
        http_rpc=os.getenv("SAPPHIRE_MEGAETH_RPC_URL") or "https://mainnet.megaeth.com/rpc",
        chain_id=4326,
    )
    async with MegaETHClient(cfg) as client:
        proto = MegaETHProtocols(client, registry=ProtocolRegistry.from_yaml())
        health = await proto.stable_health()
        ok, reason = await proto.is_safe_for_leverage()
        severity_only = await proto.peg_status()

    # Shape contract
    assert health.venue == "usdm"
    assert health.collateral_ratio is None  # Off-chain managed; documented.
    assert health.mint_open is None
    assert health.redeem_open is None
    # Live: 360M+ circulating.
    assert health.circulating_supply > Decimal(300_000_000)
    # Severity classification
    assert health.severity == PegBreak.HEALTHY, (
        f"USDM peg classified as {health.severity.name}: {health.block_reason}"
    )
    assert health.should_block_leverage is False
    # peg_status is the cheap version of the same severity.
    assert severity_only == health.severity
    # is_safe_for_leverage is the strategy-facing wrapper.
    assert ok is True
    assert reason == ""
