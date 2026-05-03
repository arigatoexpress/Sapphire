"""Tests for the USDM peg-monitor primitive.

Pure-function tests — no network, no fixture loading. The classifier
is the load-bearing part of the circuit-breaker, so it gets coverage
across every band boundary.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from lib.chains.megaeth.contracts.peg_monitor import (
    PegBreak,
    PegMonitor,
    PegSnapshot,
    classify_divergence,
)
from lib.chains.megaeth.contracts.usdm import PegQuote

# ---------------------------------------------------------------------------
# classify_divergence — every threshold boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bps, expected",
    [
        (0, PegBreak.HEALTHY),
        (10, PegBreak.HEALTHY),
        (Decimal("24.99"), PegBreak.HEALTHY),
        (25, PegBreak.WARNING_50BP),
        (50, PegBreak.WARNING_50BP),
        (Decimal("99.99"), PegBreak.WARNING_50BP),
        (100, PegBreak.BREAK_100BP),
        (250, PegBreak.BREAK_100BP),
        (Decimal("499.99"), PegBreak.BREAK_100BP),
        (500, PegBreak.CRISIS_500BP),
        (1000, PegBreak.CRISIS_500BP),
        (Decimal("1499.99"), PegBreak.CRISIS_500BP),
        (1500, PegBreak.CIRCUIT_BREAKER),
        (10_000, PegBreak.CIRCUIT_BREAKER),
    ],
)
def test_classify_divergence_band_boundaries(bps: int | Decimal, expected: PegBreak) -> None:
    assert classify_divergence(bps) == expected


def test_classify_divergence_clamps_negative() -> None:
    """Negative inputs are nonsensical (the spread is always non-negative)
    but we clamp rather than raise to avoid breaking pipelines on a
    transient sign error."""
    assert classify_divergence(-5) == PegBreak.HEALTHY


def test_classify_divergence_accepts_float() -> None:
    assert classify_divergence(99.5) == PegBreak.WARNING_50BP


def test_classify_divergence_accepts_int() -> None:
    assert classify_divergence(0) == PegBreak.HEALTHY


def test_classify_divergence_accepts_decimal_with_high_precision() -> None:
    """Edge of band — 99.999... should still classify as WARNING_50BP."""
    spread = Decimal("99.99999999999999999999")
    assert classify_divergence(spread) == PegBreak.WARNING_50BP


# ---------------------------------------------------------------------------
# PegSnapshot.from_quote — composition
# ---------------------------------------------------------------------------


def test_snapshot_from_healthy_quote() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal("0.999506"),
        aave_oracle_usd=Decimal("1.000000"),
        twap60_usd=Decimal("0.999264"),
        eth_oracle_usd=Decimal("1.0000000465"),
        divergence_bps=Decimal("7.4"),
    )
    snap = PegSnapshot.from_quote(quote)
    assert snap.severity == PegBreak.HEALTHY
    assert snap.is_healthy()
    assert snap.sources_present == 4
    assert snap.divergence_bps == Decimal("7.4")
    assert snap.usdm_kumbaya_usdt0 == Decimal("0.999506")
    assert snap.usdm_aave_oracle == Decimal("1.000000")


def test_snapshot_from_break_quote() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal("0.985"),
        aave_oracle_usd=Decimal("1.000"),
        twap60_usd=None,
        eth_oracle_usd=None,
        divergence_bps=Decimal("152.3"),
    )
    snap = PegSnapshot.from_quote(quote)
    assert snap.severity == PegBreak.BREAK_100BP
    assert not snap.is_healthy()
    assert snap.sources_present == 2


def test_snapshot_from_crisis_quote() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal("0.93"),
        aave_oracle_usd=Decimal("1.000"),
        twap60_usd=Decimal("0.95"),
        eth_oracle_usd=None,
        divergence_bps=Decimal("753.0"),
    )
    snap = PegSnapshot.from_quote(quote)
    assert snap.severity == PegBreak.CRISIS_500BP


def test_snapshot_from_circuit_breaker_quote() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal("0.80"),
        aave_oracle_usd=Decimal("1.000"),
        twap60_usd=None,
        eth_oracle_usd=None,
        divergence_bps=Decimal("2500.0"),
    )
    snap = PegSnapshot.from_quote(quote)
    assert snap.severity == PegBreak.CIRCUIT_BREAKER


def test_snapshot_carries_timestamp() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal(1),
        aave_oracle_usd=None,
        twap60_usd=None,
        eth_oracle_usd=None,
        divergence_bps=Decimal(0),
        timestamp_unix=1_700_000_000,
    )
    snap = PegSnapshot.from_quote(quote)
    assert snap.timestamp_unix == 1_700_000_000


# ---------------------------------------------------------------------------
# PegMonitor.evaluate — composes USDM.peg_quote
# ---------------------------------------------------------------------------


class _StubUSDM:
    """Minimal USDM stand-in for PegMonitor.evaluate tests."""

    def __init__(self, quote: PegQuote) -> None:
        self._quote = quote

    async def peg_quote(
        self, *, kumbaya_quote_fn: Any = None, aave_oracle_call_fn: Any = None
    ) -> PegQuote:
        return self._quote


@pytest.mark.asyncio
async def test_monitor_evaluate_healthy() -> None:
    quote = PegQuote(
        kumbaya_usdt0=Decimal("0.9995"),
        aave_oracle_usd=Decimal(1),
        twap60_usd=None,
        eth_oracle_usd=None,
        divergence_bps=Decimal(5),
    )
    snap = await PegMonitor().evaluate(_StubUSDM(quote))
    assert snap.severity == PegBreak.HEALTHY
    assert snap.sources_present == 2


@pytest.mark.asyncio
async def test_monitor_evaluate_passes_callables_through() -> None:
    """The two optional callables are forwarded verbatim to USDM.peg_quote."""

    captured: dict[str, Any] = {}

    class _CapturingUSDM:
        async def peg_quote(
            self, *, kumbaya_quote_fn: Any = None, aave_oracle_call_fn: Any = None
        ) -> PegQuote:
            captured["kumbaya"] = kumbaya_quote_fn
            captured["aave"] = aave_oracle_call_fn
            return PegQuote(
                kumbaya_usdt0=None,
                aave_oracle_usd=None,
                twap60_usd=None,
                eth_oracle_usd=None,
                divergence_bps=Decimal(0),
            )

    sentinel_a = object()
    sentinel_b = object()
    await PegMonitor().evaluate(
        _CapturingUSDM(),
        kumbaya_quote_fn=sentinel_a,
        aave_oracle_call_fn=sentinel_b,
    )
    assert captured["kumbaya"] is sentinel_a
    assert captured["aave"] is sentinel_b


# ---------------------------------------------------------------------------
# should_block_trade — the load-bearing decision
# ---------------------------------------------------------------------------


def _snap(severity: PegBreak, *, sources: int = 3, spread: Decimal = Decimal("10")) -> PegSnapshot:
    return PegSnapshot(
        usdm_kumbaya_usdt0=Decimal("1.0") if sources >= 1 else None,
        usdm_aave_oracle=Decimal("1.0") if sources >= 2 else None,
        usdm_twap60=Decimal("1.0") if sources >= 3 else None,
        usdm_implied_via_eth_oracle=Decimal("1.0") if sources >= 4 else None,
        divergence_bps=spread,
        severity=severity,
        sources_present=sources,
    )


def test_should_block_healthy_does_not_block() -> None:
    snap = _snap(PegBreak.HEALTHY, sources=3, spread=Decimal(5))
    block, reason = PegMonitor.should_block_trade(snap)
    assert block is False
    assert "HEALTHY" in reason


def test_should_block_warning_50bp_default_does_not_block() -> None:
    """Default ``min_severity_to_block`` is BREAK_100BP, so a WARNING
    (25-100bp) divergence should NOT trigger an automatic block."""
    snap = _snap(PegBreak.WARNING_50BP, spread=Decimal(50))
    block, _reason = PegMonitor.should_block_trade(snap)
    assert block is False


def test_should_block_break_100bp_default_blocks() -> None:
    snap = _snap(PegBreak.BREAK_100BP, spread=Decimal(150))
    block, reason = PegMonitor.should_block_trade(snap)
    assert block is True
    assert "BREAK_100BP" in reason
    assert "150" in reason


def test_should_block_crisis_blocks() -> None:
    snap = _snap(PegBreak.CRISIS_500BP, spread=Decimal(750))
    block, _reason = PegMonitor.should_block_trade(snap)
    assert block is True


def test_should_block_circuit_breaker_blocks() -> None:
    snap = _snap(PegBreak.CIRCUIT_BREAKER, spread=Decimal(2500))
    block, reason = PegMonitor.should_block_trade(snap)
    assert block is True
    assert "CIRCUIT_BREAKER" in reason


def test_should_block_one_source_blocks_by_default() -> None:
    """Single-source readings can be manipulated. Default require_sources=2."""
    snap = _snap(PegBreak.HEALTHY, sources=1, spread=Decimal(0))
    block, reason = PegMonitor.should_block_trade(snap)
    assert block is True
    assert "insufficient peg sources" in reason


def test_should_block_one_source_unblocks_when_threshold_lowered() -> None:
    snap = _snap(PegBreak.HEALTHY, sources=1, spread=Decimal(0))
    block, _reason = PegMonitor.should_block_trade(snap, require_sources=1)
    assert block is False


def test_should_block_with_warning_threshold_blocks_warning() -> None:
    """Strategies can tighten the threshold — WARNING blocks if so configured."""
    snap = _snap(PegBreak.WARNING_50BP, spread=Decimal(50))
    block, _reason = PegMonitor.should_block_trade(
        snap, min_severity_to_block=PegBreak.WARNING_50BP
    )
    assert block is True


def test_should_block_circuit_breaker_threshold_only_blocks_at_breaker() -> None:
    """Loosest setting: only block at CIRCUIT_BREAKER."""
    snap_break = _snap(PegBreak.BREAK_100BP, spread=Decimal(200))
    block, _reason = PegMonitor.should_block_trade(
        snap_break, min_severity_to_block=PegBreak.CIRCUIT_BREAKER
    )
    assert block is False

    snap_breaker = _snap(PegBreak.CIRCUIT_BREAKER, spread=Decimal(2000))
    block, _reason = PegMonitor.should_block_trade(
        snap_breaker, min_severity_to_block=PegBreak.CIRCUIT_BREAKER
    )
    assert block is True


def test_should_block_zero_sources_always_blocks() -> None:
    snap = _snap(PegBreak.HEALTHY, sources=0, spread=Decimal(0))
    block, reason = PegMonitor.should_block_trade(snap)
    assert block is True
    assert "0 present" in reason


# ---------------------------------------------------------------------------
# PegBreak ordering — IntEnum comparability
# ---------------------------------------------------------------------------


def test_pegbreak_is_intenum_orderable() -> None:
    assert PegBreak.HEALTHY < PegBreak.WARNING_50BP
    assert PegBreak.WARNING_50BP < PegBreak.BREAK_100BP
    assert PegBreak.BREAK_100BP < PegBreak.CRISIS_500BP
    assert PegBreak.CRISIS_500BP < PegBreak.CIRCUIT_BREAKER


def test_pegbreak_values_stable() -> None:
    """Stability of integer values matters for cross-process serialization
    (event-bus emit, dashboard JSON)."""
    assert PegBreak.HEALTHY.value == 0
    assert PegBreak.WARNING_50BP.value == 1
    assert PegBreak.BREAK_100BP.value == 2
    assert PegBreak.CRISIS_500BP.value == 3
    assert PegBreak.CIRCUIT_BREAKER.value == 4


def test_pegbreak_compare_threshold_default() -> None:
    """The ``severity >= PegBreak.BREAK_100BP`` shape used by the breaker."""
    snap = PegBreak.WARNING_50BP
    assert not (snap >= PegBreak.BREAK_100BP)
    assert PegBreak.BREAK_100BP >= PegBreak.BREAK_100BP
    assert PegBreak.CRISIS_500BP >= PegBreak.BREAK_100BP
