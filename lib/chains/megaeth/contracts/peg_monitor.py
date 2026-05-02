"""Peg-health classifier and circuit-breaker primitive for USDM.

Pure stateless utilities that turn a :class:`~lib.chains.megaeth.
contracts.usdm.PegQuote` snapshot into a severity classification and
a leverage-block decision. No I/O — every method takes a snapshot
and returns a typed value. Wiring to the live USDM wrapper happens
at the facade layer in :mod:`lib.chains.megaeth.protocols`.

Why this lives at the protocol-access layer (and not inside the
executor): the dashboard, signal-logger, and ``strategy_lab`` all
need the same classification — same thresholds, same decision rule.
Putting it here means each consumer reuses one tested primitive
instead of inventing its own bps boundary.

THRESHOLD CALIBRATION
=====================

The bps thresholds below are conservative defaults for a stable that
should sit at $1.00 :

  * **HEALTHY (< 25 bps)** — within the Aave V3 default
    ``priceDeviationThreshold`` for stablecoins.
  * **WARNING_50BP (25-100 bps)** — divergence visible in the
    lowest-liquidity venue. Don't auto-block, but surface to the
    operator. Live readings on TGE day were ~7-8 bps so this is
    well above the resting noise floor.
  * **BREAK_100BP (100-500 bps)** — divergence has crossed the
    AAVE liquidation buffer. New leverage MUST refuse.
  * **CRISIS_500BP (500-1500 bps)** — clear depeg. Existing leveraged
    positions are inside their liquidation cascade window — strategy
    code should also refuse to *increase* exposure to USDM.
  * **CIRCUIT_BREAKER (>= 1500 bps)** — stop everything.

These defaults are the *protocol-access* defaults. Strategies are
free to gate at tighter values via the ``min_severity_to_block``
argument to :func:`should_block_trade`, but they cannot override
the breaker's own honesty about the spread itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum

from .usdm import USDM, PegQuote


class PegBreak(IntEnum):
    """Severity of USDM peg deviation. Higher == more severe.

    The IntEnum subclass means callers can compare with the natural
    ``severity >= PegBreak.BREAK_100BP`` shape, which is the default
    leverage-block threshold.
    """

    HEALTHY = 0
    WARNING_50BP = 1
    BREAK_100BP = 2
    CRISIS_500BP = 3
    CIRCUIT_BREAKER = 4


#: Default thresholds in bps. Inclusive lower bound, exclusive upper bound.
#: Tuples are (severity, lower_bound_bps).
_SEVERITY_LADDER: tuple[tuple[PegBreak, Decimal], ...] = (
    (PegBreak.CIRCUIT_BREAKER, Decimal(1500)),
    (PegBreak.CRISIS_500BP, Decimal(500)),
    (PegBreak.BREAK_100BP, Decimal(100)),
    (PegBreak.WARNING_50BP, Decimal(25)),
)


def classify_divergence(divergence_bps: Decimal | int | float) -> PegBreak:
    """Map a divergence reading (in bps) to a :class:`PegBreak`.

    Negative inputs are clamped to zero (the spread is always
    non-negative as computed by ``divergence_bps`` in :mod:`usdm`).
    """
    spread = Decimal(divergence_bps) if not isinstance(divergence_bps, Decimal) else divergence_bps
    if spread < 0:
        spread = Decimal(0)
    for severity, lower in _SEVERITY_LADDER:
        if spread >= lower:
            return severity
    return PegBreak.HEALTHY


@dataclass(frozen=True)
class PegSnapshot:
    """Composed snapshot — peg quotes + classified severity.

    This is the single object Wave C strategy code receives from
    ``MegaETHProtocols.peg_status()``. It carries the underlying
    :class:`PegQuote` for callers that want the raw per-source prices,
    plus the derived ``severity`` for the gate decision.
    """

    usdm_kumbaya_usdt0: Decimal | None
    usdm_aave_oracle: Decimal | None
    usdm_twap60: Decimal | None
    usdm_implied_via_eth_oracle: Decimal | None
    divergence_bps: Decimal
    severity: PegBreak
    sources_present: int
    timestamp_unix: int = 0

    @classmethod
    def from_quote(cls, quote: PegQuote) -> PegSnapshot:
        return cls(
            usdm_kumbaya_usdt0=quote.kumbaya_usdt0,
            usdm_aave_oracle=quote.aave_oracle_usd,
            usdm_twap60=quote.twap60_usd,
            usdm_implied_via_eth_oracle=quote.eth_oracle_usd,
            divergence_bps=quote.divergence_bps,
            severity=classify_divergence(quote.divergence_bps),
            sources_present=quote.sources_present,
            timestamp_unix=quote.timestamp_unix,
        )

    def is_healthy(self) -> bool:
        return self.severity == PegBreak.HEALTHY


class PegMonitor:
    """Stateless evaluator that composes :class:`USDM` reads into a snapshot.

    No instance state — methods are bound here for namespacing and
    so callers can pass a custom subclass for testing without monkey-
    patching the module. Construct freely.

    Wired into :class:`~lib.chains.megaeth.protocols.MegaETHProtocols`
    via the facade's ``stable_health`` and ``peg_status`` methods.
    """

    async def evaluate(
        self,
        usdm: USDM,
        *,
        kumbaya_quote_fn: object | None = None,
        aave_oracle_call_fn: object | None = None,
    ) -> PegSnapshot:
        """Compose a :class:`PegSnapshot` from a :class:`USDM` instance.

        ``kumbaya_quote_fn`` and ``aave_oracle_call_fn`` are forwarded
        to :meth:`USDM.peg_quote` — see that method's docstring for
        the contract. Both are optional; missing sources reduce
        ``sources_present`` but do not error.

        Pure function w.r.t. the wrapper — no monkey-patching, no
        side effects, no caching. Re-call to refresh.
        """
        quote = await usdm.peg_quote(
            kumbaya_quote_fn=kumbaya_quote_fn,
            aave_oracle_call_fn=aave_oracle_call_fn,
        )
        return PegSnapshot.from_quote(quote)

    @staticmethod
    def should_block_trade(
        snapshot: PegSnapshot,
        *,
        min_severity_to_block: PegBreak = PegBreak.BREAK_100BP,
        require_sources: int = 2,
    ) -> tuple[bool, str]:
        """Decide whether a leveraged action should be refused.

        Returns ``(True, reason_string)`` if the action should NOT
        proceed. The reason is human-readable and intended for direct
        log output / Telegram alert / dashboard display.

        ``min_severity_to_block`` is the lowest severity that
        triggers a block. Default ``BREAK_100BP`` (>= 100 bps spread)
        matches the protocol-map's prescription for "peg deviation
        > 30 bps → ``chain.regime.shift`` event-bus emit" with a
        2x cushion on top of the regime-shift signal.

        ``require_sources`` is the minimum number of independent
        peg sources that must report a price for the breaker to
        treat the snapshot as actionable. If we only have one
        source live, we **block by default** — single-source
        readings can be manipulated, and the conservative posture
        on a leverage decision is to refuse.
        """
        if snapshot.sources_present < require_sources:
            return (
                True,
                (
                    f"insufficient peg sources: {snapshot.sources_present} present, "
                    f"need {require_sources} for an actionable read"
                ),
            )
        if snapshot.severity >= min_severity_to_block:
            return (
                True,
                (
                    f"USDM peg severity {snapshot.severity.name} "
                    f"({snapshot.divergence_bps:.1f} bps spread across "
                    f"{snapshot.sources_present} sources) >= "
                    f"block threshold {min_severity_to_block.name}"
                ),
            )
        return (
            False,
            (
                f"USDM peg HEALTHY ({snapshot.divergence_bps:.1f} bps spread, "
                f"severity {snapshot.severity.name}, "
                f"{snapshot.sources_present} sources)"
            ),
        )
