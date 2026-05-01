"""Smoke tests for the MegaETH integration.

The whole module is gated by ``SAPPHIRE_MEGAETH_INTEGRATION=1`` (see
``conftest.py``). When the gate is open these tests touch the live testnet
RPC; when it is closed they are skipped at collection time.
"""

from __future__ import annotations

import pytest


@pytest.mark.megaeth_integration
def test_chain_id_is_positive(megaeth_chain_id: int) -> None:
    """``eth_chainId`` returns a positive integer.

    This is the trivial round-trip: it verifies the configured RPC is
    reachable, returns valid JSON-RPC, and decodes to a non-zero chain ID.
    Specific chain-ID assertions live in chain-pinned tests under the
    executor lane (which owns the ``MEGAETH_TESTNET_CHAIN_ID`` constant).
    """

    assert isinstance(megaeth_chain_id, int)
    assert megaeth_chain_id > 0, "expected non-zero chain id from MegaETH testnet"
