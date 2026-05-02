"""Unit tests for the Arbitrum branch of the Sentinel chain-health gate.

The gate shell (PR #546, ``lib/hackathon/chain_health_gate.py``) carries
the dispatch + timeout/fail-open machinery; this module provides the
chain-specific classifier for Arbitrum One. Tests here pin the
classifier's severity rules without requiring PR #546 to be merged.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lib.hackathon.arbitrum_chain_health import (
    ARBITRUM_CHAIN_ID,
    HIGH_UTILIZATION_BLOCK_THRESHOLD,
    classify_arbitrum,
    evaluate_arbitrum_chain_health,
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


def test_arbitrum_chain_id_is_42161() -> None:
    """Pinned because every consumer keys behaviour on this constant."""
    assert ARBITRUM_CHAIN_ID == 42161


def test_classify_arbitrum_healthy_when_all_reserves_nominal() -> None:
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", utilization=0.5),
            _StubReserve(symbol="USDC", utilization=0.7),
            _StubReserve(symbol="ARB", utilization=0.1),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 42161
    assert verdict.chain_name == "Arbitrum One"
    assert verdict.aave_paused_reserves == []
    assert verdict.aave_frozen_reserves == []
    # Reasons list is always non-empty for downstream rendering.
    assert verdict.reasons and "nominal" in verdict.reasons[0]


def test_classify_arbitrum_warning_on_frozen_reserve() -> None:
    """Frozen reserves block new positions but allow repayment — WARNING, not BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="WETH", frozen=True, utilization=1.0),
            _StubReserve(symbol="USDC", utilization=0.7),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "WARNING"
    assert verdict.aave_frozen_reserves == ["WETH"]
    assert verdict.aave_paused_reserves == []
    assert any("frozen" in r for r in verdict.reasons)


def test_classify_arbitrum_block_on_paused_high_utilization() -> None:
    """Paused + high-util means existing borrowers can't be liquidated — BLOCK."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="WETH", utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert any("paused with high utilization" in r for r in verdict.reasons)


def test_classify_arbitrum_warning_when_paused_but_low_util_AND_frozen_present() -> None:
    """Paused-but-low-util shouldn't BLOCK; a coexisting frozen reserve still raises WARNING."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="rsETH", paused=True, utilization=0.0),
            _StubReserve(symbol="EURS", frozen=True, utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "WARNING"
    assert "rsETH" in verdict.aave_paused_reserves
    assert "EURS" in verdict.aave_frozen_reserves


def test_classify_arbitrum_block_takes_precedence_over_warning() -> None:
    """A coexisting frozen + paused-high-util must resolve to BLOCK, not WARNING."""
    overview = _StubOverview(
        reserves=[
            _StubReserve(symbol="USDC", paused=True, utilization=0.95),
            _StubReserve(symbol="EURS", frozen=True, utilization=0.5),
        ]
    )
    verdict = classify_arbitrum(overview)
    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert "EURS" in verdict.aave_frozen_reserves


def test_classify_arbitrum_threshold_constant_is_80_percent() -> None:
    """Pinned: changing this changes Sentinel's payment-refusal posture."""
    assert HIGH_UTILIZATION_BLOCK_THRESHOLD == 0.80


def test_classify_arbitrum_threshold_boundary_is_strict() -> None:
    """Exactly-80% utilization paused does NOT BLOCK (strict greater-than)."""
    overview = _StubOverview(
        reserves=[_StubReserve(symbol="USDC", paused=True, utilization=0.80)]
    )
    verdict = classify_arbitrum(overview)
    # paused-but-not-high-util => HEALTHY (no frozen present either)
    assert verdict.severity == "HEALTHY"


@pytest.mark.asyncio
async def test_evaluate_arbitrum_uses_arbitrum_protocols(monkeypatch: pytest.MonkeyPatch) -> None:
    """Composition path: evaluate_arbitrum_chain_health pulls ArbitrumProtocols.lend_overview."""
    captured: dict[str, object] = {}

    class FakeProtocols:
        def __init__(self, client: object) -> None:
            captured["client"] = client

        async def lend_overview(self) -> _StubOverview:
            return _StubOverview(reserves=[_StubReserve(symbol="WETH", utilization=0.4)])

    import lib.chains.arbitrum.protocols as proto_module

    monkeypatch.setattr(proto_module, "ArbitrumProtocols", FakeProtocols)

    fake_client = object()
    verdict = await evaluate_arbitrum_chain_health(fake_client)
    assert captured["client"] is fake_client
    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == 42161
