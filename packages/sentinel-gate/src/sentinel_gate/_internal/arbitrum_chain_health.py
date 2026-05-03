"""Arbitrum One branch for the multi-chain Sentinel chain-health gate.

Vendored from ``lib/hackathon/arbitrum_chain_health.py``. The pure
classifier is unchanged. The composition function
:func:`evaluate_arbitrum_chain_health` is simplified for the package:
upstream wraps an ``ArbitrumProtocols`` instance, but here we duck-type
the client — anything exposing ``await client.lend_overview()`` will
work, including the upstream ``ArbitrumProtocols`` instance.

Severity rules for Arbitrum (USDM does not exist here, so the only
on-chain distress signal we read is Aave V3 reserve state):

* ``BLOCK`` — any reserve is paused with utilization >
  :data:`HIGH_UTILIZATION_BLOCK_THRESHOLD` (default 80%). A paused +
  high-utilization reserve means existing borrowers can't be liquidated
  through normal channels: real risk-of-cascade.
* ``WARNING`` — any reserve is frozen but no high-util pause. Frozen
  reserves still allow repayment / withdrawal; they merely block new
  positions. Surface to the operator but do not refuse the payment.
* ``HEALTHY`` — Aave reserves nominal.

The classifier is **pure** — it does no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Arbitrum One chain id (hex 0xa4b1).
ARBITRUM_CHAIN_ID = 42161

#: BLOCK threshold for paused-reserve utilization. Mirrors the MegaETH
#: gate's threshold so behaviour is consistent across chains.
HIGH_UTILIZATION_BLOCK_THRESHOLD = 0.80


@dataclass(frozen=True)
class ArbitrumChainHealthVerdict:
    """Verdict shape — chain-specific subset of :class:`ChainHealthVerdict`.

    Field shape mirrors the unified verdict exactly, minus the
    MegaETH-specific ``peg_divergence_bps`` (USDM doesn't exist here).
    The dispatcher in :mod:`chain_health_gate` translates this into the
    unified shape before returning to the caller.
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str] = field(default_factory=list)
    aave_paused_reserves: list[str] = field(default_factory=list)
    aave_frozen_reserves: list[str] = field(default_factory=list)


def classify_arbitrum(lend: Any) -> ArbitrumChainHealthVerdict:
    """Pure classifier — turn a lend-overview-shaped object into a verdict.

    ``lend`` may be any object satisfying the duck-typed contract:
    ``lend.reserves`` is iterable, each item exposes ``.symbol``,
    ``.paused``, ``.frozen``, and ``.utilization``.

    USDM doesn't exist on Arbitrum — Aave V3 reserve state is the only
    chain-distress axis we evaluate.
    """
    reserves = list(getattr(lend, "reserves", []) or [])

    paused: list[str] = []
    frozen: list[str] = []
    paused_high_util: list[str] = []

    for r in reserves:
        if getattr(r, "paused", False):
            paused.append(r.symbol)
            if getattr(r, "utilization", 0.0) > HIGH_UTILIZATION_BLOCK_THRESHOLD:
                paused_high_util.append(r.symbol)
        if getattr(r, "frozen", False):
            frozen.append(r.symbol)

    severity = "HEALTHY"
    reasons: list[str] = []

    if paused_high_util:
        severity = "BLOCK"
        reasons.append(f"Aave reserves paused with high utilization (>80%): {paused_high_util}")
    elif frozen:
        severity = "WARNING"
        reasons.append(f"Aave reserves frozen: {frozen}")
    else:
        reasons.append("chain healthy: Aave reserves nominal")

    return ArbitrumChainHealthVerdict(
        chain_id=ARBITRUM_CHAIN_ID,
        chain_name="Arbitrum One",
        severity=severity,
        reasons=reasons,
        aave_paused_reserves=paused,
        aave_frozen_reserves=frozen,
    )


async def evaluate_arbitrum_chain_health(client: Any) -> ArbitrumChainHealthVerdict:
    """Compose the live read with the pure classifier.

    The ``client`` must duck-type ``await client.lend_overview()`` —
    this matches the ``ArbitrumProtocols`` surface upstream, but any
    custom RPC wrapper exposing the same coroutine works too.
    """
    lend = await client.lend_overview()
    return classify_arbitrum(lend)
