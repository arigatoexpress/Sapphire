"""Vendored ``PegBreak`` enum from Sapphire's ``lib.chains.megaeth.contracts.peg_monitor``.

We vendor only the enum (not the live ``PegMonitor`` class), because
the classifier in :mod:`sentinel_gate._internal.chain_health_gate`
only reads the severity tag off a pre-evaluated ``StableHealth``-like
object. The actual peg-evaluation logic is the responsibility of the
client the user passes to :class:`ChainHealthGate`.

If you want to drive the live MegaETH peg monitor, install Sapphire
itself and pass its ``MegaETHProtocols`` instance through the gate's
client factory — the duck-typed surface is identical.
"""

from __future__ import annotations

from enum import Enum


class PegBreak(Enum):
    """Severity classification for stablecoin peg deviation.

    Mirrors the upstream ``lib.chains.megaeth.contracts.peg_monitor.PegBreak``
    surface. The classifier only inspects ``severity in (BREAK_100BP,
    CRISIS_500BP, CIRCUIT_BREAKER)`` for BLOCK and ``severity is
    WARNING_50BP`` for WARNING — so any additional members upstream
    add are non-breaking here.
    """

    HEALTHY = "healthy"
    WARNING_50BP = "warning_50bp"
    BREAK_100BP = "break_100bp"
    CRISIS_500BP = "crisis_500bp"
    CIRCUIT_BREAKER = "circuit_breaker"
