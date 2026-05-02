"""Arbitrum One branch for the multi-chain Sentinel chain-health gate.

The MegaETH gate (``lib/hackathon/chain_health_gate.py``, PR #546) ships
the dispatch shell + the ``ChainHealthVerdict`` shape. This module is the
chain-specific evaluator for chain id 42161 (Arbitrum One).

It is intentionally split into its own file so this PR (Arbitrum Aave V3
read layer) and PR #546 (the gate shell) can land independently —
PR #546 imports this module on merge, no cross-file conflict required.

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

The classifier is **pure** — it does no I/O. Composition with a live
``ArbitrumProtocols`` instance is the gate's responsibility.
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
    """Stand-in verdict shape for tests + PR #546 integration.

    Field shape mirrors the MegaETH-side ``ChainHealthVerdict`` exactly
    — when PR #546 lands, the gate constructs its own
    ``ChainHealthVerdict`` from these fields rather than importing this
    dataclass directly. We keep our own copy so unit tests here don't
    require PR #546 to be merged.
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str] = field(default_factory=list)
    aave_paused_reserves: list[str] = field(default_factory=list)
    aave_frozen_reserves: list[str] = field(default_factory=list)


def classify_arbitrum(lend: Any) -> ArbitrumChainHealthVerdict:
    """Pure classifier — turn an Arbitrum ``LendOverview`` into a verdict.

    ``lend`` may be any object satisfying the duck-typed contract:
    ``lend.reserves`` is iterable, each item exposes ``.symbol``,
    ``.paused``, ``.frozen``, and ``.utilization``. Both the
    ``ArbitrumProtocols.lend_overview()`` return and a hand-rolled
    test stub satisfy this.

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
        reasons.append(
            f"Aave reserves paused with high utilization (>80%): {paused_high_util}"
        )
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

    Builds an :class:`ArbitrumProtocols` against the supplied client,
    pulls ``lend_overview()``, and runs the classifier. The gate shell
    in PR #546 is responsible for the timeout-wrapping +
    fail-open/fail-closed behaviour around this call.
    """
    # Late import — keeps ``lib.hackathon`` from pulling the chain
    # access layer at module import time.
    from lib.chains.arbitrum.protocols import ArbitrumProtocols  # noqa: PLC0415

    proto = ArbitrumProtocols(client)
    lend = await proto.lend_overview()
    return classify_arbitrum(lend)
