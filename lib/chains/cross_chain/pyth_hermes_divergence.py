"""Hermes-augmented Pyth divergence detector.

This module extends the cross-chain Pyth divergence detector
(:mod:`lib.chains.cross_chain.pyth_divergence`, landing in PR #621)
with the off-chain Hermes feed as a synthetic "chain" entry. The
goal is to upgrade the detector from a *stale-cache reporter*
(current behaviour: surfaces every on-chain × on-chain disagreement
as divergence, including 1066 bps gaps caused purely by a 25-day-
stale Optimism cache) into a *stale-cache discriminator AND real-
divergence detector*.

Why two modules instead of one
==============================

The base ``CrossChainPythScanner`` in PR #621 takes per-chain
*on-chain* Pyth registries. Hermes is *off-chain* and centralized,
so it has no chain identity in the traditional sense — it's a single
HTTP endpoint that returns the canonical price the on-chain keepers
themselves observe. Mixing it into the same constructor argument
list as the chain registries muddies the abstraction (it's not "the
fourth chain"; it's the *source of truth* the three on-chain caches
are *snapshots of*).

This composer wraps the base scanner and reasons about Hermes
separately — both the dispatch (different fetch path) and the
classification (different semantics: Hermes-vs-onchain measures
*staleness*, on-chain × on-chain measures *cache disagreement*).

Severity semantics with Hermes wired in
=======================================

Once Hermes is included, three distinct conditions can produce a
"divergence" in the raw price comparison, each with a different
implication:

1. **Stale-cache** — on-chain values disagree but Hermes is between
   them. The "real" off-chain price is fine; one or more chain
   keepers are just lagging. Action: refresh the lagging chain's
   keeper via ``updatePriceFeeds`` if you care about that chain;
   ignore otherwise. Not a tradable signal.

2. **Coordinated cache lag** — Hermes is offset from *all* on-chain
   reads in the *same direction*, with the on-chain reads agreeing
   with each other. The off-chain price has moved but no chain has
   updated yet. Action: any execution path that locks in the
   on-chain price (e.g. settling a perp at the on-chain Pyth value)
   is ~stale-priced. Tradable, but the trade is "wait for the
   keepers" or "force-update the cache", not "arb between chains".

3. **Real cross-chain divergence** — on-chain values disagree *and*
   Hermes is outside the on-chain bracket (e.g. on-chain reads are
   78,000 / 78,200; Hermes is 78,500). One chain is stale, but the
   off-chain price has *also* moved. The cross-chain gap is partly
   real, partly stale-cache. Most ambiguous; rare in practice.

This module classifies (1) vs (2)+(3) by checking whether the
Hermes price is bracketed by the min and max on-chain prices —
"bracketed" = stale-cache, "outside" = real (or partly real)
divergence. Threshold for the "outside" check is the same
``MIN_SIGNAL_DIVERGENCE_BPS`` (default 20 bps) used by the base
scanner.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .pyth_hermes import HERMES_PRICE_IDS, PythHermesClient, PythHermesPrice

logger = logging.getLogger(__name__)

#: Synthetic "chain name" used for the Hermes off-chain feed in the
#: per-chain comparison map. We use ``"Hermes"`` (not ``"hermes"`` or
#: a chain_id integer) so dashboard / Telegram consumers see a
#: consistent display label that's clearly distinguishable from the
#: real chain names ("MegaETH" / "Arbitrum" / "Optimism").
HERMES_CHAIN_NAME = "Hermes"

#: Same threshold as the base scanner's ``MIN_SIGNAL_DIVERGENCE_BPS``,
#: pinned here so this module can stand alone before PR #621 lands.
#: Once that PR is on main, the canonical constant is in
#: ``lib.chains.cross_chain.pyth_divergence`` and this can re-export.
MIN_SIGNAL_DIVERGENCE_BPS: Decimal = Decimal("20")

#: Severity strings for the Hermes-augmented signal. Distinct from
#: the base scanner's ``NORMAL / OPPORTUNITY / EXTREME`` because the
#: meaning is different — these classify the *cause* of the
#: divergence, not its magnitude.
SEVERITY_NORMAL = "NORMAL"
SEVERITY_STALE_CACHE = "STALE_CACHE"
"""On-chain caches disagree but Hermes is bracketed between them —
the gap is a keeper-lag artifact, not a real off-chain price gap."""

SEVERITY_REAL_DIVERGENCE = "REAL_DIVERGENCE"
"""Hermes is outside the on-chain bracket by >= MIN_SIGNAL_DIVERGENCE_BPS
— the off-chain price has moved relative to *all* the on-chain caches
in the same direction; the on-chain reads are coordinated-stale."""

SEVERITY_MIXED = "MIXED"
"""On-chain caches disagree with each other AND Hermes is outside
their bracket. Some real off-chain move plus some keeper lag — the
ambiguous case; least common."""


@dataclass(frozen=True)
class HermesAugmentedSignal:
    """Pyth divergence signal that includes the Hermes off-chain feed.

    Distinct from the base ``PythDivergenceSignal`` because it carries
    extra fields needed to communicate the stale-vs-real distinction
    to downstream consumers (the dashboard chain-health gate, the
    operator's Telegram alerts, the risk engine's pre-trade Pyth
    sanity check).
    """

    asset: str
    """Underlying asset symbol (e.g. ``"BTC"``)."""

    on_chain: dict[str, dict[str, Any]]
    """Per-chain snapshot from the on-chain Pyth caches. Same shape
    as ``PythDivergenceSignal.chains`` — keyed by chain display name,
    values carry ``price`` / ``publish_time`` / ``stale`` /
    ``source_address``."""

    hermes_price: Decimal
    """Off-chain Hermes USD price as a Decimal. Always populated when
    this signal is constructed (an absent Hermes reading falls back
    to the base scanner without producing a HermesAugmentedSignal)."""

    hermes_publish_time: int
    """Unix seconds — when Pyth's off-chain aggregator published the
    Hermes price. Always sub-second-fresh under normal operation."""

    on_chain_max_bps: Decimal
    """Largest pairwise divergence among the on-chain reads only, in
    basis points. This is the value the *base* scanner reports."""

    hermes_vs_onchain_max_bps: Decimal
    """Largest divergence between Hermes and any on-chain read, in
    basis points. Captures the "off-chain has moved but no chain has
    refreshed" condition."""

    hermes_bracketed: bool
    """``True`` if the Hermes price falls between the min and max
    on-chain prices (the stale-cache case). ``False`` when Hermes is
    outside the on-chain bracket (the real-divergence case)."""

    severity: str
    """One of ``NORMAL`` / ``STALE_CACHE`` / ``REAL_DIVERGENCE`` /
    ``MIXED``."""

    chains_unavailable: list[str] = field(default_factory=list)
    """Chain display names whose RPC fetch failed."""

    any_stale: bool = False
    """``True`` if any on-chain cache reports ``stale=True`` (typically
    publish_time older than 1 hour)."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (Decimals → strings)."""
        return {
            "asset": self.asset,
            "on_chain": {
                name: {
                    "price": str(payload["price"]),
                    "publish_time": int(payload["publish_time"]),
                    "stale": bool(payload["stale"]),
                    "source_address": str(payload["source_address"]),
                }
                for name, payload in self.on_chain.items()
            },
            "hermes_price": str(self.hermes_price),
            "hermes_publish_time": int(self.hermes_publish_time),
            "on_chain_max_bps": str(self.on_chain_max_bps),
            "hermes_vs_onchain_max_bps": str(self.hermes_vs_onchain_max_bps),
            "hermes_bracketed": bool(self.hermes_bracketed),
            "severity": self.severity,
            "chains_unavailable": list(self.chains_unavailable),
            "any_stale": bool(self.any_stale),
        }


def _max_pairwise_bps(prices: list[Decimal]) -> Decimal:
    """Largest pairwise (max-min)/min divergence in basis points.

    Mirrors the helper in the base scanner — duplicated rather than
    imported so this module stays usable before PR #621 lands. Once
    that PR is on main this can re-export.
    """
    if len(prices) < 2:
        return Decimal(0)
    hi = max(prices)
    lo = min(prices)
    if lo <= 0:
        return Decimal(0)
    return (hi - lo) / lo * Decimal("10000")


def _classify_with_hermes(
    on_chain_prices: list[Decimal],
    hermes_price: Decimal,
    *,
    threshold_bps: Decimal = MIN_SIGNAL_DIVERGENCE_BPS,
) -> tuple[str, bool, Decimal]:
    """Classify severity given on-chain prices + the Hermes price.

    Returns ``(severity, hermes_bracketed, hermes_vs_onchain_max_bps)``.

    Logic:

    * If both the on-chain max-pairwise bps AND the Hermes-vs-onchain
      max bps are below ``threshold_bps``, severity is ``NORMAL``.
    * If on-chain reads disagree but Hermes is bracketed (between
      min and max on-chain), severity is ``STALE_CACHE`` — the
      cross-chain gap exists only because the caches refreshed at
      different times against the same underlying off-chain feed.
    * If Hermes is outside the on-chain bracket by >= threshold but
      the on-chain reads agree with each other (within threshold),
      severity is ``REAL_DIVERGENCE`` — coordinated cache lag, the
      off-chain price has moved.
    * Both conditions together → ``MIXED``.
    """
    if not on_chain_prices:
        return SEVERITY_NORMAL, False, Decimal(0)

    on_chain_min = min(on_chain_prices)
    on_chain_max = max(on_chain_prices)
    on_chain_max_bps = _max_pairwise_bps(on_chain_prices)

    # Hermes-vs-onchain: largest pairwise gap between Hermes and any
    # individual on-chain read. We want the *worst-case* gap to drive
    # severity, so reduce over all on-chain reads.
    hermes_vs_onchain = _max_pairwise_bps([hermes_price, on_chain_min])
    hermes_vs_onchain = max(hermes_vs_onchain, _max_pairwise_bps([hermes_price, on_chain_max]))

    bracketed = on_chain_min <= hermes_price <= on_chain_max
    on_chain_disagree = on_chain_max_bps >= threshold_bps
    hermes_outside = (not bracketed) and hermes_vs_onchain >= threshold_bps

    if not on_chain_disagree and not hermes_outside:
        severity = SEVERITY_NORMAL
    elif on_chain_disagree and not hermes_outside:
        # On-chain reads disagree but Hermes is in the middle (or the
        # gap from Hermes to the nearest on-chain edge is below the
        # threshold). Pure stale-cache artifact.
        severity = SEVERITY_STALE_CACHE
    elif hermes_outside and not on_chain_disagree:
        severity = SEVERITY_REAL_DIVERGENCE
    else:
        severity = SEVERITY_MIXED

    return severity, bracketed, hermes_vs_onchain


class HermesAugmentedScanner:
    """Pyth divergence scanner with the off-chain Hermes feed wired in.

    Wraps the per-chain on-chain Pyth registries (same shapes the
    base ``CrossChainPythScanner`` accepts) plus a
    :class:`PythHermesClient`. For each scanned asset, fetches all
    chains in parallel (asyncio gather) and the Hermes price
    (synchronously via ``asyncio.to_thread``), then classifies the
    result.

    This is the "smart" scanner the chain-health gate and dashboard
    should use when they want stale-vs-real distinction. The base
    on-chain-only scanner remains useful for callers that explicitly
    want the on-chain comparison only (e.g. risk-engine pre-trade
    checks that *only* care about on-chain values because that's
    what their settlement reads).
    """

    #: Display names for the on-chain registries. Mirrors the base
    #: scanner's ``CHAIN_NAMES`` so dashboard labels stay consistent
    #: across the two scanner classes.
    CHAIN_NAMES: dict[str, str] = {
        "megaeth": "MegaETH",
        "arbitrum": "Arbitrum",
        "optimism": "Optimism",
    }

    def __init__(
        self,
        *,
        megaeth_pyth: Any | None = None,
        arbitrum_pyth: Any | None = None,
        optimism_pyth: Any | None = None,
        hermes: PythHermesClient | None = None,
        threshold_bps: Decimal = MIN_SIGNAL_DIVERGENCE_BPS,
    ) -> None:
        """Construct from per-chain registries + a Hermes client.

        Args:
            megaeth_pyth: MegaETH Pyth registry (or ``None`` to skip).
            arbitrum_pyth: Arbitrum Pyth registry (or ``None`` to skip).
            optimism_pyth: Optimism Pyth registry (or ``None`` to skip).
            hermes: Hermes client. When ``None``, constructed with
                defaults — caller can swap for a mock in tests.
            threshold_bps: Severity threshold (mirrors base scanner).

        Any registry may be ``None``, in which case that chain is
        skipped entirely. The scanner can run with just Hermes and
        zero chains — useful for "Hermes is the only price source"
        flows that don't care about the on-chain caches at all.
        """
        self._registries: dict[str, Any] = {}
        if megaeth_pyth is not None:
            self._registries[self.CHAIN_NAMES["megaeth"]] = megaeth_pyth
        if arbitrum_pyth is not None:
            self._registries[self.CHAIN_NAMES["arbitrum"]] = arbitrum_pyth
        if optimism_pyth is not None:
            self._registries[self.CHAIN_NAMES["optimism"]] = optimism_pyth
        self._hermes = hermes if hermes is not None else PythHermesClient()
        self._threshold = threshold_bps

    # -- public API --------------------------------------------------------

    async def scan_asset(self, symbol: str) -> HermesAugmentedSignal | None:
        """Scan one asset across every wired chain plus Hermes.

        Returns ``None`` when the symbol is not in
        :data:`HERMES_PRICE_IDS` (Hermes can't price it) — the entire
        point of this scanner is to use Hermes as ground truth, so
        skipping the asset rather than returning a no-Hermes signal
        is the right semantics.

        Always returns a :class:`HermesAugmentedSignal` when Hermes
        responds, even if no on-chain registries are wired (in which
        case ``on_chain`` is empty and severity is ``NORMAL``).
        """
        sym = symbol.strip().upper()
        if sym not in HERMES_PRICE_IDS:
            return None

        # Run on-chain fetches and the Hermes fetch concurrently.
        # Hermes is sync httpx; wrap with to_thread so the asyncio
        # gather actually overlaps with the chain RPC roundtrips.
        chain_names = list(self._registries.keys())
        chain_task = asyncio.gather(
            *(self._fetch_one_chain(name, sym) for name in chain_names),
            return_exceptions=True,
        )
        hermes_task = asyncio.to_thread(self._fetch_hermes, sym)

        chain_results, hermes_price = await asyncio.gather(chain_task, hermes_task)

        if hermes_price is None:
            # Hermes itself failed — fall back to no signal rather
            # than synthesizing one without ground truth. The base
            # scanner is the correct tool when Hermes isn't available.
            logger.warning("Hermes fetch for %s failed; returning no signal", sym)
            return None

        on_chain: dict[str, dict[str, Any]] = {}
        unavailable: list[str] = []
        for name, result in zip(chain_names, chain_results, strict=True):
            if isinstance(result, BaseException):
                if isinstance(result, LookupError):
                    # Registry doesn't carry this symbol — not a
                    # failure, just absent.
                    continue
                logger.warning(
                    "on-chain Pyth fetch %s on %s failed: %s",
                    sym,
                    name,
                    result,
                )
                unavailable.append(name)
                continue
            price = Decimal(str(result.usd))
            registry = self._registries[name]
            source_address = getattr(registry, "_address", "") or ""
            on_chain[name] = {
                "price": price,
                "publish_time": int(result.publish_time),
                "stale": bool(getattr(result, "stale", False)),
                "source_address": str(source_address),
            }

        on_chain_prices = [v["price"] for v in on_chain.values()]
        on_chain_max_bps = _max_pairwise_bps(on_chain_prices)
        severity, bracketed, hermes_vs_onchain = _classify_with_hermes(
            on_chain_prices,
            hermes_price.price,
            threshold_bps=self._threshold,
        )
        any_stale = any(v["stale"] for v in on_chain.values())

        return HermesAugmentedSignal(
            asset=sym,
            on_chain=on_chain,
            hermes_price=hermes_price.price,
            hermes_publish_time=hermes_price.publish_time,
            on_chain_max_bps=on_chain_max_bps,
            hermes_vs_onchain_max_bps=hermes_vs_onchain,
            hermes_bracketed=bracketed,
            severity=severity,
            chains_unavailable=unavailable,
            any_stale=any_stale,
        )

    async def scan_top_assets(self, n: int = 5) -> list[HermesAugmentedSignal]:
        """Scan top-N candidate assets, return only emitted signals.

        Walks :data:`HERMES_PRICE_IDS` keys in their declared order
        (BTC, ETH, SOL, USDC, USDT). Skips ``None`` results. Sorts
        by ``hermes_vs_onchain_max_bps`` descending so the operator
        sees the largest "off-chain has moved relative to on-chain"
        gap first — that's the signal where prompt action (refresh
        keepers, or trade against the cache lag) has the most
        impact.
        """
        signals: list[HermesAugmentedSignal] = []
        for sym in list(HERMES_PRICE_IDS):
            try:
                sig = await self.scan_asset(sym)
            except Exception:
                logger.exception("scan_asset(%s) failed", sym)
                continue
            if sig is not None:
                signals.append(sig)
            if len(signals) >= n:
                break
        signals.sort(
            key=lambda s: s.hermes_vs_onchain_max_bps,
            reverse=True,
        )
        return signals

    # -- internals ---------------------------------------------------------

    def _fetch_hermes(self, symbol: str) -> PythHermesPrice | None:
        """Sync Hermes fetch, returns ``None`` on any failure.

        Errors are logged at warning — the augmented scanner can
        survive an isolated Hermes blip by returning ``None`` from
        ``scan_asset``, falling back to the base on-chain-only flow
        for that asset.
        """
        try:
            prices = self._hermes.latest_prices_by_symbol([symbol], include_vaa=False)
        except Exception as exc:
            logger.warning("Hermes fetch %s failed: %s", symbol, exc)
            return None
        return prices.get(symbol)

    async def _fetch_one_chain(self, chain_name: str, symbol: str) -> Any:
        """Call ``fetch_price`` on one on-chain registry."""
        return await self._registries[chain_name].fetch_price(symbol)


__all__ = (
    "HERMES_CHAIN_NAME",
    "HermesAugmentedScanner",
    "HermesAugmentedSignal",
    "MIN_SIGNAL_DIVERGENCE_BPS",
    "SEVERITY_MIXED",
    "SEVERITY_NORMAL",
    "SEVERITY_REAL_DIVERGENCE",
    "SEVERITY_STALE_CACHE",
)
