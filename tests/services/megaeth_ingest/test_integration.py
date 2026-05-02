"""Integration tests gated behind SAPPHIRE_MEGAETH_INTEGRATION=1.

These hit the real testnet WSS and require network. Skipped by default.
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live MegaETH integration tests",
)


@pytest.mark.megaeth_integration
@pytest.mark.asyncio
async def test_live_testnet_subscribe_one_block():
    """Subscribe to mainnet/testnet and confirm at least one newHead arrives."""
    from megaeth_ingest.config import load_config
    from megaeth_ingest.forwarder import EventForwarder
    from megaeth_ingest.ws_client import MegaEthWsClient

    cfg = load_config()  # respects SAPPHIRE_MEGAETH_WSS

    class CapturePoster:
        def __init__(self) -> None:
            self.calls: list = []

        async def post_json(self, url: str, payload: dict) -> bool:
            self.calls.append(payload)
            return True

    poster = CapturePoster()
    fwd = EventForwarder(
        poster=poster,
        target_url=cfg.signal_logger_url,
        queue_max=64,
        forwarding_enabled=True,
    )
    client = MegaEthWsClient(config=cfg, forwarder=fwd)
    fwd.paused_provider = client

    await fwd.start()
    try:
        # Run the WS consume loop with a 30s ceiling.
        try:
            await asyncio.wait_for(client._connect_and_consume(), timeout=30.0)
        except asyncio.TimeoutError:
            pass
        await fwd.drain(timeout=2.0)
    finally:
        await fwd.stop()

    assert client.stats.new_heads_received > 0, "no newHeads received from MegaETH testnet"
    assert client.stats.last_block_number is not None
