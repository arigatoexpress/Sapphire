"""Multi-chain Sentinel chain-health dispatcher.

Routes ``ChainHealthGate.evaluate_chain(chain_id)`` to the per-chain
evaluator that ships in this package. Each per-chain module
(``megaeth_chain_health.py``, ``arbitrum_chain_health.py``,
``optimism_chain_health.py``) exposes its own pure classifier + an
async ``evaluate_<chain>_chain_health(client)`` composer; the dispatcher
adapts each return type into a unified :class:`ChainHealthVerdict` so
Sentinel callers don't have to know about the chain split.

Supported chains as of this PR:

============= ==========  =====================================
chain_id      hex         module
============= ==========  =====================================
4326          ``0x10ee``  ``megaeth_chain_health``
42161         ``0xa4b1``  ``arbitrum_chain_health``
10            ``0xa``     ``optimism_chain_health``  (this PR)
============= ==========  =====================================

The dispatcher is intentionally thin — all severity logic lives in the
per-chain modules so each chain's risk model can evolve independently.
Adding a new chain is one ``elif chain_id == ...`` branch + one
per-chain module.

Read-only. Does not refuse payments — it surfaces a verdict the
Sentinel decision engine consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arbitrum_chain_health import ARBITRUM_CHAIN_ID, evaluate_arbitrum_chain_health
from .optimism_chain_health import OPTIMISM_CHAIN_ID, evaluate_optimism_chain_health

#: MegaETH testnet chain id. Pinned here even though the per-chain
#: module isn't in this repo yet — keeps the dispatcher's surface stable
#: when PR #546 lands.
MEGAETH_CHAIN_ID = 4326

#: Recognized chain ids the dispatcher knows how to route. Anything else
#: returns an UNKNOWN verdict (fail-open at the dispatcher level so a
#: single missing per-chain module doesn't block Sentinel entirely).
SUPPORTED_CHAIN_IDS: frozenset[int] = frozenset(
    {MEGAETH_CHAIN_ID, ARBITRUM_CHAIN_ID, OPTIMISM_CHAIN_ID}
)


@dataclass(frozen=True)
class ChainHealthVerdict:
    """Unified verdict shape across chains.

    Per-chain evaluators return their own dataclass; the dispatcher
    re-shapes them into this struct so Sentinel callers see one type.
    The Optional fields are populated only when the underlying chain
    surfaces them (e.g. USDM peg only exists on MegaETH).
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK" | "UNKNOWN"
    reasons: list[str] = field(default_factory=list)
    aave_paused_reserves: list[str] = field(default_factory=list)
    aave_frozen_reserves: list[str] = field(default_factory=list)
    usdm_peg_deviation_bps: float | None = None  # MegaETH-only


def _to_unified(verdict: object) -> ChainHealthVerdict:
    """Adapt any per-chain verdict dataclass into ChainHealthVerdict.

    Per-chain modules return their own frozen dataclass with field shape
    matching ChainHealthVerdict (chain_id, chain_name, severity, reasons,
    aave_paused_reserves, aave_frozen_reserves, optional usdm_*). We
    duck-type the conversion so adding a new chain doesn't require
    touching the unifier.
    """
    return ChainHealthVerdict(
        chain_id=int(verdict.chain_id),
        chain_name=str(getattr(verdict, "chain_name", "")),
        severity=str(getattr(verdict, "severity", "UNKNOWN")),
        reasons=list(getattr(verdict, "reasons", []) or []),
        aave_paused_reserves=list(getattr(verdict, "aave_paused_reserves", []) or []),
        aave_frozen_reserves=list(getattr(verdict, "aave_frozen_reserves", []) or []),
        usdm_peg_deviation_bps=getattr(verdict, "usdm_peg_deviation_bps", None),
    )


class ChainHealthGate:
    """Dispatcher: ``evaluate_chain(chain_id)`` → ``ChainHealthVerdict``.

    Construct once, call ``evaluate_chain`` per supported chain. Caller
    is responsible for supplying the right RPC client per chain (the
    dispatcher is client-agnostic so it doesn't have to know anything
    about each chain's transport).
    """

    def __init__(self) -> None:
        # Could grow into a registry of `chain_id -> (client, evaluator)`
        # tuples in a follow-up; today the per-chain client wiring is
        # caller-supplied via evaluate_chain(client=...).
        pass

    async def evaluate_chain(self, chain_id: int, *, client: object) -> ChainHealthVerdict:
        """Route to the per-chain evaluator for ``chain_id``.

        ``client`` must satisfy the structural ``_call(method, params)``
        Protocol the per-chain wrappers expect (an
        ``OptimismClient`` / ``ArbitrumClient`` / ``MegaETHClient``
        instance, or a test stub). The dispatcher does not validate the
        client — wrong chain client + wrong chain id will surface as a
        decode failure inside the per-chain evaluator.
        """
        if chain_id == OPTIMISM_CHAIN_ID:
            verdict = await evaluate_optimism_chain_health(client)
            return _to_unified(verdict)
        if chain_id == ARBITRUM_CHAIN_ID:
            verdict = await evaluate_arbitrum_chain_health(client)
            return _to_unified(verdict)
        if chain_id == MEGAETH_CHAIN_ID:
            # MegaETH evaluator may or may not be present depending on
            # which PR has merged. Late import + graceful fallback.
            try:
                from .megaeth_chain_health import (  # type: ignore[import-not-found]  # noqa: PLC0415
                    evaluate_megaeth_chain_health,
                )
            except ImportError:
                return ChainHealthVerdict(
                    chain_id=MEGAETH_CHAIN_ID,
                    chain_name="MegaETH",
                    severity="UNKNOWN",
                    reasons=["megaeth_chain_health module not available in this build"],
                )
            verdict = await evaluate_megaeth_chain_health(client)
            return _to_unified(verdict)

        return ChainHealthVerdict(
            chain_id=chain_id,
            chain_name=f"chain:{chain_id}",
            severity="UNKNOWN",
            reasons=[
                f"chain_id={chain_id} not registered with the dispatcher; "
                f"supported: {sorted(SUPPORTED_CHAIN_IDS)}"
            ],
        )


__all__ = (
    "ChainHealthGate",
    "ChainHealthVerdict",
    "MEGAETH_CHAIN_ID",
    "ARBITRUM_CHAIN_ID",
    "OPTIMISM_CHAIN_ID",
    "SUPPORTED_CHAIN_IDS",
)
