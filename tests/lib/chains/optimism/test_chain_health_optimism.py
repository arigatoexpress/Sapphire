"""Unit tests for the Optimism branch of the Sentinel chain-health gate.

The dispatcher (``lib/hackathon/chain_health_gate.py``) carries the
multi-chain routing; this module is the chain-specific classifier for
Optimism mainnet (chain id 10). Tests here pin the classifier's severity
rules + the dispatcher's chain id 10 routing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

import pytest

from lib.hackathon.chain_health_gate import (
    OPTIMISM_CHAIN_ID as DISPATCHER_OP_ID,
)
from lib.hackathon.chain_health_gate import (
    SUPPORTED_CHAIN_IDS,
    ChainHealthGate,
    ChainHealthVerdict,
)
from lib.hackathon.optimism_chain_health import (
    HIGH_UTILIZATION_BLOCK_THRESHOLD,
    OPTIMISM_CHAIN_ID,
    classify_optimism,
    evaluate_optimism_chain_health,
)


@dataclass
class _StubReserve:
    symbol: str
    paused: bool = False
    frozen: bool = False
    utilization: float = 0.0


@dataclass
class _StubOverview:
    reserves: list[_StubReserve]


# ---------------------------------------------------------------------------
# Constants pin
# ---------------------------------------------------------------------------


def test_optimism_chain_id_is_10() -> None:
    """Pinned because every consumer keys behaviour on this constant."""
    assert OPTIMISM_CHAIN_ID == 10
    assert DISPATCHER_OP_ID == 10
    assert 10 in SUPPORTED_CHAIN_IDS


def test_optimism_threshold_constant_is_80_percent() -> None:
    """Pinned: changing this changes Sentinel's payment-refusal posture."""
    assert HIGH_UTILIZATION_BLOCK_THRESHOLD == 0.80


# ---------------------------------------------------------------------------
# Pure classifier
# ---------------------------------------------------------------------------


def test_classify_optimism_healthy_when_all_reserves_nominal() -> None:
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", utilization=0.5),
            _StubReserve(symbol="USDC", utilization=0.7),
            _StubReserve(symbol="OP", utilization=0.1),
        ]
    )
    verdict = classify_optimism(overview)
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 10
    assert verdict.chain_name == "Optimism"
    assert verdict.aave_paused_reserves == []
    assert verdict.aave_frozen_reserves == []
    assert verdict.reasons and "nominal" in verdict.reasons[0]


def test_classify_optimism_warning_on_frozen_reserve() -> None:
    """Frozen reserves block new positions but allow repayment — WARNING, not BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="MAI", frozen=True, utilization=0.25),
            _StubReserve(symbol="USDC", utilization=0.7),
        ]
    )
    verdict = classify_optimism(overview)
    assert verdict.severity == "WARNING"
    assert verdict.aave_frozen_reserves == ["MAI"]
    assert verdict.aave_paused_reserves == []
    assert any("frozen" in r for r in verdict.reasons)


def test_classify_optimism_block_on_paused_high_utilization() -> None:
    """Paused + high-util means existing borrowers can't be liquidated — BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="OP", utilization=0.5),
        ]
    )
    verdict = classify_optimism(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert any("paused with high utilization" in r for r in verdict.reasons)


def test_classify_optimism_block_takes_precedence_over_warning() -> None:
    """Coexisting frozen + paused-high-util must resolve to BLOCK, not WARNING."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="MAI", frozen=True, utilization=0.25),
        ]
    )
    verdict = classify_optimism(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert "MAI" in verdict.aave_frozen_reserves


def test_classify_optimism_threshold_boundary_is_strict() -> None:
    """Exactly-80% utilization paused does NOT BLOCK (strict greater-than)."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="USDC", paused=True, utilization=0.80)]
    )
    verdict = classify_optimism(overview)
    # paused-but-not-high-util => HEALTHY (no frozen present either)
    assert verdict.severity == "HEALTHY"


# ---------------------------------------------------------------------------
# evaluate_optimism_chain_health composition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_optimism_uses_optimism_protocols(monkeypatch: pytest.MonkeyPatch) -> None:
    """Composition path: evaluate_optimism_chain_health pulls OptimismProtocols.lend_overview."""
    captured: dict[str, object] = {}

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        async def lend_overview(self) -> _StubOverview:
            return _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.4)])

    import lib.chains.optimism.protocols as proto_module

    monkeypatch.setattr(proto_module, "OptimismProtocols", FakeProtocols)

    fake_client = object()
    verdict = await evaluate_optimism_chain_health(fake_client)
    assert captured["client"] is fake_client
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 10


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_routes_chain_id_10_to_optimism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ChainHealthGate.evaluate_chain(10, client=...) routes to optimism evaluator."""

    async def fake_optimism(client: object) -> object:
        from lib.hackathon.optimism_chain_health import OptimismChainHealthVerdict

        return OptimismChainHealthVerdict(
            chain_id=10,
            chain_name="Optimism",
            severity="HEALTHY",
            reasons=["test stub OK"],
        )

    import lib.hackathon.chain_health_gate as gate_module

    monkeypatch.setattr(gate_module, "evaluate_optimism_chain_health", fake_optimism)

    gate = ChainHealthGate()
    verdict = await gate.evaluate_chain(10, client=object())
    assert isinstance(verdict, ChainHealthVerdict)
    assert verdict.chain_id == 10
    assert verdict.chain_name == "Optimism"
    assert verdict.severity == "HEALTHY"
    assert verdict.reasons == ["test stub OK"]


@pytest.mark.asyncio
async def test_dispatcher_unknown_chain_id_returns_unknown_verdict() -> None:
    """Unsupported chain id => severity=UNKNOWN, doesn't raise."""
    gate = ChainHealthGate()
    verdict = await gate.evaluate_chain(99999, client=object())
    assert verdict.severity == "UNKNOWN"
    assert verdict.chain_id == 99999
    assert any("not registered" in r for r in verdict.reasons)


@pytest.mark.asyncio
async def test_dispatcher_routes_chain_id_42161_to_arbitrum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: adding Optimism didn't break the existing Arbitrum route."""

    async def fake_arbitrum(client: object) -> object:
        from lib.hackathon.arbitrum_chain_health import ArbitrumChainHealthVerdict

        return ArbitrumChainHealthVerdict(
            chain_id=42161,
            chain_name="Arbitrum One",
            severity="WARNING",
            reasons=["test arb stub"],
            aave_frozen_reserves=["WETH"],
        )

    import lib.hackathon.chain_health_gate as gate_module

    monkeypatch.setattr(gate_module, "evaluate_arbitrum_chain_health", fake_arbitrum)

    gate = ChainHealthGate()
    verdict = await gate.evaluate_chain(42161, client=object())
    assert verdict.chain_id == 42161
    assert verdict.severity == "WARNING"
    assert "WETH" in verdict.aave_frozen_reserves


# ---------------------------------------------------------------------------
# Live integration test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SAPPHIRE_OPTIMISM_INTEGRATION") != "1",
    reason="set SAPPHIRE_OPTIMISM_INTEGRATION=1 to run live RPC test",
)
async def test_live_chain_health_gate_evaluate_chain_10() -> None:
    """Live: ChainHealthGate.evaluate_chain(10) returns a sane verdict."""
    from lib.chains.optimism.client import OptimismClient

    gate = ChainHealthGate()
    async with OptimismClient() as client:
        verdict = await gate.evaluate_chain(10, client=client)
    assert verdict.chain_id == 10
    assert verdict.severity in {"HEALTHY", "WARNING", "BLOCK"}
    assert verdict.reasons  # always non-empty
    # Decimal import is unused otherwise — keep the gated test self-sufficient.
    assert isinstance(verdict.aave_paused_reserves, list)
    _ = Decimal  # keep linter quiet on the import even when this test is skipped
