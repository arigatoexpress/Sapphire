"""Exercise the README's 3-line usage example with mocked chain reads.

The README claims:

    from sentinel_gate import default_gate
    gate = default_gate()
    verdict = gate.evaluate_chain(4326)  # MegaETH
    if verdict.severity == "BLOCK": refuse_trade()

This test runs that exact shape against an injected mock factory so
we don't hit a live RPC during ``pytest``. The point is: if a user
copies the README snippet into their own code (with their own client
factory), the API surface they see matches what the README promises.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from sentinel_gate import (
    MEGAETH_CHAIN_ID,
    ChainHealthGate,
    ChainHealthVerdict,
    PegBreak,
)


def _peg_snapshot(divergence_bps: int) -> SimpleNamespace:
    return SimpleNamespace(divergence_bps=Decimal(divergence_bps))


def _stable(severity: PegBreak, divergence_bps: int) -> SimpleNamespace:
    return SimpleNamespace(
        severity=severity,
        peg_snapshot=_peg_snapshot(divergence_bps),
    )


def _reserve(symbol: str, paused: bool = False, frozen: bool = False, utilization: float = 0.5):
    return SimpleNamespace(symbol=symbol, paused=paused, frozen=frozen, utilization=utilization)


def _lend(reserves: list) -> SimpleNamespace:
    return SimpleNamespace(reserves=reserves)


class _MockMegaETHClient:
    """Duck-typed MegaETHProtocols stand-in. Pre-opened (no async-CM)."""

    def __init__(self, stable, lend):
        self._stable = stable
        self._lend = lend

    async def stable_health(self):
        return self._stable

    async def lend_overview(self):
        return self._lend


def test_readme_three_line_example_returns_verdict_object():
    """The 3-line README usage returns a `ChainHealthVerdict` with the documented fields."""
    stable = _stable(PegBreak.HEALTHY, 8)
    lend = _lend([_reserve("USDC", utilization=0.5), _reserve("WETH", utilization=0.3)])

    def factory():
        return _MockMegaETHClient(stable=stable, lend=lend)

    gate = ChainHealthGate(client_factory=factory)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert isinstance(verdict, ChainHealthVerdict)
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == MEGAETH_CHAIN_ID
    assert verdict.chain_name == "MegaETH"
    assert verdict.peg_divergence_bps == Decimal(8)
    assert verdict.aave_paused_reserves == []
    assert len(verdict.reasons) >= 1


def test_readme_block_branch_fires_on_severe_depeg():
    """`if verdict.severity == "BLOCK": refuse_trade()` branch is reachable."""
    stable = _stable(PegBreak.BREAK_100BP, 137)
    lend = _lend([_reserve("USDC", utilization=0.5)])

    def factory():
        return _MockMegaETHClient(stable=stable, lend=lend)

    gate = ChainHealthGate(client_factory=factory)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert any("USDM depegging" in r for r in verdict.reasons)
    assert verdict.peg_divergence_bps == Decimal(137)


def test_warning_severity_does_not_block():
    """Warning is surface-only — README says only BLOCK should refuse trades."""
    stable = _stable(PegBreak.WARNING_50BP, 60)
    lend = _lend([_reserve("USDC")])

    def factory():
        return _MockMegaETHClient(stable=stable, lend=lend)

    gate = ChainHealthGate(client_factory=factory)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "WARNING"
    # The README's `if verdict.severity == "BLOCK"` branch must NOT fire here.
    assert verdict.severity != "BLOCK"


def test_paused_high_utilization_reserve_blocks():
    """A paused reserve with >80% utilization is the canonical Aave BLOCK signal."""
    stable = _stable(PegBreak.HEALTHY, 8)
    lend = _lend(
        [
            _reserve("USDC", paused=True, utilization=0.85),  # >80% -> BLOCK
            _reserve("WETH", utilization=0.3),
        ]
    )

    def factory():
        return _MockMegaETHClient(stable=stable, lend=lend)

    gate = ChainHealthGate(client_factory=factory)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert any("paused with high utilization" in r for r in verdict.reasons)


def test_fail_open_returns_healthy_when_client_factory_raises():
    """allow_when_unavailable=True (default): RPC failure -> HEALTHY, not BLOCK."""

    def broken_factory():
        raise ConnectionError("simulated RPC outage")

    gate = ChainHealthGate(client_factory=broken_factory, allow_when_unavailable=True)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "HEALTHY"
    assert any("rpc error" in r.lower() for r in verdict.reasons)


def test_fail_closed_returns_block_when_client_factory_raises():
    """allow_when_unavailable=False: paranoid mode refuses payments on RPC outage."""

    def broken_factory():
        raise ConnectionError("simulated RPC outage")

    gate = ChainHealthGate(client_factory=broken_factory, allow_when_unavailable=False)
    verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert any("fail-closed" in r for r in verdict.reasons)
