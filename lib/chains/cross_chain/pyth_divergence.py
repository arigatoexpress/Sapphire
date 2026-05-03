"""Cross-chain Pyth oracle price-divergence signal detector.

Pyth feeds publish off-chain on a sub-second cadence, but the
**on-chain cached** value updates only when someone calls
``updatePriceFeeds`` (a gas-paid keeper action). Each chain Pyth
deploys to has its own pull-keeper cadence — Arbitrum mainnet sees
frequent refreshes (deep liquidity → many keepers), MegaETH testnet
sees sparser refreshes (small validator set), Optimism sits in
between.

That asymmetry creates a real, measurable divergence between
``pyth.getPriceUnsafe(BTC)`` on chain A and chain B at the same wall-
clock moment: the cached price on the slower chain is just *older*.
Whether that divergence is *tradable* depends on:

* Is it large enough to clear bridge + gas costs?
* Is the staler chain about to keeper-update (closing the gap), or
  is it stuck (so the gap persists long enough to bridge)?
* Is the divergence persistent or noise (within Pyth's own
  confidence interval)?

This module is a *signal generator* — it observes the divergence,
classifies severity, and returns a structured signal. It does NOT
execute. Routing remains a separate, gated decision the operator
(or a future executor) makes.

Why this matters: each per-chain Pyth wrapper (megaeth/arbitrum/optimism)
returns its own ``PythRegistryPrice``. Single-chain consumers see one
chain's cached price and can't notice the cross-chain dislocation.
This scanner is the second cross-chain primitive composed over the
chain wrappers (after the Aave APY arb in
:mod:`lib.chains.cross_chain.aave_apy_arb`), so the multi-chain
integration substantiates "Sapphire is the canonical multi-chain
alpha-discovery layer" rather than just claiming portability.

Severity bands (basis points = bps; 100 bps == 1 %):

* ``NORMAL``       — max divergence < 20 bps (noise / tight tape)
* ``OPPORTUNITY``  — 20 bps ≤ max divergence < 100 bps (worth watching)
* ``EXTREME``      — max divergence ≥ 100 bps (rare; investigate first
  for staleness on one chain — divergence may be artificial if the
  cached price on a chain is more than 1 hour old)

Staleness handling
==================

If any chain's price is stale (``publish_time`` older than 1 h), the
signal still surfaces — but the staleness flag is preserved on the
per-chain payload so the operator can see "Optimism's cache is 73
minutes old; the 142 bps gap may close the moment a keeper refreshes
it." The thesis is that the *off-chain* Pyth Hermes API would resolve
the gap immediately; the on-chain divergence is real only insofar as
on-chain execution is the constraint (e.g. bridging rather than
trading off-chain).

Thresholds are constants exported from this module so callers can
reference them and tests can pin them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

#: Minimum max-divergence (in basis points) before a signal is emitted
#: at all. Below this we treat the chains as effectively at parity and
#: ``scan_asset`` returns ``None``. Pinned because every downstream
#: consumer keys behaviour on this constant.
MIN_SIGNAL_DIVERGENCE_BPS: Decimal = Decimal("20")

#: Boundary between OPPORTUNITY and EXTREME severities, in basis points.
EXTREME_DIVERGENCE_BPS: Decimal = Decimal("100")

#: Severity labels — string-typed so JSON serialization is trivial and
#: there's no enum coupling at the dashboard / plugin tool boundary.
SEVERITY_NORMAL = "NORMAL"
SEVERITY_OPPORTUNITY = "OPPORTUNITY"
SEVERITY_EXTREME = "EXTREME"

#: Default top-N candidate symbols. These are the underlying assets
#: with Pyth price feeds present on every supported chain
#: (MegaETH / Arbitrum / Optimism) so cross-chain comparison is
#: meaningful without needing to pivot through wrapped/synth tokens.
DEFAULT_TOP_ASSETS: tuple[str, ...] = ("BTC", "ETH", "SOL", "USDC", "USDT")


@dataclass(frozen=True)
class PythDivergenceSignal:
    """Structured cross-chain Pyth oracle divergence signal.

    A single signal pertains to a single underlying asset (e.g. BTC).
    It carries the per-chain Pyth read snapshot for context, the
    maximum pairwise divergence in basis points, the freshest /
    stalest chain identifiers, and a severity classification.

    Per-chain prices are :class:`decimal.Decimal` to preserve the
    precision the upstream Pyth wrappers compute — Pyth USD feeds use
    ``int64 price * 10**expo`` which is exact in Decimal but lossy in
    float. Divergence math upgrades to Decimal so basis-point
    comparisons are exact.

    Field shape is intentionally JSON-friendly: :meth:`to_dict`
    flattens Decimals to strings so the signal can ride the dashboard
    SSE stream or a plugin tool's stdout without bespoke encoders.
    """

    asset: str
    """Underlying asset symbol (e.g. ``"BTC"``)."""

    chains: dict[str, dict[str, Any]]
    """Per-chain snapshot keyed by chain display name. Each entry has:

    * ``price``: ``Decimal`` USD price
    * ``publish_time``: ``int`` unix seconds — when the off-chain feed
      last published (the on-chain cache stores this verbatim)
    * ``stale``: ``bool`` — True if ``publish_time`` is older than 1 h
    * ``source_address``: ``str`` — Pyth contract address on the chain
    """

    max_divergence_bps: Decimal
    """Largest pairwise divergence in basis points across the available
    chains. ``Decimal("142")`` == 1.42 %. Always >= 0."""

    freshest_chain: str
    """Chain display name with the most recent ``publish_time`` (i.e.
    the chain whose cached price is least stale). Empty string when no
    chains have data."""

    stalest_chain: str
    """Chain display name with the oldest ``publish_time``. Empty string
    when no chains have data."""

    severity: str
    """One of ``NORMAL`` / ``OPPORTUNITY`` / ``EXTREME``."""

    chains_unavailable: list[str] = field(default_factory=list)
    """Chain display names whose RPC fetch failed; the signal still
    surfaces if at least 2 chains succeeded."""

    any_stale: bool = False
    """``True`` if at least one chain's cached price is stale (older
    than 1 h). When True the operator should weight the divergence
    accordingly — it may close the moment a keeper refreshes the
    stale chain's cache."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (Decimals → strings)."""
        return {
            "asset": self.asset,
            "chains": {
                name: {
                    "price": str(payload["price"]),
                    "publish_time": int(payload["publish_time"]),
                    "stale": bool(payload["stale"]),
                    "source_address": str(payload["source_address"]),
                }
                for name, payload in self.chains.items()
            },
            "max_divergence_bps": str(self.max_divergence_bps),
            "freshest_chain": self.freshest_chain,
            "stalest_chain": self.stalest_chain,
            "severity": self.severity,
            "chains_unavailable": list(self.chains_unavailable),
            "any_stale": bool(self.any_stale),
        }


def _classify_severity(max_bps: Decimal) -> str:
    """Map max pairwise divergence (bps) → severity label."""
    if max_bps < MIN_SIGNAL_DIVERGENCE_BPS:
        return SEVERITY_NORMAL
    if max_bps < EXTREME_DIVERGENCE_BPS:
        return SEVERITY_OPPORTUNITY
    return SEVERITY_EXTREME


def _max_pairwise_bps(prices: list[Decimal]) -> Decimal:
    """Largest pairwise (max-min)/min divergence in basis points.

    Uses the *minimum* price as the denominator so the result is the
    upper-bound percentage gap a buyer-on-cheap / seller-on-expensive
    arb sees. Equivalent to the standard cross-venue spread quote.
    Returns ``Decimal(0)`` for fewer than 2 prices.
    """
    if len(prices) < 2:
        return Decimal(0)
    hi = max(prices)
    lo = min(prices)
    if lo <= 0:
        # Defensive — Pyth feeds should never report non-positive but
        # if one slips through we'd rather emit zero than divide-by-zero.
        return Decimal(0)
    return (hi - lo) / lo * Decimal("10000")


class CrossChainPythScanner:
    """Pyth oracle cross-chain divergence scanner.

    Composes per-chain Pyth registries. Each registry only needs to
    expose ``async def fetch_price(symbol: str) -> <something with
    .usd / .publish_time / .stale / .price_id>`` plus a
    ``known_symbols() -> list[str]`` for fast availability checks. We
    duck-type rather than importing the per-chain types so the
    scanner stays agnostic to which chain's registry has been mocked
    in tests.

    Construct once; ``scan_asset`` and ``scan_top_assets`` are cheap
    to invoke repeatedly (each call re-fetches per chain so the data
    stays fresh — caching can be layered on by the caller).
    """

    #: Display names mirrored from the per-chain wrappers so dashboard
    #: / signal-stream callers see consistent chain labels everywhere.
    CHAIN_NAMES: dict[str, str] = {
        "megaeth": "MegaETH",
        "arbitrum": "Arbitrum",
        "optimism": "Optimism",
    }

    def __init__(
        self,
        megaeth_pyth: Any | None = None,
        arbitrum_pyth: Any | None = None,
        optimism_pyth: Any | None = None,
    ) -> None:
        """Construct from per-chain Pyth registries.

        Any registry may be ``None`` — in that case the scanner skips
        that chain entirely. This is the partial-deployment path: at
        the time of writing, MegaETH Pyth ships in PR #608 and
        Optimism Pyth ships in parallel; until both land on main this
        scanner accepts whichever subset is available and just
        compares across the two.
        """
        self._registries: dict[str, Any] = {}
        if megaeth_pyth is not None:
            self._registries[self.CHAIN_NAMES["megaeth"]] = megaeth_pyth
        if arbitrum_pyth is not None:
            self._registries[self.CHAIN_NAMES["arbitrum"]] = arbitrum_pyth
        if optimism_pyth is not None:
            self._registries[self.CHAIN_NAMES["optimism"]] = optimism_pyth

    # -- public API --------------------------------------------------------

    async def scan_asset(self, symbol: str) -> PythDivergenceSignal | None:
        """Scan one asset across every wired chain.

        Returns ``None`` when:

        * fewer than 2 chains have the asset registered (can't compute
          a divergence)
        * the maximum divergence is below
          :data:`MIN_SIGNAL_DIVERGENCE_BPS`

        Otherwise returns a fully-populated
        :class:`PythDivergenceSignal`. Stale prices are *included* in
        the signal — the operator decides whether to discount them.
        """
        per_chain, unavailable = await self._collect_per_chain_prices(symbol)
        if len(per_chain) < 2:
            return None

        prices = [v["price"] for v in per_chain.values()]
        max_bps = _max_pairwise_bps(prices)
        if max_bps < MIN_SIGNAL_DIVERGENCE_BPS:
            return None

        # Freshest / stalest by publish_time. Highest publish_time =
        # most recent off-chain publish that the on-chain cache has
        # observed. Ties broken by chain-name sort order so the result
        # is deterministic.
        items_sorted = sorted(
            per_chain.items(),
            key=lambda kv: (kv[1]["publish_time"], kv[0]),
        )
        stalest = items_sorted[0][0]
        freshest = items_sorted[-1][0]

        any_stale = any(v["stale"] for v in per_chain.values())

        return PythDivergenceSignal(
            asset=symbol.upper(),
            chains=per_chain,
            max_divergence_bps=max_bps,
            freshest_chain=freshest,
            stalest_chain=stalest,
            severity=_classify_severity(max_bps),
            chains_unavailable=unavailable,
            any_stale=any_stale,
        )

    async def scan_top_assets(self, n: int = 5) -> list[PythDivergenceSignal]:
        """Scan the top-N candidate assets, return only emitted signals.

        Walks :data:`DEFAULT_TOP_ASSETS` until ``n`` signals have been
        collected (or the candidate list is exhausted). Assets that
        don't appear on at least 2 chains are silently skipped.

        Results are sorted by ``max_divergence_bps`` descending so the
        caller sees the sharpest opportunity first.
        """
        signals: list[PythDivergenceSignal] = []
        for symbol in DEFAULT_TOP_ASSETS:
            try:
                sig = await self.scan_asset(symbol)
            except Exception:
                logger.exception("scan_asset(%s) failed", symbol)
                continue
            if sig is not None:
                signals.append(sig)
            if len(signals) >= n:
                break
        signals.sort(key=lambda s: s.max_divergence_bps, reverse=True)
        return signals

    # -- internals ---------------------------------------------------------

    async def _collect_per_chain_prices(
        self, symbol: str
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """Fan out ``fetch_price`` across every wired chain.

        Returns ``(per_chain, unavailable)`` where:

        * ``per_chain`` maps chain display name → ``{price,
          publish_time, stale, source_address}`` for the requested
          symbol (only chains that responded AND know the symbol)
        * ``unavailable`` is the list of chain names whose RPC fetch
          raised — included so the signal can flag partial coverage
        """
        chain_names = list(self._registries.keys())
        results = await asyncio.gather(
            *(self._fetch_one(name, symbol) for name in chain_names),
            return_exceptions=True,
        )

        per_chain: dict[str, dict[str, Any]] = {}
        unavailable: list[str] = []
        for name, result in zip(chain_names, results, strict=True):
            if isinstance(result, BaseException):
                # ``LookupError`` from a registry that doesn't know the
                # symbol is *not* an availability failure — the chain
                # responded; it just doesn't carry that feed. Skip
                # silently so single-chain feeds (e.g. ARB-only) don't
                # pollute ``chains_unavailable``.
                if isinstance(result, LookupError):
                    continue
                logger.warning(
                    "Pyth fetch_price(%s) failed on %s: %s",
                    symbol,
                    name,
                    result,
                )
                unavailable.append(name)
                continue
            # Result is a PythRegistryPrice-shaped object. Pull the
            # three required fields by attribute, plus the registry's
            # contract address for provenance on the dashboard.
            price = Decimal(str(result.usd))
            registry = self._registries[name]
            source_address = getattr(registry, "_address", "") or ""
            per_chain[name] = {
                "price": price,
                "publish_time": int(result.publish_time),
                "stale": bool(result.stale),
                "source_address": str(source_address),
            }
        return per_chain, unavailable

    async def _fetch_one(self, chain_name: str, symbol: str) -> Any:
        """Call ``fetch_price`` on one registry. Errors propagate to
        the gather + are caught there as ``return_exceptions=True``."""
        return await self._registries[chain_name].fetch_price(symbol)


__all__ = (
    "CrossChainPythScanner",
    "DEFAULT_TOP_ASSETS",
    "EXTREME_DIVERGENCE_BPS",
    "MIN_SIGNAL_DIVERGENCE_BPS",
    "PythDivergenceSignal",
    "SEVERITY_EXTREME",
    "SEVERITY_NORMAL",
    "SEVERITY_OPPORTUNITY",
)
