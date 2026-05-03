"""Optimism mainnet branch for the multi-chain Sentinel chain-health gate.

The MegaETH gate (``lib/hackathon/chain_health_gate.py``) ships the
dispatch shell + the ``ChainHealthVerdict`` shape. This module is the
chain-specific evaluator for chain id 10 (Optimism mainnet).

It is intentionally split into its own file so the dispatcher can route
to it without pulling the lib.chains.optimism import chain at module-load
time.

Severity rules for Optimism:

* ``BLOCK`` — any reserve is paused with utilization >
  :data:`HIGH_UTILIZATION_BLOCK_THRESHOLD` (default 80%). A paused +
  high-utilization reserve means existing borrowers can't be liquidated
  through normal channels: real risk-of-cascade.
* ``WARNING`` — any reserve is frozen but no high-util pause; OR Pyth
  reports a stale reading on a major (>1h since publish_time on
  BTC/ETH/USDC). Frozen reserves still allow repayment / withdrawal;
  stale Pyth reads degrade the gate's redundancy without breaking the
  primary path. Surface to the operator but do not refuse the payment.
* ``HEALTHY`` — Aave reserves nominal AND Pyth fresh (or unavailable
  but Aave OK).

Pyth (added in the follow-up to PR #569) is a *fallback* oracle: when
the Aave oracle reverts on an asset that Pyth does cover, the gate
prefers Pyth and continues instead of treating the chain as unpriced.
Pyth-only data does not change the Aave reserve verdict — it only
supplements with redundancy + staleness telemetry.

The classifier is **pure** — it does no I/O. Composition with a live
``OptimismProtocols`` instance is the gate's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Optimism mainnet chain id (hex 0xa).
OPTIMISM_CHAIN_ID = 10

#: BLOCK threshold for paused-reserve utilization. Mirrors the Arbitrum +
#: MegaETH gates' threshold so behaviour is consistent across chains.
HIGH_UTILIZATION_BLOCK_THRESHOLD = 0.80

#: Pyth feeds we expect to read for the Optimism health probe. These
#: are the assets where Aave + Pyth overlap on Optimism — losing fresh
#: telemetry on any of these means Sentinel's redundancy is degraded.
#: Order matters only for which one logs first if multiple stale.
PYTH_PROBE_SYMBOLS = ("BTC", "ETH", "USDC")


@dataclass(frozen=True)
class OptimismChainHealthVerdict:
    """Stand-in verdict shape for tests + dispatcher integration.

    Field shape mirrors the Arbitrum-side ``ArbitrumChainHealthVerdict``
    and the MegaETH-side ``ChainHealthVerdict`` exactly — the dispatcher
    in :mod:`lib.hackathon.chain_health_gate` constructs its own
    ``ChainHealthVerdict`` from these fields rather than importing this
    dataclass directly. We keep our own copy so unit tests here don't
    require the dispatcher to be loaded.

    The two ``pyth_*`` fields are Optimism-specific telemetry added by
    the PR-after-#569 Pyth wiring. They're optional metadata for
    operator dashboards — the dispatcher copies them onto the
    ``ChainHealthVerdict`` only when present, so older callers keep
    working unchanged.
    """

    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str] = field(default_factory=list)
    aave_paused_reserves: list[str] = field(default_factory=list)
    aave_frozen_reserves: list[str] = field(default_factory=list)
    pyth_stale_symbols: list[str] = field(default_factory=list)
    pyth_fresh_symbols: list[str] = field(default_factory=list)


def classify_optimism(
    lend: Any,
    pyth_readings: list[Any] | None = None,
) -> OptimismChainHealthVerdict:
    """Pure classifier — turn an Optimism ``LendOverview`` (+ optional Pyth
    readings) into a verdict.

    ``lend`` may be any object satisfying the duck-typed contract:
    ``lend.reserves`` is iterable, each item exposes ``.symbol``,
    ``.paused``, ``.frozen``, and ``.utilization``. Both the
    ``OptimismProtocols.lend_overview()`` return and a hand-rolled test
    stub satisfy this.

    ``pyth_readings`` is the optional list of
    :class:`~lib.chains.optimism.contracts.pyth_oracle.PythRegistryPrice`
    records (or any object with ``.symbol`` and ``.stale`` attributes)
    for the major-feed probe symbols. When supplied:

    * Each fresh reading appends to ``pyth_fresh_symbols`` (telemetry).
    * Each stale reading appends to ``pyth_stale_symbols`` AND lifts
      severity to at least ``WARNING`` (never overrides ``BLOCK``).

    Pyth degradation never escalates above ``WARNING``: Aave is still
    the primary on-chain source; losing the fallback is a soft signal.
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

    pyth_fresh: list[str] = []
    pyth_stale: list[str] = []
    for reading in pyth_readings or ():
        sym = str(getattr(reading, "symbol", "") or "")
        if not sym:
            continue
        if getattr(reading, "stale", False):
            pyth_stale.append(sym)
        else:
            pyth_fresh.append(sym)

    severity = "HEALTHY"
    reasons: list[str] = []

    if paused_high_util:
        severity = "BLOCK"
        reasons.append(f"Aave reserves paused with high utilization (>80%): {paused_high_util}")
    elif frozen:
        severity = "WARNING"
        reasons.append(f"Aave reserves frozen: {frozen}")
    elif pyth_stale:
        # Pyth-only degradation — Aave nominal, Pyth fallback stale.
        severity = "WARNING"
        reasons.append(f"Pyth fallback stale on {pyth_stale} (>1h)")
    else:
        reasons.append("chain healthy: Aave reserves nominal")
        if pyth_fresh:
            reasons.append(f"Pyth fallback fresh on {pyth_fresh}")

    # If we BLOCKed on Aave but Pyth is also stale, still surface Pyth
    # in reasons — operators want both axes when triaging.
    if severity == "BLOCK" and pyth_stale or severity == "WARNING" and frozen and pyth_stale:
        reasons.append(f"Pyth fallback also stale on {pyth_stale}")

    return OptimismChainHealthVerdict(
        chain_id=OPTIMISM_CHAIN_ID,
        chain_name="Optimism",
        severity=severity,
        reasons=reasons,
        aave_paused_reserves=paused,
        aave_frozen_reserves=frozen,
        pyth_stale_symbols=pyth_stale,
        pyth_fresh_symbols=pyth_fresh,
    )


async def _probe_pyth(proto: Any, symbols: tuple[str, ...]) -> list[Any]:
    """Best-effort: read each symbol from Pyth, returning whatever succeeded.

    Soft-fail on every axis — RPC timeout, contract revert, missing
    priceId, non-positive price all silently drop the reading. The
    classifier only sees readings that succeeded; a chain with zero
    Pyth coverage simply has no Pyth telemetry, not a hard error.
    """
    out: list[Any] = []
    pyth = getattr(proto, "pyth", None)
    if pyth is None:
        return out
    for sym in symbols:
        try:
            out.append(await pyth.fetch_price(sym))
        except Exception:  # noqa: BLE001 — Pyth is the fallback, never the gate
            continue
    return out


async def evaluate_optimism_chain_health(client: Any) -> OptimismChainHealthVerdict:
    """Compose the live reads with the pure classifier.

    Builds an :class:`OptimismProtocols` against the supplied client,
    pulls ``lend_overview()`` AND probes Pyth for the major-feed
    symbols, then runs the classifier with both. The dispatcher in
    :mod:`lib.hackathon.chain_health_gate` is responsible for the
    timeout-wrapping + fail-open/fail-closed behaviour around this call.

    Aave-revert fallback: if ``lend_overview()`` raises (the Aave
    oracle reverts on a known asset, the most common live failure
    mode), AND we have at least one fresh Pyth reading on a major,
    surface a WARNING-severity verdict instead of bubbling the error.
    Sentinel can then continue operating with degraded confidence
    rather than freezing the whole gate. If neither source returns,
    re-raise so the dispatcher's outer fail-closed logic kicks in.
    """
    # Late import — keeps lib.hackathon from pulling the chain access
    # layer at module import time.
    from lib.chains.optimism.protocols import OptimismProtocols  # noqa: PLC0415

    proto = OptimismProtocols(client)

    # Probe Pyth first — cheap, fully concurrent in spirit (we keep it
    # sequential here for predictable error semantics; multicall is a
    # follow-up).
    pyth_readings = await _probe_pyth(proto, PYTH_PROBE_SYMBOLS)

    try:
        lend = await proto.lend_overview()
    except Exception as exc:
        # Aave path failed. If Pyth gave us at least one fresh reading
        # on a major asset, treat the chain as WARNING (degraded but
        # not blind) and surface the Aave error in reasons.
        fresh = [r for r in pyth_readings if not getattr(r, "stale", True)]
        if not fresh:
            raise
        return OptimismChainHealthVerdict(
            chain_id=OPTIMISM_CHAIN_ID,
            chain_name="Optimism",
            severity="WARNING",
            reasons=[
                f"Aave read failed: {type(exc).__name__}: {exc}",
                f"Pyth fallback active on {[str(r.symbol) for r in fresh]}",
            ],
            pyth_fresh_symbols=[str(r.symbol) for r in fresh],
            pyth_stale_symbols=[
                str(r.symbol) for r in pyth_readings if getattr(r, "stale", False)
            ],
        )

    return classify_optimism(lend, pyth_readings=pyth_readings)
