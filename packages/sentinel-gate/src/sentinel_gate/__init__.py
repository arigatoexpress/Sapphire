"""sapphire-sentinel-gate — multi-chain agent-safety gate.

Public API surface (everything else is ``_internal`` and unstable):

* :class:`ChainHealthGate` — the gate; constructor + :meth:`evaluate_chain`.
* :class:`ChainHealthVerdict` — the dataclass returned by ``evaluate_chain``.
* :class:`PegBreak` — severity enum used by the MegaETH classifier.
* :func:`default_gate` — convenience constructor for live MegaETH RPC.
* :func:`register_chain` — extend the gate with custom chain evaluators.
* :func:`supported_chains` — introspect the registered chain set.

Three-line usage::

    from sentinel_gate import default_gate
    gate = default_gate()
    verdict = gate.evaluate_chain(4326)  # MegaETH
    if verdict.severity == "BLOCK":
        refuse_trade(reasons=verdict.reasons)
"""

from __future__ import annotations

from ._internal.chain_health_gate import (
    ARBITRUM_CHAIN_ID,
    DEFAULT_MEGAETH_RPC_URL,
    DEFAULT_READ_TIMEOUT_S,
    HIGH_UTILIZATION_BLOCK_THRESHOLD,
    MEGAETH_CHAIN_ID,
    OPTIMISM_CHAIN_ID,
    ChainEvaluator,
    ChainHealthGate,
    ChainHealthVerdict,
    default_gate,
    register_chain,
    supported_chains,
)
from ._internal.peg_monitor import PegBreak

__version__ = "0.1.0"

__all__ = [
    # Core API
    "ChainHealthGate",
    "ChainHealthVerdict",
    "ChainEvaluator",
    "PegBreak",
    # Factory + registry
    "default_gate",
    "register_chain",
    "supported_chains",
    # Constants
    "MEGAETH_CHAIN_ID",
    "ARBITRUM_CHAIN_ID",
    "OPTIMISM_CHAIN_ID",
    "DEFAULT_MEGAETH_RPC_URL",
    "DEFAULT_READ_TIMEOUT_S",
    "HIGH_UTILIZATION_BLOCK_THRESHOLD",
    "__version__",
]
