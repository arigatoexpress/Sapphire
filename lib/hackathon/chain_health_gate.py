"""Multi-chain health gate for Sapphire Sentinel.

Sentinel already screens payments on policy axes (mandate, budget, domain
allow-list, prompt-injection, secret-egress). This module adds one more
axis: the *chain state the alpha references must not be in distress*.

If the alpha's underlying chain has USDM depegging, an Aave reserve frozen,
or a paused high-utilization reserve, paying for that signal is wasteful
at best and adversarial at worst — the chain is currently un-tradeable.

The gate is **fail-open by default** (``allow_when_unavailable=True``) so a
flaky RPC at demo time doesn't block legitimate payments. We block only on
*observed* distress, never on absence of evidence.

Wave A only knows MegaETH (chain 4326). Other chain IDs short-circuit to
HEALTHY with a "chain not gated" reason — Sentinel never blocks a chain
the gate doesn't know how to read.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from lib.chains.megaeth.contracts.peg_monitor import PegBreak
from lib.chains.megaeth.protocols import MegaETHProtocols
from lib.hackathon.chain_health_price_source import (
    ChainHealthPriceResolver,
    PriceSource,
    ResolvedPrice,
)

#: Chain IDs the gate knows how to evaluate. Anything else returns HEALTHY.
MEGAETH_CHAIN_ID = 4326

#: Symbols the gate consults for price-source freshness on MegaETH.
#: Wave A only checks BTC because that was the asset PR #621 surfaced as
#: 25-day-stale on Optimism — extending to ETH/SOL is a one-line change
#: but adds extra Hermes round-trips on the gate critical path.
MEGAETH_PRICE_SOURCE_SYMBOL = "BTC"

#: Per-read timeout. The gate calls 2 reads (stable_health, lend_overview).
#: Keep this small — the gate sits in the Sentinel critical path and a slow
#: RPC must not stall a payment evaluation.
DEFAULT_READ_TIMEOUT_S = 3.0

#: Default mainnet RPC URL. Mirrors the plugin tool default.
DEFAULT_MEGAETH_RPC_URL = "https://mainnet.megaeth.com/rpc"

#: Aave-side BLOCK threshold: a paused reserve isn't itself a crisis, but a
#: paused reserve with >80% utilization means existing borrowers can't be
#: liquidated through normal channels — a real risk-of-cascade signal.
HIGH_UTILIZATION_BLOCK_THRESHOLD = 0.80


@dataclass(frozen=True)
class ChainHealthVerdict:
    """Severity classification + supporting evidence for one chain.

    Field shape mirrors :class:`SentinelDecision` so it embeds cleanly:

    * ``severity`` — one of ``HEALTHY``/``WARNING``/``BLOCK``. Sentinel
      only refuses on ``BLOCK``; ``WARNING`` is surface-only.
    * ``reasons`` — human-readable strings the dashboard renders next
      to the existing policy reasons.
    * ``peg_divergence_bps`` — the actual measured spread when a stable
      health read succeeded; ``None`` when MegaETH wasn't gated or the
      read failed.
    * ``aave_paused_reserves`` — symbol list, surfaced even on WARNING
      so judges can see *which* reserve is degraded.
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str] = field(default_factory=list)
    peg_divergence_bps: Decimal | None = None
    aave_paused_reserves: list[str] = field(default_factory=list)


class ChainHealthGate:
    """Sentinel-aware chain-health classifier.

    Constructor:

    * ``client_factory`` — zero-arg callable returning a fresh
      MegaETH-shaped JSON-RPC client. Factory pattern (instead of a
      live client) means tests can inject a mock and the gate doesn't
      hold an open httpx session for the entire process lifetime.
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
        price_resolver: ChainHealthPriceResolver | None = None,
    ) -> None:
        """Construct the gate.

        ``price_resolver`` is the Hermes-primary + on-chain-fallback
        price resolver shared across every per-chain branch — when the
        gate process owns a single resolver, all branches see the same
        Hermes connection pool and the same fresh / stale decision
        timeline. ``None`` means no price-source axis is consulted (the
        gate falls back to peg + Aave classification only); pass
        :func:`shared_price_resolver` to wire the singleton in.
        """
        self._client_factory = client_factory
        self._allow_when_unavailable = allow_when_unavailable
        self._read_timeout_s = read_timeout_s
        self._price_resolver = price_resolver

    def evaluate_chain(self, chain_id: int) -> ChainHealthVerdict:
        """Classify a chain's current health.

        Synchronous wrapper around the async chain reads — Sentinel's
        ``evaluate_attempt`` is sync today and we don't want this gate
        to force a refactor of every existing caller.
        """
        if chain_id != MEGAETH_CHAIN_ID:
            return ChainHealthVerdict(
                chain_id=chain_id,
                chain_name=_chain_name_for(chain_id),
                severity="HEALTHY",
                reasons=["chain not gated"],
            )
        try:
            return asyncio.run(self._evaluate_megaeth())
        except RuntimeError as exc:
            # ``asyncio.run`` refuses when called from inside a running loop.
            # Surface as a fail-open / fail-closed branch identical to other
            # transport errors so the demo path stays predictable.
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, f"event-loop conflict: {exc}")

    async def _evaluate_megaeth(self) -> ChainHealthVerdict:
        """Run the two reads against MegaETH and compose a verdict."""
        client_cm = self._client_factory()
        # Two transport shapes are accepted: an async-context-manager (the
        # production HTTP client) and a plain duck-typed client (the test
        # mock — already 'open'). Both reach the same ``MegaETHProtocols``
        # surface; the only difference is whether we ``__aenter__`` it.
        if hasattr(client_cm, "__aenter__"):
            try:
                async with client_cm as client:
                    return await self._read_with_client(client)
            except Exception as exc:  # noqa: BLE001 — last-line transport defence
                return self._unavailable_verdict(MEGAETH_CHAIN_ID, f"rpc error: {exc}")
        try:
            return await self._read_with_client(client_cm)
        except Exception as exc:  # noqa: BLE001 — last-line transport defence
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, f"rpc error: {exc}")

    async def _read_with_client(self, client: Any) -> ChainHealthVerdict:
        """Pull stable_health + lend_overview, classify, return verdict.

        If a price resolver is wired, it is consulted in parallel with
        the on-chain reads (Hermes is HTTP, the on-chain reads are
        JSON-RPC — they share no resources) and its severity
        contribution is composed into the final verdict.
        """
        proto = MegaETHProtocols(client)

        try:
            stable = await asyncio.wait_for(
                proto.stable_health(), timeout=self._read_timeout_s
            )
        except TimeoutError:
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, "rpc timeout (stable_health)")
        except Exception as exc:  # noqa: BLE001
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, f"stable_health failed: {exc}")

        try:
            lend = await asyncio.wait_for(
                proto.lend_overview(), timeout=self._read_timeout_s
            )
        except TimeoutError:
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, "rpc timeout (lend_overview)")
        except Exception as exc:  # noqa: BLE001
            return self._unavailable_verdict(MEGAETH_CHAIN_ID, f"lend_overview failed: {exc}")

        # Price-source resolution is *additive* — it never overrides the
        # peg + Aave verdict, only augments it. Run after the on-chain
        # reads (rather than concurrently) because the resolver is
        # already fail-open and quick (5s Hermes timeout, no on-chain
        # call when use_onchain_only=False), and serial keeps the
        # exception story straightforward.
        resolved = self._resolve_price_or_none()
        return _classify(stable, lend, resolved=resolved)

    def _resolve_price_or_none(self) -> ResolvedPrice | None:
        """Consult the resolver if one is wired, swallow defensively.

        The resolver is *itself* fail-open, but a misconfigured resolver
        (e.g. wrong symbol map, broken httpx wiring) must still never
        propagate an exception out of the gate. This method is the
        last-line catch.
        """
        if self._price_resolver is None:
            return None
        try:
            return self._price_resolver.resolve(MEGAETH_PRICE_SOURCE_SYMBOL)
        except Exception:  # noqa: BLE001 — resolver should not raise; if it does, drop the axis
            return None

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


def _chain_name_for(chain_id: int) -> str:
    if chain_id == MEGAETH_CHAIN_ID:
        return "MegaETH"
    return f"chain-{chain_id}"


def _classify(
    stable: Any,
    lend: Any,
    *,
    resolved: ResolvedPrice | None = None,
) -> ChainHealthVerdict:
    """Pure classifier — composes ``stable_health`` + ``lend_overview`` into a verdict.

    Severity ladder (highest wins):

    * ``BLOCK`` if stable severity >= ``BREAK_100BP`` OR any reserve is
      paused with utilization > 80%.
    * ``WARNING`` if stable severity == ``WARNING_50BP`` OR any reserve
      is frozen.
    * ``HEALTHY`` otherwise.

    When a :class:`ResolvedPrice` is provided, its
    ``severity_contribution`` is composed with the same highest-wins
    ladder — a price-source ``WARNING`` lifts a ``HEALTHY`` verdict to
    ``WARNING`` but never lowers a ``BLOCK``. Price-source reasons are
    appended to the verdict reasons so the dashboard can render *which
    source* is in use (HERMES_PRIMARY in the canonical case;
    ON_CHAIN_FALLBACK / BOTH_STALE / NO_FALLBACK_AVAILABLE in degraded
    cases). This is the fix for the PR #621 false-positive scenario:
    when Hermes is fresh, the verdict no longer flags WARNING for a
    25-day-stale on-chain cache because Hermes is the ground truth.
    """
    reasons: list[str] = []
    paused_reserves: list[str] = []
    peg_divergence: Decimal | None = None
    if stable is not None and getattr(stable, "peg_snapshot", None) is not None:
        peg_divergence = Decimal(stable.peg_snapshot.divergence_bps)

    severity = "HEALTHY"

    # --- stable-side classification -----------------------------------------
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

    # --- aave-side classification -------------------------------------------
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

    # --- price-source augmentation -----------------------------------------
    # The resolver's severity contribution is composed with the same
    # highest-wins ladder. We *only* accept HEALTHY / WARNING from the
    # resolver — price-source degradation is never grounds for BLOCK
    # (the chain may still be perfectly tradeable on the peg + Aave
    # axes; refusing payments because hermes.pyth.network is down is a
    # bigger user-impact incident than the data-quality problem we'd be
    # protecting against).
    if resolved is not None:
        if resolved.severity_contribution == "WARNING" and severity == "HEALTHY":
            severity = "WARNING"
        # Always append the price-source reasons so the dashboard can
        # render the source state, even when severity didn't change.
        # In the canonical Hermes-fresh case ``resolved.reasons`` is
        # empty — append a single-line "using Hermes" so the dashboard
        # still reflects which source the gate trusted, which closes
        # the PR #621 loop visibly to the operator.
        if resolved.reasons:
            reasons.extend(resolved.reasons)
        elif resolved.source == PriceSource.HERMES_PRIMARY:
            reasons.append(
                f"price-source: Hermes primary ({resolved.symbol} fresh, "
                f"age {resolved.age_s}s)"
            )

    return ChainHealthVerdict(
        chain_id=MEGAETH_CHAIN_ID,
        chain_name=_chain_name_for(MEGAETH_CHAIN_ID),
        severity=severity,
        reasons=reasons,
        peg_divergence_bps=peg_divergence,
        aave_paused_reserves=paused_reserves,
    )


def _load_megaeth_rpc_client_class() -> Any:
    """Load ``_HttpJsonRpcClient`` from the plugin tool file.

    The plugin directory is ``plugins/claw-sapphire`` (hyphenated), which
    is not a valid Python package name. We therefore load the tool
    module by file path rather than relying on ``import``.

    Cached on the module so repeated ``default_gate()`` calls don't
    re-spec the file every time.
    """
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    cached = getattr(_load_megaeth_rpc_client_class, "_cached", None)
    if cached is not None:
        return cached

    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "internal"
        / "megaeth_protocols.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_sentinel_megaeth_rpc_client", str(module_path)
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"could not load megaeth_protocols plugin module from {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    klass = module._HttpJsonRpcClient
    _load_megaeth_rpc_client_class._cached = klass  # type: ignore[attr-defined]
    return klass


#: Module-level price resolver, shared across every per-chain gate
#: constructed via :func:`shared_price_resolver`. Lazily constructed on
#: first access so a unit test that never exercises price-source logic
#: doesn't pay the (tiny) cost of building a Hermes client.
_SHARED_PRICE_RESOLVER: ChainHealthPriceResolver | None = None


def shared_price_resolver() -> ChainHealthPriceResolver:
    """Return the process-wide price resolver, constructing on first call.

    The lane prompt explicitly calls for the Hermes client to be
    *singleton, shared across all 3 chain gates* — this is the
    accessor that the per-chain gate factories call in. Threading the
    same resolver instance through every gate means every chain's
    evaluation sees the same ``httpx.Client`` connection pool and the
    same Hermes responses (within the resolver's own freshness window).

    Tests can replace the singleton via :func:`reset_price_resolver` to
    avoid leaking a real Hermes client into the test process.
    """
    global _SHARED_PRICE_RESOLVER
    if _SHARED_PRICE_RESOLVER is None:
        _SHARED_PRICE_RESOLVER = ChainHealthPriceResolver()
    return _SHARED_PRICE_RESOLVER


def reset_price_resolver(resolver: ChainHealthPriceResolver | None = None) -> None:
    """Replace (or clear) the shared price resolver — testing only.

    Pass a pre-built resolver to inject a fake Hermes client; pass
    ``None`` to clear the singleton (the next ``shared_price_resolver``
    call will rebuild a default).
    """
    global _SHARED_PRICE_RESOLVER
    _SHARED_PRICE_RESOLVER = resolver


def default_gate(rpc_url: str = DEFAULT_MEGAETH_RPC_URL) -> ChainHealthGate:
    """Construct a gate against the production MegaETH mainnet RPC.

    The factory closure is what gets re-invoked per ``evaluate_chain``
    call — each call gets a fresh httpx ``AsyncClient`` rather than
    reusing one across long-lived processes, which sidesteps the
    'closed-loop' httpx footgun in test runners.

    The default gate also wires the shared :func:`shared_price_resolver`
    into the ``price_resolver`` slot, so every chain branch the gate
    evaluates consults the same Hermes client. Callers that don't want
    the price-source axis (e.g. environments without internet egress)
    can construct ``ChainHealthGate`` directly with ``price_resolver=None``.
    """
    client_cls = _load_megaeth_rpc_client_class()

    def _factory() -> Any:
        return client_cls(rpc_url=rpc_url)

    return ChainHealthGate(
        client_factory=_factory,
        price_resolver=shared_price_resolver(),
    )
