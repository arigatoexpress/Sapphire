"""Arbitrum One branch for the multi-chain Sentinel chain-health gate.

The MegaETH gate (``lib/hackathon/chain_health_gate.py``, PR #546) ships
the dispatch shell + the ``ChainHealthVerdict`` shape. This module is the
chain-specific evaluator for chain id 42161 (Arbitrum One).

It is intentionally split into its own file so this PR (Arbitrum Aave V3
+ GMX V2 read layer) and PR #546 (the gate shell) can land independently —
PR #546 imports this module on merge, no cross-file conflict required.

Severity rules for Arbitrum:

Aave (lending) tier:
  * ``BLOCK``   — any reserve is paused with utilization >
                  :data:`HIGH_UTILIZATION_BLOCK_THRESHOLD` (80%).
                  Paused + high-util means existing borrowers can't be
                  liquidated through normal channels — real cascade risk.
  * ``WARNING`` — any reserve is frozen but no high-util pause.

GMX V2 (perps) tier (added in this PR):
  * ``BLOCK``   — any market with ``abs(funding_apr) > 500%``. Funding
                  that extreme means the order book is one-sided to a
                  degree where new positions are basically prepaid loans
                  to the counterparty; closing existing positions is a
                  last-resort move.
  * ``WARNING`` — any market with ``abs(funding_apr) > 200%``, OR any
                  market with ``abs(oi_skew - 0.5) > 0.45`` (i.e. ≥95%
                  one-sided) AND total OI > $10M.
  * ``HEALTHY`` — perps state nominal.

Final severity is the max of (Aave severity, GMX severity). The
classifier is **pure** — it does no I/O. Composition with a live
``ArbitrumProtocols`` instance is the gate's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

#: Arbitrum One chain id (hex 0xa4b1).
ARBITRUM_CHAIN_ID = 42161

#: BLOCK threshold for paused-reserve utilization. Mirrors the MegaETH
#: gate's threshold so behaviour is consistent across chains.
HIGH_UTILIZATION_BLOCK_THRESHOLD = 0.80

# --- GMX-side severity thresholds ----------------------------------------

#: WARNING threshold on funding APR magnitude. 200% APR = 0.55%/day —
#: extreme but not unheard of in ARB or alt-perp markets during
#: liquidation cascades.
GMX_FUNDING_WARNING_APR = Decimal("2.0")

#: BLOCK threshold on funding APR magnitude. 500% APR = 1.37%/day —
#: at this level the venue is effectively distressed and we should not
#: route any new exposure through it.
GMX_FUNDING_BLOCK_APR = Decimal("5.0")

#: WARNING threshold on OI skew (one-sidedness). 0.95 means one side
#: holds ≥95% of total OI — combined with the size floor below, this is
#: a "thin counterparty side" signal.
GMX_OI_SKEW_WARNING_THRESHOLD = Decimal("0.95")

#: Minimum total OI in USD to consider an OI-skew warning meaningful.
#: Tiny markets routinely run at extreme skews without it mattering.
GMX_OI_SIZE_FLOOR_USD = Decimal("10000000")  # $10M


#: Severity ranking — used to compose the Aave + GMX verdicts.
_SEVERITY_RANK = {"HEALTHY": 0, "WARNING": 1, "BLOCK": 2}


def _max_severity(*severities: str) -> str:
    """Return the most severe of N severity labels (HEALTHY < WARNING < BLOCK)."""
    if not severities:
        return "HEALTHY"
    return max(severities, key=lambda s: _SEVERITY_RANK.get(s, -1))


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
    # GMX-side fields (added in the perps extension PR). Default to
    # empty/None so callers built against the lend-only verdict don't
    # break.
    gmx_funding_warning_markets: list[str] = field(default_factory=list)
    gmx_funding_block_markets: list[str] = field(default_factory=list)
    gmx_skewed_markets: list[str] = field(default_factory=list)


def classify_arbitrum_lend(lend: Any) -> tuple[str, list[str], list[str], list[str]]:
    """Pure Aave-side classifier — split out so the perps extension can compose.

    Returns ``(severity, reasons, paused, frozen)``.

    Kept as its own helper (rather than rolled inline into
    :func:`classify_arbitrum`) so the perps extension's tests can
    exercise the lend tier without re-rolling the same logic and so the
    lend evaluator stays unchanged from its pre-extension behaviour.
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

    return severity, reasons, paused, frozen


def classify_arbitrum_perps(
    perps: Any,
) -> tuple[str, list[str], list[str], list[str], list[str]]:
    """Pure GMX-side classifier — turn a ``PerpsOverview`` into a verdict tier.

    ``perps`` may be any object satisfying the duck-typed contract:

        * ``perps.markets`` is iterable of ``PerpsMarketState``-shaped
          objects with attrs ``state``, ``funding_apr``, ``oi_skew``,
          ``oi_total_usd``, and a nested ``market.name``.

    Returns ``(severity, reasons, funding_warn_names, funding_block_names,
    skew_warn_names)``.

    A market in state other than ``"ok"`` is **skipped silently** (we
    don't have data to judge it). The lend tier is the safety floor; if
    GMX is unreachable the perps verdict simply doesn't escalate.
    """
    markets = list(getattr(perps, "markets", []) or [])

    funding_warn: list[str] = []
    funding_block: list[str] = []
    skew_warn: list[str] = []

    for m in markets:
        state = getattr(m, "state", "")
        if state != "ok":
            continue

        apr = getattr(m, "funding_apr", None)
        skew = getattr(m, "oi_skew", None)
        oi_usd = getattr(m, "oi_total_usd", None)
        name = getattr(getattr(m, "market", None), "name", "?")

        if apr is not None:
            apr_abs = abs(Decimal(apr))
            if apr_abs > GMX_FUNDING_BLOCK_APR:
                funding_block.append(name)
            elif apr_abs > GMX_FUNDING_WARNING_APR:
                funding_warn.append(name)

        if skew is not None and oi_usd is not None:
            skew_dist = abs(Decimal(skew) - Decimal("0.5"))
            # 0.95 one-sided = skew_dist > 0.45
            if (
                skew_dist > (GMX_OI_SKEW_WARNING_THRESHOLD - Decimal("0.5"))
                and Decimal(oi_usd) > GMX_OI_SIZE_FLOOR_USD
            ):
                skew_warn.append(name)

    severity = "HEALTHY"
    reasons: list[str] = []

    if funding_block:
        severity = "BLOCK"
        reasons.append(
            f"GMX markets with extreme funding (>500% APR): {funding_block}"
        )
    if funding_warn:
        severity = _max_severity(severity, "WARNING")
        reasons.append(
            f"GMX markets with elevated funding (>200% APR): {funding_warn}"
        )
    if skew_warn:
        severity = _max_severity(severity, "WARNING")
        reasons.append(
            f"GMX markets one-sided (>=95% OI skew with >$10M OI): {skew_warn}"
        )

    return severity, reasons, funding_warn, funding_block, skew_warn


def classify_arbitrum(
    lend: Any,
    perps: Any | None = None,
) -> ArbitrumChainHealthVerdict:
    """Pure classifier — turn Aave + (optional) GMX state into a verdict.

    ``lend`` may be any object satisfying ``lend.reserves`` iterable of
    ``.symbol``/``.paused``/``.frozen``/``.utilization`` records.

    ``perps`` is optional — when ``None``, only the lend tier is
    evaluated (preserves the pre-extension behaviour exactly). When
    supplied, the GMX tier is composed in and the final severity is the
    max of the two.
    """
    lend_sev, lend_reasons, paused, frozen = classify_arbitrum_lend(lend)

    perps_sev = "HEALTHY"
    perps_reasons: list[str] = []
    funding_warn: list[str] = []
    funding_block: list[str] = []
    skew_warn: list[str] = []

    if perps is not None:
        (
            perps_sev,
            perps_reasons,
            funding_warn,
            funding_block,
            skew_warn,
        ) = classify_arbitrum_perps(perps)

    severity = _max_severity(lend_sev, perps_sev)
    reasons = list(lend_reasons) + list(perps_reasons)

    if not reasons:
        reasons = ["chain healthy: Aave reserves nominal" + (
            ", GMX perps nominal" if perps is not None else ""
        )]

    return ArbitrumChainHealthVerdict(
        chain_id=ARBITRUM_CHAIN_ID,
        chain_name="Arbitrum One",
        severity=severity,
        reasons=reasons,
        aave_paused_reserves=paused,
        aave_frozen_reserves=frozen,
        gmx_funding_warning_markets=funding_warn,
        gmx_funding_block_markets=funding_block,
        gmx_skewed_markets=skew_warn,
    )


async def evaluate_arbitrum_chain_health(
    client: Any,
    *,
    include_perps: bool = True,
) -> ArbitrumChainHealthVerdict:
    """Compose the live read with the pure classifier.

    Builds an :class:`ArbitrumProtocols` against the supplied client,
    pulls ``lend_overview()`` (and ``perps_overview()`` if
    ``include_perps``), and runs the classifier. The gate shell in
    PR #546 is responsible for the timeout-wrapping +
    fail-open/fail-closed behaviour around this call.

    ``include_perps`` defaults to ``True`` post-extension. Callers that
    want the legacy lend-only behaviour can opt out with
    ``include_perps=False`` — the lend evaluator's behaviour is
    unchanged from the pre-extension version.
    """
    # Late import — keeps ``lib.hackathon`` from pulling the chain
    # access layer at module import time.
    from lib.chains.arbitrum.protocols import ArbitrumProtocols  # noqa: PLC0415

    proto = ArbitrumProtocols(client)
    lend = await proto.lend_overview()

    perps = None
    if include_perps:
        try:
            perps = await proto.perps_overview()
        except Exception:  # noqa: BLE001
            # Soft-fail the perps tier — the lend tier is the safety
            # floor and we don't want a transient GMX RPC issue to
            # silently fail-closed the chain-health verdict. The gate
            # shell in PR #546 owns the wider fail-open/closed call.
            perps = None

    return classify_arbitrum(lend, perps=perps)
