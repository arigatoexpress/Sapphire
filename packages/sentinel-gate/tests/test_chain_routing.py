"""Verify the dispatcher routes chain ids to the right evaluator.

* 4326 (MegaETH) -> MegaETH classifier
* 42161 (Arbitrum) -> Arbitrum classifier (Aave V3 only, no peg axis)
* 10 (Optimism) -> not registered -> HEALTHY / "chain not gated"
* 8453 (Base, hypothetical) -> not registered -> HEALTHY / "chain not gated"
* register_chain() -> custom chain becomes routable
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sentinel_gate import (
    ARBITRUM_CHAIN_ID,
    MEGAETH_CHAIN_ID,
    OPTIMISM_CHAIN_ID,
    ChainHealthGate,
    ChainHealthVerdict,
    PegBreak,
    register_chain,
    supported_chains,
)


def _reserve(symbol: str, paused: bool = False, frozen: bool = False, utilization: float = 0.5):
    return SimpleNamespace(symbol=symbol, paused=paused, frozen=frozen, utilization=utilization)


class _MockMultiChainClient:
    """Duck-typed client exposing both MegaETH + Arbitrum surfaces."""

    def __init__(self, stable=None, lend=None):
        self._stable = stable
        self._lend = lend

    async def stable_health(self):
        return self._stable

    async def lend_overview(self):
        return self._lend


def test_supported_chains_includes_megaeth_and_arbitrum():
    """`supported_chains()` is the introspection API users should rely on."""
    chains = supported_chains()
    assert MEGAETH_CHAIN_ID in chains
    assert ARBITRUM_CHAIN_ID in chains
    assert chains[MEGAETH_CHAIN_ID] == "MegaETH"
    assert chains[ARBITRUM_CHAIN_ID] == "Arbitrum One"


def test_optimism_chain_id_falls_through_to_chain_not_gated():
    """Optimism (10) is intentionally not registered -> HEALTHY / 'chain not gated'."""
    gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient())
    verdict = gate.evaluate_chain(OPTIMISM_CHAIN_ID)

    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == OPTIMISM_CHAIN_ID
    assert verdict.chain_name == "Optimism"
    assert verdict.reasons == ["chain not gated"]


def test_unknown_chain_id_falls_through_with_synthetic_name():
    """A chain id we've never heard of returns HEALTHY with chain-<id> name."""
    gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient())
    verdict = gate.evaluate_chain(99999)

    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 99999
    assert verdict.chain_name == "chain-99999"


def test_arbitrum_dispatcher_routes_to_arbitrum_classifier():
    """Chain id 42161 -> Arbitrum classifier (no peg axis, Aave only)."""
    lend = SimpleNamespace(
        reserves=[
            _reserve("USDC", paused=True, utilization=0.85),  # high-util pause -> BLOCK
        ]
    )
    gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient(lend=lend))
    verdict = gate.evaluate_chain(ARBITRUM_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert verdict.chain_id == ARBITRUM_CHAIN_ID
    assert verdict.chain_name == "Arbitrum One"
    # Arbitrum has no USDM, so peg_divergence_bps must be None even when blocking.
    assert verdict.peg_divergence_bps is None
    assert "USDC" in verdict.aave_paused_reserves


def test_arbitrum_healthy_returns_healthy():
    """Arbitrum healthy path — all reserves nominal."""
    lend = SimpleNamespace(
        reserves=[_reserve("USDC", utilization=0.5), _reserve("WETH", utilization=0.3)]
    )
    gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient(lend=lend))
    verdict = gate.evaluate_chain(ARBITRUM_CHAIN_ID)

    assert verdict.severity == "HEALTHY"
    assert verdict.aave_paused_reserves == []


def test_arbitrum_frozen_reserve_warns_but_does_not_block():
    """Frozen != paused — frozen blocks new positions but allows repay/withdraw."""
    lend = SimpleNamespace(
        reserves=[
            _reserve("WBTC", frozen=True, utilization=0.4),
            _reserve("USDC", utilization=0.5),
        ]
    )
    gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient(lend=lend))
    verdict = gate.evaluate_chain(ARBITRUM_CHAIN_ID)

    assert verdict.severity == "WARNING"
    assert any("Aave reserves frozen" in r for r in verdict.reasons)


def test_register_chain_makes_custom_chain_routable():
    """Users can extend the gate without forking the package."""

    async def evaluate_base_chain(client) -> ChainHealthVerdict:
        # In a real impl we'd read chain state. For the routing test
        # we just hardcode a BLOCK verdict so we can verify dispatch
        # actually routed to our function.
        return ChainHealthVerdict(
            chain_id=8453,
            chain_name="Base",
            severity="BLOCK",
            reasons=["custom evaluator fired"],
        )

    register_chain(chain_id=8453, name="Base", evaluator=evaluate_base_chain)

    try:
        gate = ChainHealthGate(client_factory=lambda: _MockMultiChainClient())
        verdict = gate.evaluate_chain(8453)

        assert verdict.severity == "BLOCK"
        assert verdict.chain_name == "Base"
        assert verdict.reasons == ["custom evaluator fired"]
        # And the new chain shows up in `supported_chains()` for introspection.
        assert 8453 in supported_chains()
    finally:
        # Clean up so other tests don't see the registration leak.
        from sentinel_gate._internal.chain_health_gate import _CHAIN_REGISTRY

        _CHAIN_REGISTRY.pop(8453, None)
