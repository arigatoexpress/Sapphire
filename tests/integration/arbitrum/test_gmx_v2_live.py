"""Live mainnet integration tests for the GMX V2 read path on Arbitrum One.

Skipped by default. Set ``SAPPHIRE_ARBITRUM_INTEGRATION=1`` to enable.

Two tests, both gated:

1. ``test_perps_overview_against_live_arbitrum_mainnet``
   — Hits Reader/DataStore via ArbitrumProtocols.perps_overview().
   Asserts >= 5 markets returned, that some are priced (Aave coverage),
   that funding APRs are in plausible range.

2. ``test_chain_health_with_perps_against_live_arbitrum_mainnet``
   — Composes the full evaluator (lend + perps tier) against live
   Arbitrum mainnet and asserts a verdict comes back without raising.

Failure modes that should surface here:
  * GMX deploys a new Reader and our pinned ABI drifts.
  * The Reader changes its return tuple shape.
  * Aave oracle drops feeds for tokens we expect to have prices for.
  * DataStore moves and our pinned address becomes stale.
"""

from __future__ import annotations

import os
from decimal import Decimal

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
async def test_perps_overview_against_live_arbitrum_mainnet() -> None:
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
        overview = await proto.perps_overview(max_markets=50)

    # Arbitrum's flagship GMX deployment has ≥30 markets as of 2026-04-30.
    # Use ≥5 as a generous floor that'll catch only catastrophic regressions.
    assert overview.market_count >= 5, (
        f"GMX V2 on Arbitrum should expose ≥5 markets, got {overview.market_count}"
    )

    # At least some should be priced — if Aave loses every overlapping
    # feed at once we have a much bigger problem than this test.
    assert overview.priced_count >= 1, (
        f"expected ≥1 priced market on live mainnet, got {overview.priced_count}; "
        f"unpriced={overview.unpriced_count}"
    )

    # Sanity check funding APRs across priced markets — bound it loose
    # enough to tolerate liquidation cascades (which routinely drive
    # specific markets to several hundred percent APR) but tight enough
    # to catch a wrong-by-1e22 decoder.
    for state in overview.markets:
        if state.state != "ok" or state.funding_apr is None:
            continue
        assert abs(state.funding_apr) < Decimal("100"), (
            f"{state.market.name} funding APR out of plausible range: {state.funding_apr}"
        )


@pytest.mark.asyncio
async def test_chain_health_with_perps_against_live_arbitrum_mainnet() -> None:
    """End-to-end: lend + perps tier composed against live mainnet."""
    from lib.chains.arbitrum.client import ArbitrumClient, ArbitrumConfig
    from lib.hackathon.arbitrum_chain_health import evaluate_arbitrum_chain_health

    cfg = ArbitrumConfig(
        http_rpc=os.getenv("SAPPHIRE_ARBITRUM_RPC_URL") or "https://arb1.arbitrum.io/rpc",
        chain_id=42161,
    )
    async with ArbitrumClient(cfg) as client:
        verdict = await evaluate_arbitrum_chain_health(client, include_perps=True)

    assert verdict.chain_id == 42161
    assert verdict.severity in ("HEALTHY", "WARNING", "BLOCK")
    assert verdict.reasons, "verdict.reasons should never be empty"
