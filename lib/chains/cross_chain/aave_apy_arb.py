"""Cross-chain Aave V3 supply/borrow APY arbitrage signal detector.

When Aave V3's USDC supply APY is materially higher on Optimism than on
Arbitrum (for example), capital sitting in the lower-APY pool is leaving
yield on the table and a cross-chain rotation has positive expected
value (modulo bridge cost + bridge time).

This module is a *signal generator* — it observes the spread, classifies
severity, and returns a structured signal. It does NOT execute. Routing
is a separate, gated decision the operator (or a future executor) makes.

Why this matters: each per-chain Aave wrapper (megaeth/arbitrum/optimism)
returns its own ``LendOverview``. Single-chain consumers see a single
chain's reserves and can't notice cross-chain dislocation. This scanner
is the first cross-chain primitive composed over all three facades, so
the multi-chain integration becomes a positive alpha source rather than
just a portability claim.

Severity rules (basis points = bps; 100 bps == 1%):

* ``NORMAL``       — max spread < 50 bps  (noise)
* ``OPPORTUNITY``  — 50 bps ≤ max spread < 200 bps  (worth watching)
* ``EXTREME``      — max spread ≥ 200 bps  (rare; investigate first)

The thresholds are constants exported from this module so callers can
reference them and tests can pin them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

#: Minimum max-spread (in basis points) before a signal is emitted at
#: all. Below this we treat the chains as effectively at parity and
#: ``scan_asset`` returns ``None`` (no signal). Pinned because every
#: downstream consumer keys behaviour on this constant.
MIN_SIGNAL_SPREAD_BPS: Decimal = Decimal("50")

#: Boundary between OPPORTUNITY and EXTREME severities, in basis points.
EXTREME_SPREAD_BPS: Decimal = Decimal("200")

#: Severity labels — string-typed so JSON serialization is trivial and
#: there's no enum-coupling at the dashboard / plugin tool boundary.
SEVERITY_NORMAL = "NORMAL"
SEVERITY_OPPORTUNITY = "OPPORTUNITY"
SEVERITY_EXTREME = "EXTREME"

#: Default top-N assets surface when the caller does not specify which
#: assets to scan. These are the symbols that historically appear on
#: every major Aave V3 deployment; ``scan_top_assets`` filters down to
#: those that actually overlap across the available chains.
DEFAULT_TOP_ASSETS: tuple[str, ...] = ("USDC", "USDT", "DAI", "WETH", "WBTC")


@dataclass(frozen=True)
class AaveApyArbSignal:
    """Structured cross-chain Aave APY arbitrage signal.

    A single signal pertains to a single underlying asset (e.g. USDC).
    It carries the per-chain APY snapshot for context, the maximum
    supply-side and borrow-side spreads in basis points, a human-readable
    direction string, and a severity classification.

    APY values inside ``chains`` are :class:`decimal.Decimal` to preserve
    the precision the upstream Aave wrappers compute — the source values
    are floats in *fraction* form (0.05 == 5%), but the spread math
    upgrades to Decimal so basis-point comparisons are exact.

    Field shape is intentionally JSON-friendly: ``to_dict`` flattens
    Decimals to strings so the signal can ride the dashboard SSE stream
    or a plugin tool's stdout without bespoke encoders.
    """

    asset: str
    """Underlying asset symbol (e.g. ``"USDC"``)."""

    chains: dict[str, dict[str, Decimal]]
    """Per-chain snapshot keyed by chain name. Each entry has keys
    ``supply_apy`` and ``borrow_apy`` (both ``Decimal`` fractions)."""

    max_supply_spread_bps: Decimal
    """Largest pairwise difference in supply APY across the available
    chains, expressed in basis points (``Decimal("250")`` == 2.5%)."""

    max_borrow_spread_bps: Decimal
    """Largest pairwise difference in borrow APY across the available
    chains, in basis points."""

    direction: str
    """Human-readable description, e.g.
    ``"supply on Optimism (3.50%) vs Arbitrum (1.20%)"``."""

    severity: str
    """One of ``NORMAL`` / ``OPPORTUNITY`` / ``EXTREME``."""

    chains_unavailable: list[str] = field(default_factory=list)
    """Chain names whose RPC fetch failed; the signal still surfaces if
    at least 2 chains succeeded."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (Decimals → strings)."""
        return {
            "asset": self.asset,
            "chains": {
                name: {k: str(v) for k, v in payload.items()}
                for name, payload in self.chains.items()
            },
            "max_supply_spread_bps": str(self.max_supply_spread_bps),
            "max_borrow_spread_bps": str(self.max_borrow_spread_bps),
            "direction": self.direction,
            "severity": self.severity,
            "chains_unavailable": list(self.chains_unavailable),
        }


def _classify_severity(max_bps: Decimal) -> str:
    """Map the larger of (supply_spread, borrow_spread) bps → severity."""
    if max_bps < MIN_SIGNAL_SPREAD_BPS:
        return SEVERITY_NORMAL
    if max_bps < EXTREME_SPREAD_BPS:
        return SEVERITY_OPPORTUNITY
    return SEVERITY_EXTREME


def _fraction_to_bps(fraction: Decimal) -> Decimal:
    """Convert a fraction-form APY (0.05) to basis points (500)."""
    return fraction * Decimal("10000")


def _format_direction(
    asset: str,
    chains: dict[str, dict[str, Decimal]],
    side: str,
) -> str:
    """Build a `"supply on X (a%) vs Y (b%)"`-style direction string.

    Picks the (max, min) pair on the requested side and formats
    fraction-APYs as percentage with 2 decimal places.
    """
    if len(chains) < 2:
        return f"insufficient data for {asset} {side}-side direction"
    key = f"{side}_apy"
    sorted_chains = sorted(chains.items(), key=lambda kv: kv[1][key], reverse=True)
    high_name, high = sorted_chains[0]
    low_name, low = sorted_chains[-1]
    high_pct = float(high[key]) * 100
    low_pct = float(low[key]) * 100
    return f"{side} on {high_name} ({high_pct:.2f}%) vs {low_name} ({low_pct:.2f}%)"


class CrossChainAaveScanner:
    """Aave V3 cross-chain APY arbitrage scanner.

    Composes three per-chain protocol facades. Each facade only needs to
    expose ``async def lend_overview() -> <something with .reserves>``;
    we duck-type rather than importing the per-chain types so the
    scanner stays agnostic to which chain's facade has been mocked in
    tests.

    Construct once; ``scan_asset`` and ``scan_top_assets`` are cheap to
    invoke repeatedly (each call re-fetches ``lend_overview`` per chain
    so the data stays fresh — caching can be layered on by the caller).
    """

    #: Display names mirrored from chain-health gate so dashboard /
    #: signal-stream callers see consistent chain labels everywhere.
    CHAIN_NAMES: dict[str, str] = {
        "megaeth": "MegaETH",
        "arbitrum": "Arbitrum",
        "optimism": "Optimism",
    }

    def __init__(
        self,
        megaeth_protocols: Any | None = None,
        arbitrum_protocols: Any | None = None,
        optimism_protocols: Any | None = None,
    ) -> None:
        """Construct from per-chain protocol facades.

        Any facade may be ``None`` — in that case the scanner skips that
        chain entirely (useful for partial deployments / dev mode where
        only one or two RPC clients are wired).
        """
        self._facades: dict[str, Any] = {}
        if megaeth_protocols is not None:
            self._facades[self.CHAIN_NAMES["megaeth"]] = megaeth_protocols
        if arbitrum_protocols is not None:
            self._facades[self.CHAIN_NAMES["arbitrum"]] = arbitrum_protocols
        if optimism_protocols is not None:
            self._facades[self.CHAIN_NAMES["optimism"]] = optimism_protocols

    # -- public API --------------------------------------------------------

    async def scan_asset(self, asset_symbol: str) -> AaveApyArbSignal | None:
        """Scan one asset across every wired chain.

        Returns ``None`` when:

        * fewer than 2 chains have the asset available (can't compute a
          spread)
        * the maximum spread is below ``MIN_SIGNAL_SPREAD_BPS``

        Otherwise returns a fully-populated :class:`AaveApyArbSignal`.
        """
        per_chain, unavailable = await self._collect_per_chain_apys(asset_symbol)
        if len(per_chain) < 2:
            # Not a multi-chain situation — no spread to compute.
            return None

        supply_values = [v["supply_apy"] for v in per_chain.values()]
        borrow_values = [v["borrow_apy"] for v in per_chain.values()]

        supply_spread_bps = _fraction_to_bps(max(supply_values) - min(supply_values))
        borrow_spread_bps = _fraction_to_bps(max(borrow_values) - min(borrow_values))
        max_bps = max(supply_spread_bps, borrow_spread_bps)

        if max_bps < MIN_SIGNAL_SPREAD_BPS:
            return None

        # Direction string anchors on the larger side so the operator
        # immediately sees which way the rotation runs.
        side = "supply" if supply_spread_bps >= borrow_spread_bps else "borrow"
        direction = _format_direction(asset_symbol, per_chain, side)

        return AaveApyArbSignal(
            asset=asset_symbol,
            chains=per_chain,
            max_supply_spread_bps=supply_spread_bps,
            max_borrow_spread_bps=borrow_spread_bps,
            direction=direction,
            severity=_classify_severity(max_bps),
            chains_unavailable=unavailable,
        )

    async def scan_top_assets(self, n: int = 5) -> list[AaveApyArbSignal]:
        """Scan the top-N candidate assets, return only emitted signals.

        Walks ``DEFAULT_TOP_ASSETS`` until ``n`` signals have been
        collected (or the candidate list is exhausted). Assets that
        don't appear on at least 2 chains are silently skipped.

        Results are sorted by ``max(supply_spread_bps, borrow_spread_bps)``
        descending so the caller sees the sharpest opportunity first.
        """
        signals: list[AaveApyArbSignal] = []
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
        signals.sort(
            key=lambda s: max(s.max_supply_spread_bps, s.max_borrow_spread_bps),
            reverse=True,
        )
        return signals

    # -- internals ---------------------------------------------------------

    async def _collect_per_chain_apys(
        self, asset_symbol: str
    ) -> tuple[dict[str, dict[str, Decimal]], list[str]]:
        """Fan-out ``lend_overview`` across every wired chain.

        Returns ``(per_chain, unavailable)`` where:

        * ``per_chain`` maps chain display name → ``{supply_apy,
          borrow_apy}`` Decimals for the requested asset (only chains
          that both responded AND list the asset)
        * ``unavailable`` is the list of chain names whose RPC fetch
          raised — included so the signal can flag partial coverage
        """
        # Fan out concurrently. Failures are caught per-chain so one dead
        # RPC doesn't poison the whole scan (graceful degradation).
        chain_names = list(self._facades.keys())
        results = await asyncio.gather(
            *(self._fetch_one(name) for name in chain_names),
            return_exceptions=True,
        )

        per_chain: dict[str, dict[str, Decimal]] = {}
        unavailable: list[str] = []
        for name, result in zip(chain_names, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("lend_overview failed for %s: %s", name, result)
                unavailable.append(name)
                continue
            reserves = list(getattr(result, "reserves", []) or [])
            target = self._find_reserve(reserves, asset_symbol)
            if target is None:
                # Asset not on this chain — neither a failure nor a
                # contributor; just skipped.
                continue
            per_chain[name] = {
                "supply_apy": Decimal(str(getattr(target, "supply_apy", 0.0))),
                "borrow_apy": Decimal(str(getattr(target, "borrow_apy", 0.0))),
            }
        return per_chain, unavailable

    async def _fetch_one(self, chain_name: str) -> Any:
        """Call ``lend_overview`` on one facade. Errors propagate to
        the gather + are caught there as ``return_exceptions=True``."""
        return await self._facades[chain_name].lend_overview()

    @staticmethod
    def _find_reserve(reserves: list[Any], symbol: str) -> Any | None:
        """Match a reserve by symbol case-insensitively.

        Aave deployments occasionally vary symbol case (``"USDC"`` vs
        ``"USDC.e"``). For wave-1 we accept exact case-insensitive
        matches only; bridged variants like ``USDC.e`` are *not*
        coalesced into the canonical asset because they're a different
        underlying token with their own peg risk.
        """
        target = symbol.upper()
        for r in reserves:
            sym = str(getattr(r, "symbol", "")).upper()
            if sym == target:
                return r
        return None


__all__ = (
    "AaveApyArbSignal",
    "CrossChainAaveScanner",
    "DEFAULT_TOP_ASSETS",
    "EXTREME_SPREAD_BPS",
    "MIN_SIGNAL_SPREAD_BPS",
    "SEVERITY_EXTREME",
    "SEVERITY_NORMAL",
    "SEVERITY_OPPORTUNITY",
)
