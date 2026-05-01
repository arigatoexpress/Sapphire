"""Unit tests for the Sentinel MegaETH chain-health gate.

The gate is purposefully thin — most of its work is composing two
existing MegaETHProtocols reads. We mock those reads (rather than the
RPC client) to keep the test surface focused on the *classification
logic* and *fail-open behaviour* the gate actually owns.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from lib.chains.megaeth.contracts.peg_monitor import PegBreak
from lib.hackathon.chain_health_gate import (
    MEGAETH_CHAIN_ID,
    ChainHealthGate,
    ChainHealthVerdict,
    _classify,
    default_gate,
)


# ---------------------------------------------------------------------------
# Mock fixtures — minimal duck-typed objects matching the dataclass surface
# the classifier reads from. We don't construct real StableHealth /
# LendOverview because they pull in registry yaml + ABIs we don't need.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test 1: HEALTHY chain returns HEALTHY
# ---------------------------------------------------------------------------


def test_healthy_chain_classifies_as_healthy():
    stable = _stable(PegBreak.HEALTHY, 8)
    lend = _lend([_reserve("USDC", utilization=0.5), _reserve("WETH", utilization=0.3)])

    verdict = _classify(stable, lend)

    assert verdict.severity == "HEALTHY"
    assert verdict.chain_id == MEGAETH_CHAIN_ID
    assert verdict.peg_divergence_bps == Decimal(8)
    assert verdict.aave_paused_reserves == []


# ---------------------------------------------------------------------------
# Test 2: BREAK_100BP USDM depeg triggers BLOCK
# ---------------------------------------------------------------------------


def test_usdm_depegging_triggers_block():
    stable = _stable(PegBreak.BREAK_100BP, 137)
    lend = _lend([_reserve("USDC", utilization=0.5)])

    verdict = _classify(stable, lend)

    assert verdict.severity == "BLOCK"
    assert verdict.peg_divergence_bps == Decimal(137)
    assert any("USDM depegging" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# Test 3: WARNING_50BP severity -> WARNING (do not block)
# ---------------------------------------------------------------------------


def test_warning_50bp_classifies_as_warning():
    stable = _stable(PegBreak.WARNING_50BP, 60)
    lend = _lend([_reserve("USDC")])

    verdict = _classify(stable, lend)

    assert verdict.severity == "WARNING"
    assert any("USDM peg drift" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# Test 4: paused reserve with high utilization triggers BLOCK
# ---------------------------------------------------------------------------


def test_paused_high_utilization_reserve_triggers_block():
    stable = _stable(PegBreak.HEALTHY, 5)
    lend = _lend(
        [
            _reserve("USDC", paused=True, utilization=0.92),  # paused + pinned
            _reserve("WETH", utilization=0.4),
        ]
    )

    verdict = _classify(stable, lend)

    assert verdict.severity == "BLOCK"
    assert "USDC" in verdict.aave_paused_reserves
    assert any("paused with high utilization" in r for r in verdict.reasons)


def test_paused_low_utilization_reserve_only_surfaces_no_block():
    stable = _stable(PegBreak.HEALTHY, 5)
    lend = _lend([_reserve("USDC", paused=True, utilization=0.30)])

    verdict = _classify(stable, lend)

    # Paused but low-util: surface in aave_paused_reserves but don't BLOCK.
    assert verdict.severity == "HEALTHY"
    assert verdict.aave_paused_reserves == ["USDC"]


def test_frozen_reserve_classifies_as_warning():
    stable = _stable(PegBreak.HEALTHY, 5)
    lend = _lend([_reserve("USDT", frozen=True, utilization=0.5)])

    verdict = _classify(stable, lend)

    assert verdict.severity == "WARNING"
    assert any("frozen" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# Test 5: RPC timeout -> HEALTHY (fail-open) with reason
# ---------------------------------------------------------------------------


def test_rpc_timeout_returns_healthy_with_reason_when_failopen():
    """Slow RPC must not block legitimate payments at demo time."""

    class _SlowClient:
        async def _call(self, *_a, **_kw):
            await asyncio.sleep(10)  # well past the 0.05s test timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    # Patch MegaETHProtocols.stable_health to actually trigger a sleep.
    async def _slow_stable_health(self, *_a, **_kw):
        await asyncio.sleep(10)

    gate = ChainHealthGate(
        client_factory=lambda: _SlowClient(), allow_when_unavailable=True, read_timeout_s=0.05
    )

    with patch(
        "lib.hackathon.chain_health_gate.MegaETHProtocols.stable_health",
        _slow_stable_health,
    ):
        verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "HEALTHY"
    assert any("rpc timeout" in r.lower() for r in verdict.reasons)


def test_rpc_timeout_blocks_when_failclosed():
    async def _slow_stable_health(self, *_a, **_kw):
        await asyncio.sleep(10)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    gate = ChainHealthGate(
        client_factory=lambda: _Client(), allow_when_unavailable=False, read_timeout_s=0.05
    )

    with patch(
        "lib.hackathon.chain_health_gate.MegaETHProtocols.stable_health",
        _slow_stable_health,
    ):
        verdict = gate.evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.severity == "BLOCK"
    assert any("fail-closed" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# Test 6: non-MegaETH chain ID -> HEALTHY trivially
# ---------------------------------------------------------------------------


def test_non_megaeth_chain_id_returns_healthy_trivially():
    gate = ChainHealthGate(client_factory=lambda: object(), allow_when_unavailable=True)

    verdict = gate.evaluate_chain(46630)  # Robinhood Chain testnet

    assert verdict.severity == "HEALTHY"
    assert verdict.reasons == ["chain not gated"]
    assert verdict.peg_divergence_bps is None


# ---------------------------------------------------------------------------
# Bonus: ChainHealthVerdict construction shape (defensive — Sentinel embeds it)
# ---------------------------------------------------------------------------


def test_verdict_dataclass_shape():
    v = ChainHealthVerdict(
        chain_id=4326,
        chain_name="MegaETH",
        severity="BLOCK",
        reasons=["USDM depegging at 200 bps"],
        peg_divergence_bps=Decimal(200),
        aave_paused_reserves=["USDC"],
    )
    assert v.severity == "BLOCK"
    assert v.peg_divergence_bps == Decimal(200)


# ---------------------------------------------------------------------------
# Live integration test — gated on env, hits real MegaETH mainnet
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SAPPHIRE_MEGAETH_INTEGRATION") != "1",
    reason="set SAPPHIRE_MEGAETH_INTEGRATION=1 to run live mainnet gate test",
)
def test_default_gate_against_live_mainnet_returns_known_severity():
    """Hits MegaETH mainnet via default_gate(); accepts any of the 3 severities."""
    verdict = default_gate().evaluate_chain(MEGAETH_CHAIN_ID)

    assert verdict.chain_id == MEGAETH_CHAIN_ID
    assert verdict.severity in {"HEALTHY", "WARNING", "BLOCK"}
    # peg_divergence_bps may be None if the gate fell back to fail-open;
    # that's still a valid live response.
    assert verdict.peg_divergence_bps is None or isinstance(verdict.peg_divergence_bps, Decimal)
    assert isinstance(verdict.reasons, list) and verdict.reasons
