"""Price-source resolver for the Sentinel chain-health gate.

Background
==========

PR #621 surfaced a class of failure mode in the multi-chain Pyth
divergence detector: on-chain Pyth caches can lag arbitrarily because
they only refresh when a keeper pays gas to call ``updatePriceFeeds``.
On a chain with sparse keepers — Optimism BTC at the time of PR #621 was
**25 days stale** — the on-chain "price" the gate observes is not a
recent price observation, it's a fossilised snapshot from weeks ago.

A chain-health gate that classifies severity based on *that* snapshot
will produce two kinds of false positives:

* a true off-chain move that has not yet been keeper-pushed onto the
  chain looks like the chain is "fine" (HEALTHY) when in fact every
  contract reading the on-chain price is mispricing — equally, a fresh
  off-chain price will look like it disagrees with the on-chain cache
  by 1066 bps when there is no real disagreement at all
* a stale on-chain cache cannot be distinguished from real chain
  distress without an external reference

PR #625 (``lib.chains.cross_chain.pyth_hermes``) added an off-chain
Hermes client that hits ``hermes.pyth.network`` directly and returns the
canonical, sub-second-fresh price the on-chain keepers themselves read
from. This module is the bridge between PR #625's Hermes client and the
chain-health gate's severity calculation:

* **Hermes is the *primary* price source** — fresh by definition,
  ground truth for every payment-evaluation severity decision.
* **On-chain Pyth remains the *secondary* source** — useful when an
  *atomic* flow needs the price to be on-chain at the moment of contract
  execution (settlement / liquidation paths that pay gas to refresh the
  cache so a downstream contract reads the new price in the same tx).
* **Settlement flows opt out of Hermes** with ``use_onchain_only=True``
  — those callers genuinely need the on-chain value, even if it's stale,
  because that's the value the contract will actually use.

The shape this module gives the gate
====================================

``ChainHealthPriceResolver.resolve(...)`` returns a
:class:`ResolvedPrice` describing *which source* won, *how fresh* it is,
and *what severity contribution* the price-source state should make to
the surrounding gate verdict. The gate composes that contribution into
its final verdict (it never *overrides* the gate's existing peg-monitor
or Aave classification — it only *augments* it).

The five scenarios the gate must handle (covered by
``tests/unit/test_chain_health_hermes_primary.py``):

#. **Hermes fresh, on-chain stale** — Hermes wins, severity unaffected
   (the stale on-chain cache is a known-OK condition when Hermes is
   available). ``ResolvedPrice.source == HERMES_PRIMARY``.
#. **Hermes stale, on-chain fresh** — fall back to on-chain, but raise a
   ``WARNING`` reason on the verdict because Hermes being stale is itself
   unusual and worth surfacing.
#. **Both stale** — ``ResolvedPrice.source == BOTH_STALE``, severity
   contribution is ``WARNING`` (the price source is unreliable on this
   chain right now, but the gate's other axes — peg monitor, Aave —
   may still be fine).
#. **Hermes API timeout / network error** — caught here; we fall back
   to on-chain identically to the "Hermes stale" path. The gate never
   sees the exception.
#. **Settlement flow (``use_onchain_only=True``)** — Hermes is bypassed
   entirely. Returns ``ResolvedPrice.source == ON_CHAIN_FALLBACK`` with
   ``settlement_opt_out=True`` so the gate can record *why* it didn't
   consult Hermes.

Why a separate module
=====================

Both the MegaETH branch (already inline in
``lib/hackathon/chain_health_gate.py``) and the Arbitrum branch
(``lib/hackathon/arbitrum_chain_health.py``) currently classify on
peg-monitor / Aave reserve state. Threading the same Hermes-primary +
on-chain-fallback pattern through both files means the integration logic
must live somewhere shared — a free function pair would do, but a
resolver class lets us hold one ``PythHermesClient`` shared across all
chain branches (the prompt explicitly calls for a *singleton, shared
across all 3 chain gates*) and lets tests inject a fake client without
patching module globals.

The resolver does **not** reach into on-chain Pyth itself — that
contract surface lives under ``lib.chains.<chain>.contracts.pyth_oracle``
(per chain). Instead the resolver accepts an ``on_chain_reader``
callable that the per-chain gate provides; callers that don't yet have
an on-chain Pyth wrapper for their chain (Wave A only has MegaETH +
Arbitrum so far) pass ``None`` and the resolver simply skips the
fallback step.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

#: Default freshness threshold. A Hermes response is considered "fresh"
#: if its ``publish_time`` is within this many seconds of ``now``. The
#: threshold is intentionally generous (Hermes is sub-second under
#: normal operation) — anything beyond 30s indicates the off-chain
#: aggregator itself is degraded, which is rare enough that we want to
#: surface it as a WARNING when it happens.
DEFAULT_FRESHNESS_THRESHOLD_S = 30

#: Same threshold reused for the on-chain fallback freshness check.
#: On-chain Pyth caches are *expected* to lag (they only update when a
#: keeper pays gas) — the gate uses this threshold purely to decide
#: whether the on-chain cache is fresh enough to be a reasonable
#: secondary source. A cache older than 30s is "stale" relative to a
#: live trading flow; a cache older than 25 days (PR #621's Optimism
#: BTC observation) is unambiguously stale-by-any-definition.


class PriceSource(StrEnum):
    """Which source provided the resolved price.

    Inherits from ``str`` so the value round-trips through JSON cleanly
    when the verdict is serialised to the dashboard / Telegram.
    """

    HERMES_PRIMARY = "HERMES_PRIMARY"
    """Hermes returned a fresh price within the freshness threshold —
    the canonical case. The on-chain cache may still be stale; we don't
    care because Hermes is ground truth."""

    ON_CHAIN_FALLBACK = "ON_CHAIN_FALLBACK"
    """Hermes was unavailable or stale; on-chain Pyth provided a fresh
    price. The verdict carries a WARNING reason to surface that the
    primary source was degraded — the price itself is still trustworthy.

    Also returned (without the WARNING reason) when the caller passed
    ``use_onchain_only=True`` for a settlement flow."""

    BOTH_STALE = "BOTH_STALE"
    """Neither source produced a fresh price. The gate raises a WARNING
    reason — *not* a BLOCK — because price-source degradation alone is
    not a reason to refuse a payment (the chain itself may still be
    functioning fine on the peg / Aave axes). Callers that need a
    fresh price must surface this to a human."""

    NO_FALLBACK_AVAILABLE = "NO_FALLBACK_AVAILABLE"
    """Hermes was stale or errored *and* the caller did not provide an
    on-chain reader. Treated identically to ``BOTH_STALE`` for severity
    purposes; distinct enum value so the gate can log "no on-chain
    Pyth wrapper for this chain yet" rather than "both sources stale"
    (the former is a Wave-A roadmap item, the latter is a real
    incident)."""


@dataclass(frozen=True)
class ResolvedPrice:
    """The outcome of one price-source resolution.

    ``severity_contribution`` is the suggested severity contribution this
    price-source state should make to the surrounding gate verdict —
    the gate composes it with its other axes (peg, Aave) using the same
    "highest wins" ladder it already uses. ``HEALTHY`` means
    *price-source is fine, do not raise on this axis*; ``WARNING`` means
    *price-source is degraded, surface to operator*; we never return
    ``BLOCK`` from this module because price-source degradation alone is
    not grounds to refuse a payment (per fail-open philosophy of the
    gate).
    """

    symbol: str
    """The symbol that was resolved (e.g. ``"BTC"``)."""

    source: PriceSource
    """Which source ultimately won."""

    price_usd: Decimal | None
    """The resolved price. ``None`` only when ``source`` is one of the
    degraded states (``BOTH_STALE`` / ``NO_FALLBACK_AVAILABLE``) AND no
    fallback price was available even as a stale value."""

    publish_time_s: int | None
    """Unix-seconds publish_time of the resolved price. ``None`` mirrors
    ``price_usd``."""

    age_s: int | None
    """Seconds between ``now`` and ``publish_time_s`` at resolution
    time. Computed once, here, so callers don't second-guess the
    freshness decision."""

    severity_contribution: str
    """``"HEALTHY"`` or ``"WARNING"`` — the gate composes this into its
    overall verdict."""

    reasons: list[str] = field(default_factory=list)
    """Human-readable reason strings the gate appends to its verdict."""

    settlement_opt_out: bool = False
    """True when the caller passed ``use_onchain_only=True`` — the
    resolver skipped Hermes by request, not by failure. The gate
    records this so the dashboard can distinguish "we chose on-chain"
    from "we fell back to on-chain because Hermes errored"."""


class ChainHealthPriceResolver:
    """Resolve a chain-health price using Hermes-primary + on-chain-fallback.

    Construction is cheap — the resolver holds one ``PythHermesClient``
    that is shared across every chain branch the gate evaluates. The
    intent (echoed by the lane prompt) is one resolver per gate
    process, threaded into each per-chain branch.

    The resolver is **not** itself the gate. It does not produce a full
    ``ChainHealthVerdict``; it produces a :class:`ResolvedPrice` that
    the gate composes into its verdict. This separation means the
    resolver is testable in isolation (no Aave fixtures needed) and
    re-usable from other contexts that need the same Hermes-primary
    pattern (e.g. signal generators, settlement-prep flows).
    """

    def __init__(
        self,
        hermes_client: Any | None = None,
        freshness_threshold_s: int = DEFAULT_FRESHNESS_THRESHOLD_S,
    ) -> None:
        """Construct the resolver.

        Args:
            hermes_client: A ``PythHermesClient``-shaped object. When
                ``None``, the resolver constructs a default client
                lazily on first use — this keeps unit tests that never
                call ``resolve()`` from importing httpx. Tests inject a
                hand-rolled mock here.
            freshness_threshold_s: Seconds beyond which a price is
                considered "stale". Default 30s.
        """
        self._hermes_client = hermes_client
        self._owns_client = hermes_client is None
        self._freshness_threshold_s = int(freshness_threshold_s)

    def _ensure_hermes(self) -> Any:
        """Lazily construct the default Hermes client on first use.

        Imports are deferred so a test that injects its own client
        never pays for httpx + the cross_chain package.
        """
        if self._hermes_client is not None:
            return self._hermes_client
        # Late import — keeps the lib.hackathon package import-time
        # surface free of httpx + the PR #625 modules until someone
        # actually calls ``resolve()`` without a pre-built client.
        from lib.chains.cross_chain.pyth_hermes import PythHermesClient  # noqa: PLC0415

        self._hermes_client = PythHermesClient()
        return self._hermes_client

    def resolve(
        self,
        symbol: str,
        *,
        on_chain_reader: Callable[[], tuple[Decimal, int] | None] | None = None,
        use_onchain_only: bool = False,
        now: int | None = None,
    ) -> ResolvedPrice:
        """Resolve the canonical price for ``symbol`` for the gate.

        Args:
            symbol: Canonical symbol (``"BTC"`` / ``"ETH"`` / ``"SOL"``
                / ``"USDC"`` / ``"USDT"``). Case-insensitive.
            on_chain_reader: Zero-arg callable returning
                ``(price_decimal, publish_time_unix_s)`` or ``None`` if
                the on-chain wrapper has no fresh value to give us. The
                per-chain gate constructs this closure around its own
                on-chain Pyth wrapper. Pass ``None`` if the chain has
                no on-chain Pyth wrapper yet (Wave A: MegaETH /
                Arbitrum have peg + Aave reads but no Pyth wrapper —
                NO_FALLBACK_AVAILABLE is the right outcome there).
            use_onchain_only: Settlement-flow flag. When True, Hermes
                is bypassed and the on-chain reader is consulted
                directly. Returns ``ON_CHAIN_FALLBACK`` with
                ``settlement_opt_out=True``.
            now: Override unix-seconds clock — testing only. Defaults
                to ``time.time()``.

        Returns:
            A :class:`ResolvedPrice` describing the resolution outcome.
        """
        sym = symbol.strip().upper()
        clock = int(time.time()) if now is None else int(now)

        # ----- settlement flow opt-out -------------------------------------
        # Caller explicitly wants on-chain. We don't even contact Hermes —
        # this saves an HTTP round-trip on the settlement critical path,
        # which matters when the surrounding flow is paying gas to refresh
        # the cache atomically.
        if use_onchain_only:
            return self._on_chain_only(sym, on_chain_reader, clock)

        # ----- Hermes primary attempt --------------------------------------
        hermes_price, hermes_pt, hermes_error = self._fetch_hermes(sym)

        if hermes_price is not None and hermes_pt is not None:
            age = clock - hermes_pt
            if age <= self._freshness_threshold_s:
                # Hermes is fresh: ground truth. Severity unaffected.
                return ResolvedPrice(
                    symbol=sym,
                    source=PriceSource.HERMES_PRIMARY,
                    price_usd=hermes_price,
                    publish_time_s=hermes_pt,
                    age_s=age,
                    severity_contribution="HEALTHY",
                    reasons=[],
                )
            # Hermes responded but with a stale price. Fall through to
            # on-chain; the WARNING is recorded on the *combined* outcome
            # below so it accurately reflects what we ultimately used.
            hermes_stale_age = age
        else:
            hermes_stale_age = None

        # ----- on-chain fallback -------------------------------------------
        return self._on_chain_fallback(
            sym,
            on_chain_reader=on_chain_reader,
            now=clock,
            hermes_error=hermes_error,
            hermes_stale_age=hermes_stale_age,
        )

    # -- internals ---------------------------------------------------------

    def _fetch_hermes(self, symbol: str) -> tuple[Decimal | None, int | None, str | None]:
        """Fetch one Hermes price, swallow expected exceptions.

        Returns ``(price, publish_time, error_str)``. Exactly one of
        (price, publish_time) or error_str is populated.

        Network / HTTP / parse errors are *all* caught here — the gate
        must never raise out of price resolution because price-source
        degradation is never grounds to refuse a payment. Errors are
        logged at WARNING for ops visibility.
        """
        try:
            client = self._ensure_hermes()
            prices = client.latest_prices_by_symbol([symbol], include_vaa=False)
        except Exception as exc:  # noqa: BLE001 — fall-back catch
            logger.warning(
                "Hermes resolve failed for %s: %s (%s)",
                symbol,
                exc,
                type(exc).__name__,
            )
            return None, None, f"{type(exc).__name__}: {exc}"

        entry = prices.get(symbol)
        if entry is None:
            return None, None, f"hermes returned no entry for {symbol}"

        # Defensive against a Hermes response with a missing / non-int
        # publish_time. The PR #625 client already type-coerces, but a
        # mock injected by a test could return whatever shape it likes.
        try:
            return Decimal(entry.price), int(entry.publish_time), None
        except (AttributeError, TypeError, ValueError) as exc:
            return None, None, f"hermes entry malformed: {exc}"

    def _on_chain_only(
        self,
        symbol: str,
        on_chain_reader: Callable[[], tuple[Decimal, int] | None] | None,
        now: int,
    ) -> ResolvedPrice:
        """Settlement-flow path: bypass Hermes, read on-chain directly."""
        if on_chain_reader is None:
            # Caller asked for settlement-mode but didn't give us an
            # on-chain reader. The gate has nothing to work with —
            # surface as NO_FALLBACK_AVAILABLE so the operator sees
            # "you wanted on-chain only but provided no on-chain
            # source", which is a wiring bug, not a real chain issue.
            return ResolvedPrice(
                symbol=symbol,
                source=PriceSource.NO_FALLBACK_AVAILABLE,
                price_usd=None,
                publish_time_s=None,
                age_s=None,
                severity_contribution="WARNING",
                reasons=[
                    f"price-source: settlement-mode requested for {symbol} "
                    "but no on-chain Pyth reader is wired"
                ],
                settlement_opt_out=True,
            )
        observation = self._safe_on_chain_read(symbol, on_chain_reader)
        if observation is None:
            return ResolvedPrice(
                symbol=symbol,
                source=PriceSource.NO_FALLBACK_AVAILABLE,
                price_usd=None,
                publish_time_s=None,
                age_s=None,
                severity_contribution="WARNING",
                reasons=[f"price-source: settlement-mode read returned no value for {symbol}"],
                settlement_opt_out=True,
            )
        price, pt = observation
        return ResolvedPrice(
            symbol=symbol,
            source=PriceSource.ON_CHAIN_FALLBACK,
            price_usd=price,
            publish_time_s=pt,
            age_s=now - pt,
            severity_contribution="HEALTHY",
            reasons=[],
            settlement_opt_out=True,
        )

    def _on_chain_fallback(
        self,
        symbol: str,
        *,
        on_chain_reader: Callable[[], tuple[Decimal, int] | None] | None,
        now: int,
        hermes_error: str | None,
        hermes_stale_age: int | None,
    ) -> ResolvedPrice:
        """Fall back to on-chain when Hermes is unavailable / stale.

        Composes the WARNING reason that surfaces *why* we fell back —
        timeout, malformed response, or stale Hermes — so the operator
        can distinguish a hermes.pyth.network outage from a clock-skew
        / Pythnet aggregator pause.
        """
        # Hermes failure context — included on every degraded outcome.
        why_hermes_failed: str
        if hermes_error is not None:
            why_hermes_failed = f"hermes unavailable: {hermes_error}"
        elif hermes_stale_age is not None:
            why_hermes_failed = (
                f"hermes stale by {hermes_stale_age}s (threshold {self._freshness_threshold_s}s)"
            )
        else:  # pragma: no cover — defensive
            why_hermes_failed = "hermes returned no usable price"

        if on_chain_reader is None:
            # No on-chain wrapper for this chain yet (Wave A roadmap).
            # Distinct enum value so the dashboard can render
            # "no on-chain Pyth wrapper" rather than "both sources stale".
            return ResolvedPrice(
                symbol=symbol,
                source=PriceSource.NO_FALLBACK_AVAILABLE,
                price_usd=None,
                publish_time_s=None,
                age_s=None,
                severity_contribution="WARNING",
                reasons=[
                    f"price-source: {why_hermes_failed}; "
                    "no on-chain Pyth wrapper available for fallback"
                ],
            )

        observation = self._safe_on_chain_read(symbol, on_chain_reader)
        if observation is None:
            # On-chain reader gave us nothing — both sources are
            # effectively unavailable.
            return ResolvedPrice(
                symbol=symbol,
                source=PriceSource.BOTH_STALE,
                price_usd=None,
                publish_time_s=None,
                age_s=None,
                severity_contribution="WARNING",
                reasons=[
                    f"price-source: {why_hermes_failed}; "
                    "on-chain reader returned no value (both sources stale)"
                ],
            )

        price, pt = observation
        age = now - pt
        if age > self._freshness_threshold_s:
            # On-chain is also stale. Source unreliable.
            return ResolvedPrice(
                symbol=symbol,
                source=PriceSource.BOTH_STALE,
                price_usd=price,
                publish_time_s=pt,
                age_s=age,
                severity_contribution="WARNING",
                reasons=[
                    f"price-source: {why_hermes_failed}; "
                    f"on-chain {symbol} also stale by {age}s "
                    "(price source unreliable)"
                ],
            )

        # On-chain is fresh — fall-back succeeded. Surface a WARNING
        # reason because the primary source was unavailable, but the
        # gate still has a usable price.
        return ResolvedPrice(
            symbol=symbol,
            source=PriceSource.ON_CHAIN_FALLBACK,
            price_usd=price,
            publish_time_s=pt,
            age_s=age,
            severity_contribution="WARNING",
            reasons=[f"price-source: {why_hermes_failed}; using on-chain {symbol} (age {age}s)"],
        )

    @staticmethod
    def _safe_on_chain_read(
        symbol: str,
        reader: Callable[[], tuple[Decimal, int] | None],
    ) -> tuple[Decimal, int] | None:
        """Call ``reader`` and swallow any exception.

        Mirrors the Hermes-side defensive catch — a misbehaving
        on-chain wrapper must never escape into the gate's exception
        handler, which is fail-open and would mask the real reason for
        the price-source degradation.
        """
        try:
            return reader()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "on-chain Pyth read failed for %s: %s (%s)",
                symbol,
                exc,
                type(exc).__name__,
            )
            return None


__all__ = (
    "DEFAULT_FRESHNESS_THRESHOLD_S",
    "ChainHealthPriceResolver",
    "PriceSource",
    "ResolvedPrice",
)
