"""Multi-chain health gate (vendored from Sapphire's ``lib/hackathon/chain_health_gate.py``).

Sentinel already screens payments on policy axes (mandate, budget, domain
allow-list, prompt-injection, secret-egress). This module adds one more
axis: the *chain state the alpha references must not be in distress*.

If the alpha's underlying chain has USDM depegging, an Aave reserve frozen,
or a paused high-utilization reserve, paying for that signal is wasteful
at best and adversarial at worst — the chain is currently un-tradeable.

The gate is **fail-open by default** (``allow_when_unavailable=True``) so a
flaky RPC at demo time doesn't block legitimate payments. We block only on
*observed* distress, never on absence of evidence.

This vendored copy differs from the upstream Sapphire file in two ways:

1. The ``PegBreak`` enum and protocol facades are imported from this
   package's ``_internal`` namespace rather than ``lib.chains.megaeth``,
   so the package is installable without the full Sapphire monorepo.
2. The dispatcher accepts a registered evaluator table — see
   :func:`register_chain` — so users can add chain support without
   modifying the package source.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .arbitrum_chain_health import (
    ARBITRUM_CHAIN_ID,
    evaluate_arbitrum_chain_health,
)
from .peg_monitor import PegBreak

#: MegaETH chain id (Wave A primary target).
MEGAETH_CHAIN_ID = 4326

#: Optimism chain id — placeholder. No live evaluator is shipped; chain
#: id 10 currently falls through to ``HEALTHY / "chain not gated"``.
#: Users with an Optimism evaluator can register it via
#: :func:`register_chain`.
OPTIMISM_CHAIN_ID = 10

#: Per-read timeout. The gate calls 2 reads (stable_health, lend_overview).
#: Keep this small — the gate sits in the Sentinel critical path and a slow
#: RPC must not stall a payment evaluation.
DEFAULT_READ_TIMEOUT_S = 3.0

#: Default mainnet RPC URL for the optional ``default_gate()`` factory.
DEFAULT_MEGAETH_RPC_URL = "https://mainnet.megaeth.com/rpc"

#: BLOCK threshold for paused-reserve utilization. A paused reserve isn't
#: itself a crisis, but a paused reserve with >80% utilization means
#: existing borrowers can't be liquidated through normal channels —
#: a real risk-of-cascade signal.
HIGH_UTILIZATION_BLOCK_THRESHOLD = 0.80


@dataclass(frozen=True)
class ChainHealthVerdict:
    """Severity classification + supporting evidence for one chain.

    Field shape mirrors Sapphire Sentinel's ``SentinelDecision`` so it
    embeds cleanly:

    * ``severity`` — one of ``HEALTHY``/``WARNING``/``BLOCK``. Sentinel
      only refuses on ``BLOCK``; ``WARNING`` is surface-only.
    * ``reasons`` — human-readable strings the dashboard renders next
      to the existing policy reasons.
    * ``peg_divergence_bps`` — the actual measured spread when a stable
      health read succeeded; ``None`` when the chain wasn't gated, the
      read failed, or the chain has no stablecoin to gate on.
    * ``aave_paused_reserves`` — symbol list, surfaced even on WARNING
      so dashboards can show *which* reserve is degraded.
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str] = field(default_factory=list)
    peg_divergence_bps: Decimal | None = None
    aave_paused_reserves: list[str] = field(default_factory=list)


# Type alias for a chain-specific evaluator coroutine. Given the user's
# duck-typed RPC client, returns a verdict for that chain.
ChainEvaluator = Callable[[Any], Awaitable[ChainHealthVerdict]]


# ---------------------------------------------------------------------------
# Per-chain evaluator registry
# ---------------------------------------------------------------------------


def _evaluate_megaeth_default(client: Any) -> Awaitable[ChainHealthVerdict]:
    """Default MegaETH evaluator — composes ``stable_health`` + ``lend_overview``.

    Expects ``client`` to be a duck-typed ``MegaETHProtocols`` instance:
    must expose async ``stable_health()`` and ``lend_overview()``
    coroutines whose returns satisfy the surface read by
    :func:`_classify_megaeth`.
    """

    async def _run() -> ChainHealthVerdict:
        stable = await client.stable_health()
        lend = await client.lend_overview()
        return _classify_megaeth(stable, lend)

    return _run()


def _evaluate_arbitrum_default(client: Any) -> Awaitable[ChainHealthVerdict]:
    """Default Arbitrum evaluator — wraps ``evaluate_arbitrum_chain_health``.

    Translates the chain-specific verdict shape back to the unified
    :class:`ChainHealthVerdict` so the dispatcher returns a homogeneous
    type regardless of the chain.
    """

    async def _run() -> ChainHealthVerdict:
        verdict = await evaluate_arbitrum_chain_health(client)
        return ChainHealthVerdict(
            chain_id=verdict.chain_id,
            chain_name=verdict.chain_name,
            severity=verdict.severity,
            reasons=list(verdict.reasons),
            peg_divergence_bps=None,
            aave_paused_reserves=list(verdict.aave_paused_reserves),
        )

    return _run()


# Registry: chain_id -> (display_name, evaluator)
_CHAIN_REGISTRY: dict[int, tuple[str, ChainEvaluator]] = {
    MEGAETH_CHAIN_ID: ("MegaETH", _evaluate_megaeth_default),
    ARBITRUM_CHAIN_ID: ("Arbitrum One", _evaluate_arbitrum_default),
    # Optimism intentionally absent — falls through to "chain not gated".
}


def register_chain(
    chain_id: int,
    name: str,
    evaluator: ChainEvaluator,
) -> None:
    """Register a custom chain evaluator.

    Allows users to extend the gate with chain-specific health checks
    without forking the package. The evaluator is an async callable
    that receives the user's duck-typed RPC client and returns a
    :class:`ChainHealthVerdict`.
    """
    _CHAIN_REGISTRY[chain_id] = (name, evaluator)


def supported_chains() -> dict[int, str]:
    """Return ``{chain_id: display_name}`` for every registered chain."""
    return {cid: name for cid, (name, _) in _CHAIN_REGISTRY.items()}


def _chain_name_for(chain_id: int) -> str:
    entry = _CHAIN_REGISTRY.get(chain_id)
    if entry is not None:
        return entry[0]
    if chain_id == OPTIMISM_CHAIN_ID:
        return "Optimism"
    return f"chain-{chain_id}"


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------


class ChainHealthGate:
    """Sentinel-aware multi-chain health classifier.

    Constructor:

    * ``client_factory`` — zero-arg callable returning a fresh
      RPC client. Factory pattern (instead of a live client) means
      tests can inject a mock and the gate doesn't hold an open
      httpx session for the entire process lifetime.
    * ``allow_when_unavailable`` — when True (default), RPC failure /
      timeout returns HEALTHY with a "rpc unavailable" reason. When
      False, the gate fails closed (BLOCK) — only set this when you
      explicitly want to refuse payments during chain-data outages.
    """

    def __init__(
        self,
        client_factory: Callable[[], Any],
        allow_when_unavailable: bool = True,
        *,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        self._client_factory = client_factory
        self._allow_when_unavailable = allow_when_unavailable
        self._read_timeout_s = read_timeout_s

    def evaluate_chain(self, chain_id: int) -> ChainHealthVerdict:
        """Classify a chain's current health.

        Synchronous wrapper around the async chain reads — Sentinel's
        ``evaluate_attempt`` is sync today and we don't want this gate
        to force a refactor of every existing caller.
        """
        entry = _CHAIN_REGISTRY.get(chain_id)
        if entry is None:
            return ChainHealthVerdict(
                chain_id=chain_id,
                chain_name=_chain_name_for(chain_id),
                severity="HEALTHY",
                reasons=["chain not gated"],
            )
        try:
            return asyncio.run(self._evaluate_with(chain_id, entry[1]))
        except RuntimeError as exc:
            # ``asyncio.run`` refuses when called from inside a running
            # loop. Surface as a fail-open / fail-closed branch identical
            # to other transport errors so the demo path stays
            # predictable.
            return self._unavailable_verdict(chain_id, f"event-loop conflict: {exc}")

    async def _evaluate_with(
        self, chain_id: int, evaluator: ChainEvaluator
    ) -> ChainHealthVerdict:
        """Run the chain-specific evaluator with timeout + transport defence."""
        # Factory invocation itself can fail (RPC URL unreachable, env var
        # missing, etc) — wrap from the very first line so the fail-open /
        # fail-closed branch covers factory exceptions identically to
        # mid-call transport errors.
        try:
            client_cm = self._client_factory()
        except Exception as exc:  # noqa: BLE001 — last-line transport defence
            return self._unavailable_verdict(chain_id, f"rpc error: {exc}")

        # Two transport shapes are accepted: an async-context-manager
        # (the production HTTP client) and a plain duck-typed client
        # (the test mock — already 'open').
        if hasattr(client_cm, "__aenter__"):
            try:
                async with client_cm as client:
                    return await asyncio.wait_for(
                        evaluator(client), timeout=self._read_timeout_s
                    )
            except TimeoutError:
                return self._unavailable_verdict(chain_id, "rpc timeout")
            except Exception as exc:  # noqa: BLE001 — last-line transport defence
                return self._unavailable_verdict(chain_id, f"rpc error: {exc}")
        try:
            return await asyncio.wait_for(
                evaluator(client_cm), timeout=self._read_timeout_s
            )
        except TimeoutError:
            return self._unavailable_verdict(chain_id, "rpc timeout")
        except Exception as exc:  # noqa: BLE001 — last-line transport defence
            return self._unavailable_verdict(chain_id, f"rpc error: {exc}")

    def _unavailable_verdict(self, chain_id: int, reason: str) -> ChainHealthVerdict:
        """Return the configured fail-open / fail-closed verdict."""
        if self._allow_when_unavailable:
            return ChainHealthVerdict(
                chain_id=chain_id,
                chain_name=_chain_name_for(chain_id),
                severity="HEALTHY",
                reasons=[reason],
            )
        return ChainHealthVerdict(
            chain_id=chain_id,
            chain_name=_chain_name_for(chain_id),
            severity="BLOCK",
            reasons=[f"chain-health unavailable (fail-closed): {reason}"],
        )


# ---------------------------------------------------------------------------
# MegaETH classifier (pure — no I/O)
# ---------------------------------------------------------------------------


def _classify_megaeth(stable: Any, lend: Any) -> ChainHealthVerdict:
    """Pure classifier — composes ``stable_health`` + ``lend_overview`` into a verdict.

    Severity ladder (highest wins):

    * ``BLOCK`` if stable severity >= ``BREAK_100BP`` OR any reserve is
      paused with utilization > 80%.
    * ``WARNING`` if stable severity == ``WARNING_50BP`` OR any reserve
      is frozen.
    * ``HEALTHY`` otherwise.
    """
    reasons: list[str] = []
    paused_reserves: list[str] = []
    peg_divergence: Decimal | None = None
    if stable is not None and getattr(stable, "peg_snapshot", None) is not None:
        peg_divergence = Decimal(stable.peg_snapshot.divergence_bps)

    severity = "HEALTHY"

    # --- stable-side classification ----------------------------------------
    stable_severity: PegBreak | None = getattr(stable, "severity", None)
    if stable_severity is not None and stable_severity in (
        PegBreak.BREAK_100BP,
        PegBreak.CRISIS_500BP,
        PegBreak.CIRCUIT_BREAKER,
    ):
        severity = "BLOCK"
        reasons.append(
            f"USDM depegging: severity={stable_severity.name}, "
            f"divergence={peg_divergence} bps"
        )
    elif stable_severity is PegBreak.WARNING_50BP:
        severity = "WARNING"
        reasons.append(
            f"USDM peg drift: severity={stable_severity.name}, "
            f"divergence={peg_divergence} bps"
        )

    # --- aave-side classification ------------------------------------------
    reserves = list(getattr(lend, "reserves", []) or [])
    paused_high_util: list[str] = []
    frozen: list[str] = []
    for r in reserves:
        if getattr(r, "paused", False):
            paused_reserves.append(r.symbol)
            if getattr(r, "utilization", 0.0) > HIGH_UTILIZATION_BLOCK_THRESHOLD:
                paused_high_util.append(r.symbol)
        if getattr(r, "frozen", False):
            frozen.append(r.symbol)

    if paused_high_util:
        severity = "BLOCK"
        reasons.append(
            f"Aave reserves paused with high utilization (>80%): {paused_high_util}"
        )
    elif severity != "BLOCK" and frozen:
        severity = "WARNING"
        reasons.append(f"Aave reserves frozen: {frozen}")

    if not reasons:
        reasons.append("chain healthy: USDM peg within tolerance, Aave reserves nominal")

    return ChainHealthVerdict(
        chain_id=MEGAETH_CHAIN_ID,
        chain_name=_chain_name_for(MEGAETH_CHAIN_ID),
        severity=severity,
        reasons=reasons,
        peg_divergence_bps=peg_divergence,
        aave_paused_reserves=paused_reserves,
    )


# ---------------------------------------------------------------------------
# Optional default-gate factory — requires ``httpx`` to construct a live
# RPC client. The user is free to ignore this and pass their own factory.
# ---------------------------------------------------------------------------


def default_gate(rpc_url: str = DEFAULT_MEGAETH_RPC_URL) -> ChainHealthGate:
    """Construct a gate against the production MegaETH mainnet RPC.

    The factory closure is what gets re-invoked per ``evaluate_chain``
    call — each call gets a fresh httpx ``AsyncClient`` rather than
    reusing one across long-lived processes, which sidesteps the
    'closed-loop' httpx footgun in test runners.

    NB: the live MegaETH evaluator only works if the user's RPC
    client exposes the duck-typed ``stable_health()`` /
    ``lend_overview()`` async surface. The minimal client shipped
    with this package fetches the raw JSON-RPC envelope but does
    NOT decode contract calls — for the full peg + reserve read
    surface you must either (a) pip install ``sapphire-os`` and pass
    its ``MegaETHProtocols`` instance via a custom factory, or
    (b) supply your own duck-typed client.

    For tests and CI, use ``ChainHealthGate(client_factory=mock_factory)``
    directly with a ``SimpleNamespace``-shaped mock.
    """
    from .rpc_client import HttpJsonRpcClient

    def _factory() -> Any:
        return HttpJsonRpcClient(rpc_url=rpc_url)

    return ChainHealthGate(client_factory=_factory)
