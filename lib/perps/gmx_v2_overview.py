"""Cross-chain GMX V2 perps overview — funding APR + OI skew.

This module is the multi-chain analog of
:mod:`lib.hackathon.cross_chain_alpha`: it composes per-chain GMX V2
read-only wrappers (MegaETH chain 4326, Arbitrum chain 42161) into one
JSON-friendly summary the dashboard, the agent, and Telegram operator
can all consume.

What the dashboard panel shows
==============================

- Per-market funding APR (signed: positive = longs pay shorts).
- Per-market open-interest skew (long share of total OI, in [0, 1]).
- A severity badge keyed off |APR| > 50% or |skew - 0.5| > 0.2.
- A side recommendation: ``long collects funding`` when APR < 0,
  ``short collects funding`` when APR > 0.
- A cross-chain divergence figure for ETH (and other shared markets)
  in basis points, so operators can see at a glance whether the same
  underlying is running diverged funding across chains.

Why this matters
================

Funding-rate divergence across chains is a real, persistent
edge — when GMX MegaETH ETH/USD funds at +56% APR while Arbitrum
GMX V2 ETH/USD funds at +2% APR, that 5,400+ bps spread is an
arbitrage opportunity (short the high-funding venue, long the low-
funding venue, collect the carry). This panel surfaces those signals
visually for both demo and ongoing operator awareness.

Wiring strategy
===============

Each chain wrapper is constructed lazily and independently. If the
GMX V2 ``Reader`` wrapper has not been merged on a given chain yet
(Wave B.3 + B.4 lane), the scanner gracefully degrades to a
documented ``sample`` payload labeled ``mode: "sample"`` so the
panel still demonstrates the visual surface end-to-end. Once both
wrappers ship (PRs in flight as of 2026-05-02), production callers
get ``mode: "live"`` automatically with no API change.

This mirrors the graceful-degradation guarantee in
:func:`lib.hackathon.cross_chain_alpha.scan_aave_arb` — chain stack
unhealthy → structured empty / sample payload, never a 500.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Severity thresholds. EXTREME is the load-bearing demo signal:
# anything beyond ±50% APR is a screaming carry opportunity.
EXTREME_FUNDING_ABS_APR = Decimal("0.50")
WARN_FUNDING_ABS_APR = Decimal("0.20")
EXTREME_SKEW_DELTA = Decimal("0.20")  # |skew - 0.5| > 0.2 ⇒ extreme

CHAIN_ID_MEGAETH = 4326
CHAIN_ID_ARBITRUM = 42161

CHAIN_NAME_BY_ID: dict[int, str] = {
    CHAIN_ID_MEGAETH: "MegaETH",
    CHAIN_ID_ARBITRUM: "Arbitrum",
}


@dataclass(frozen=True)
class PerpsMarketSnapshot:
    """One GMX V2 market state, normalized for cross-chain comparison.

    All numeric fields are :class:`~decimal.Decimal` for full precision
    until the JSON serialization layer stringifies them.
    """

    chain_id: int
    chain_name: str  # "MegaETH" / "Arbitrum"
    market_name: str  # human-readable e.g. "ETH/USD"
    market_address: str  # GMX market token address (lowercased)
    funding_apr: Decimal  # signed annualized fraction (0.56 == +56%)
    funding_direction: str  # "longs_pay_shorts" | "shorts_pay_longs"
    open_interest_long_usd: Decimal
    open_interest_short_usd: Decimal
    skew: Decimal  # long_oi / (long_oi + short_oi); 0.5 == balanced
    mark_price_usd: Decimal | None  # may be None when off-chain price feed unavailable
    severity: str  # "NORMAL" | "WARN" | "EXTREME"
    side_recommendation: str  # human-readable directional hint


def _classify_severity(funding_apr: Decimal, skew: Decimal) -> str:
    """Map (funding_apr, skew) → NORMAL / WARN / EXTREME.

    EXTREME if |APR| > 50% OR skew leaves [0.30, 0.70].
    WARN    if |APR| > 20% OR skew leaves [0.40, 0.60].
    NORMAL otherwise.
    """
    abs_apr = abs(funding_apr)
    skew_delta = abs(skew - Decimal("0.5"))
    if abs_apr > EXTREME_FUNDING_ABS_APR or skew_delta > EXTREME_SKEW_DELTA:
        return "EXTREME"
    if abs_apr > WARN_FUNDING_ABS_APR or skew_delta > Decimal("0.10"):
        return "WARN"
    return "NORMAL"


def _side_recommendation(funding_apr: Decimal) -> str:
    """Human-readable hint for which side currently collects funding.

    GMX V2 funding pays the *underweighted* side. When ``funding_apr > 0``
    (longs pay shorts), the short side collects. Inverse when negative.
    """
    if funding_apr > 0:
        return "short collects funding"
    if funding_apr < 0:
        return "long collects funding"
    return "balanced — no funding edge"


def _snapshot_to_dict(snap: PerpsMarketSnapshot) -> dict[str, Any]:
    """Flatten one snapshot to a JSON-serializable dict (Decimals → strings)."""
    raw = asdict(snap)
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Sample payload — used when live GMX V2 wrappers are not wired on this
# branch. Funding rates are calibrated to the 2026-05-02 mainnet snapshot
# captured by the ops team (BTC -43% / -15%, ETH +56% / +2%) so the demo
# is grounded in real numbers and the panel renders correctly out of the
# box. Once the live wrappers land, the production path replaces this.
# ---------------------------------------------------------------------------

_SAMPLE_MARKETS: tuple[PerpsMarketSnapshot, ...] = (
    PerpsMarketSnapshot(
        chain_id=CHAIN_ID_MEGAETH,
        chain_name="MegaETH",
        market_name="ETH/USD MegaETH 0.3%",
        market_address="0x" + "ee" + "0" * 38,
        funding_apr=Decimal("0.5612"),
        funding_direction="longs_pay_shorts",
        open_interest_long_usd=Decimal("8425000"),
        open_interest_short_usd=Decimal("1860000"),
        skew=Decimal("0.819"),
        mark_price_usd=Decimal("3142.55"),
        severity="EXTREME",
        side_recommendation="short collects funding",
    ),
    PerpsMarketSnapshot(
        chain_id=CHAIN_ID_MEGAETH,
        chain_name="MegaETH",
        market_name="BTC/USD MegaETH 0.3%",
        market_address="0x" + "bb" + "0" * 38,
        funding_apr=Decimal("-0.4318"),
        funding_direction="shorts_pay_longs",
        open_interest_long_usd=Decimal("1240000"),
        open_interest_short_usd=Decimal("4905000"),
        skew=Decimal("0.202"),
        mark_price_usd=Decimal("76812.40"),
        severity="EXTREME",
        side_recommendation="long collects funding",
    ),
    PerpsMarketSnapshot(
        chain_id=CHAIN_ID_ARBITRUM,
        chain_name="Arbitrum",
        market_name="ETH/USD Arbitrum",
        market_address="0x" + "ea" + "0" * 38,
        funding_apr=Decimal("0.0213"),
        funding_direction="longs_pay_shorts",
        open_interest_long_usd=Decimal("142500000"),
        open_interest_short_usd=Decimal("128300000"),
        skew=Decimal("0.526"),
        mark_price_usd=Decimal("3140.18"),
        severity="NORMAL",
        side_recommendation="short collects funding",
    ),
    PerpsMarketSnapshot(
        chain_id=CHAIN_ID_ARBITRUM,
        chain_name="Arbitrum",
        market_name="BTC/USD Arbitrum",
        market_address="0x" + "ba" + "0" * 38,
        funding_apr=Decimal("-0.1502"),
        funding_direction="shorts_pay_longs",
        open_interest_long_usd=Decimal("82400000"),
        open_interest_short_usd=Decimal("106700000"),
        skew=Decimal("0.436"),
        mark_price_usd=Decimal("76798.91"),
        severity="WARN",
        side_recommendation="long collects funding",
    ),
)


# ---------------------------------------------------------------------------
# Cross-chain divergence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingDivergence:
    """One same-underlying funding divergence between two chains.

    ``divergence_bps`` is signed: positive means chain A funds *higher*
    than chain B (i.e. the long side on A is paying more vs. shorts than
    on B). The strategy lane uses the absolute value to size opportunity.
    """

    underlying: str  # "ETH" / "BTC"
    chain_a: str  # "MegaETH"
    chain_b: str  # "Arbitrum"
    apr_a: Decimal
    apr_b: Decimal
    divergence_bps: Decimal  # (apr_a - apr_b) * 10_000


def _underlying_from_market_name(name: str) -> str | None:
    """Best-effort underlying parse from a GMX market display name.

    GMX V2 market names follow ``<INDEX>/<QUOTE> <chain> <fee>`` — we
    strip the slash-quote and any trailing chain/fee modifiers.
    """
    if not name:
        return None
    head = name.split(" ", 1)[0]
    return head.split("/", 1)[0].upper() if "/" in head else None


def compute_cross_chain_divergence(
    snapshots: list[PerpsMarketSnapshot],
) -> list[FundingDivergence]:
    """Pair MegaETH vs. Arbitrum snapshots by underlying and compute spread."""
    by_underlying: dict[str, dict[str, PerpsMarketSnapshot]] = {}
    for snap in snapshots:
        underlying = _underlying_from_market_name(snap.market_name)
        if underlying is None:
            continue
        by_underlying.setdefault(underlying, {})[snap.chain_name] = snap

    out: list[FundingDivergence] = []
    for underlying, by_chain in by_underlying.items():
        a = by_chain.get("MegaETH")
        b = by_chain.get("Arbitrum")
        if a is None or b is None:
            continue
        out.append(
            FundingDivergence(
                underlying=underlying,
                chain_a=a.chain_name,
                chain_b=b.chain_name,
                apr_a=a.funding_apr,
                apr_b=b.funding_apr,
                divergence_bps=(a.funding_apr - b.funding_apr) * Decimal(10_000),
            )
        )
    return out


def _divergence_to_dict(div: FundingDivergence) -> dict[str, Any]:
    raw = asdict(div)
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Live wrappers — lazy import so missing deps degrade gracefully
# ---------------------------------------------------------------------------


@dataclass
class _ChainWiring:
    """Resolved per-chain wrapper bundle (or None when not yet shipped)."""

    chain_id: int
    chain_name: str
    gmx_v2_wrapper: Any | None = None
    error: str | None = None


def _build_megaeth_wiring() -> _ChainWiring:
    wiring = _ChainWiring(chain_id=CHAIN_ID_MEGAETH, chain_name="MegaETH")
    try:
        from lib.chains.megaeth.client import MegaETHClient  # noqa: PLC0415
        from lib.chains.megaeth.contracts.gmx_v2 import (  # noqa: PLC0415
            GmxV2,
            GmxV2Addresses,
        )
        from lib.chains.megaeth.registry import ProtocolRegistry  # noqa: PLC0415

        registry = ProtocolRegistry.from_yaml()
        try:
            entry = registry.get("gmx_v2")
        except Exception as exc:
            wiring.error = f"gmx_v2 not in MegaETH registry: {exc}"
            return wiring
        client = MegaETHClient()
        wiring.gmx_v2_wrapper = GmxV2(client, GmxV2Addresses.from_registry_entry(entry))
    except ImportError as exc:
        wiring.error = f"megaeth gmx_v2 wrapper not yet shipped: {exc}"
    except Exception as exc:  # pragma: no cover — exercised by integration test
        wiring.error = f"megaeth wiring failed: {type(exc).__name__}: {exc}"
    return wiring


def _build_arbitrum_wiring() -> _ChainWiring:
    wiring = _ChainWiring(chain_id=CHAIN_ID_ARBITRUM, chain_name="Arbitrum")
    try:
        from lib.chains.arbitrum.client import ArbitrumClient  # noqa: PLC0415
        from lib.chains.arbitrum.contracts.gmx_v2 import (  # noqa: PLC0415
            GmxV2,
            GmxV2Addresses,
        )
        from lib.chains.arbitrum.registry import ProtocolRegistry  # noqa: PLC0415

        registry = ProtocolRegistry.from_yaml()
        try:
            entry = registry.get("gmx_v2")
        except Exception as exc:
            wiring.error = f"gmx_v2 not in Arbitrum registry: {exc}"
            return wiring
        client = ArbitrumClient()
        wiring.gmx_v2_wrapper = GmxV2(client, GmxV2Addresses.from_registry_entry(entry))
    except ImportError as exc:
        wiring.error = f"arbitrum gmx_v2 wrapper not yet shipped: {exc}"
    except Exception as exc:  # pragma: no cover
        wiring.error = f"arbitrum wiring failed: {type(exc).__name__}: {exc}"
    return wiring


async def _scan_chain_live(wiring: _ChainWiring) -> list[PerpsMarketSnapshot]:
    """Pull funding APR + OI for every priced market on one chain.

    Defensive: any single market failure is swallowed (logged) so the
    overall scan still surfaces the markets that DID resolve. Empty
    list is a valid return when no markets are priceable.
    """
    if wiring.gmx_v2_wrapper is None:
        return []
    out: list[PerpsMarketSnapshot] = []
    try:
        markets = await wiring.gmx_v2_wrapper.list_markets()
    except Exception as exc:
        logger.warning("list_markets failed on %s: %s", wiring.chain_name, exc)
        return []

    for market in markets:
        try:
            # Live wrappers require an oracle-fed Price.Props tuple;
            # callers wire that via a chain-specific price adapter
            # (Wave B.4). Until that lands the per-market call may
            # raise — we swallow, log, and continue so a partial
            # outage produces a partial view instead of an empty page.
            prices = await wiring.gmx_v2_wrapper.fetch_prices(market)  # type: ignore[attr-defined]
            info = await wiring.gmx_v2_wrapper.market_info(market.market_token, prices)
            apr = wiring.gmx_v2_wrapper._funding_apr_from_info(info)  # type: ignore[attr-defined]
            skew = wiring.gmx_v2_wrapper._oi_skew_from_info(info)  # type: ignore[attr-defined]
            from decimal import Decimal as _D

            long_usd = _D(int(info.open_interest_long)) / _D(10) ** 30
            short_usd = _D(int(info.open_interest_short)) / _D(10) ** 30
            mark = None
            try:
                mark = (_D(int(prices[0][0]) + int(prices[0][1])) / _D(2)) / (_D(10) ** _D(30 - 18))
            except Exception:
                mark = None
            severity = _classify_severity(apr, skew)
            out.append(
                PerpsMarketSnapshot(
                    chain_id=wiring.chain_id,
                    chain_name=wiring.chain_name,
                    market_name=market.name,
                    market_address=market.market_token,
                    funding_apr=apr,
                    funding_direction=(
                        "longs_pay_shorts" if info.longs_pay_shorts else "shorts_pay_longs"
                    ),
                    open_interest_long_usd=long_usd,
                    open_interest_short_usd=short_usd,
                    skew=skew,
                    mark_price_usd=mark,
                    severity=severity,
                    side_recommendation=_side_recommendation(apr),
                )
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "market_info failed on %s/%s: %s",
                wiring.chain_name,
                getattr(market, "name", "<unknown>"),
                exc,
            )
            continue
    return out


async def _scan_all_chains_live() -> tuple[list[PerpsMarketSnapshot], list[str]]:
    """Run both per-chain live scans concurrently. Returns (snapshots, wiring_errors)."""
    wirings = [_build_megaeth_wiring(), _build_arbitrum_wiring()]
    errors = [w.error for w in wirings if w.error]
    results = await asyncio.gather(*(_scan_chain_live(w) for w in wirings), return_exceptions=True)
    snapshots: list[PerpsMarketSnapshot] = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(f"{type(r).__name__}: {r}")
            continue
        snapshots.extend(r)
    return snapshots, errors


# ---------------------------------------------------------------------------
# Public sync entry point — what the dashboard route calls
# ---------------------------------------------------------------------------


def scan_perps_overview(
    *,
    snapshots: list[PerpsMarketSnapshot] | None = None,
    force_sample: bool = False,
) -> dict[str, Any]:
    """Synchronous JSON-serializable cross-chain GMX V2 perps overview.

    Returns a dict with this shape::

        {
            "mode": "live" | "sample" | "empty",
            "markets": [ {<flattened snapshot>}, ... ],
            "by_chain": { "4326": [...], "42161": [...] },
            "cross_chain_funding_divergence": [
                { "underlying": "ETH", "chain_a": "MegaETH",
                  "chain_b": "Arbitrum", "apr_a": "0.5612",
                  "apr_b": "0.0213", "divergence_bps": "5399.00" },
                ...
            ],
            "max_abs_divergence_bps": "<Decimal-as-str>" | None,
            "extreme_count": <int>,
            "wiring_errors": ["..."],
            "thresholds": {
                "extreme_funding_abs_apr": "0.50",
                "warn_funding_abs_apr": "0.20",
                "extreme_skew_delta": "0.20",
            },
        }

    Parameters
    ----------
    snapshots
        Inject pre-built snapshots for tests; production callers pass
        nothing and accept the live-wiring default.
    force_sample
        When True, skip live scanning and return the sample payload.
        Useful for offline demo recordings.
    """
    wiring_errors: list[str] = []

    if snapshots is None:
        if force_sample or _force_sample_from_env():
            snapshots = list(_SAMPLE_MARKETS)
            mode = "sample"
        else:
            try:
                live, wiring_errors = asyncio.run(_scan_all_chains_live())
            except Exception as exc:
                logger.exception("scan_perps_overview live path failed")
                wiring_errors.append(f"{type(exc).__name__}: {exc}")
                live = []
            if not live:
                # Live wiring not yet shipped on this branch (Wave B.4 in
                # flight) → fall through to the sample payload so the
                # demo + panel still render. Tagged ``mode: "sample"``.
                snapshots = list(_SAMPLE_MARKETS)
                mode = "sample"
            else:
                snapshots = live
                mode = "live"
    else:
        mode = "live"

    if not snapshots:
        return _empty_payload(wiring_errors)

    # Group by chain id (string keys for JSON-friendliness).
    by_chain: dict[str, list[dict[str, Any]]] = {}
    for snap in snapshots:
        by_chain.setdefault(str(snap.chain_id), []).append(_snapshot_to_dict(snap))

    divs = compute_cross_chain_divergence(snapshots)
    div_dicts = [_divergence_to_dict(d) for d in divs]
    max_abs = max((abs(d.divergence_bps) for d in divs), default=None) if divs else None
    extreme_count = sum(1 for s in snapshots if s.severity == "EXTREME")

    return {
        "mode": mode,
        "markets": [_snapshot_to_dict(s) for s in snapshots],
        "by_chain": by_chain,
        "chain_names": dict(CHAIN_NAME_BY_ID),
        "cross_chain_funding_divergence": div_dicts,
        "max_abs_divergence_bps": str(max_abs) if max_abs is not None else None,
        "extreme_count": extreme_count,
        "wiring_errors": wiring_errors,
        "thresholds": {
            "extreme_funding_abs_apr": str(EXTREME_FUNDING_ABS_APR),
            "warn_funding_abs_apr": str(WARN_FUNDING_ABS_APR),
            "extreme_skew_delta": str(EXTREME_SKEW_DELTA),
        },
    }


def _empty_payload(wiring_errors: list[str]) -> dict[str, Any]:
    """Structured empty state — both chains returned no priced markets."""
    return {
        "mode": "empty",
        "markets": [],
        "by_chain": {},
        "chain_names": dict(CHAIN_NAME_BY_ID),
        "cross_chain_funding_divergence": [],
        "max_abs_divergence_bps": None,
        "extreme_count": 0,
        "wiring_errors": wiring_errors,
        "thresholds": {
            "extreme_funding_abs_apr": str(EXTREME_FUNDING_ABS_APR),
            "warn_funding_abs_apr": str(WARN_FUNDING_ABS_APR),
            "extreme_skew_delta": str(EXTREME_SKEW_DELTA),
        },
    }


def _force_sample_from_env() -> bool:
    return os.getenv("SAPPHIRE_PERPS_FORCE_SAMPLE") == "1"


def is_integration_enabled() -> bool:
    """Helper used by the gated live integration test."""
    return os.getenv("SAPPHIRE_PERPS_INTEGRATION") == "1"


__all__ = (
    "EXTREME_FUNDING_ABS_APR",
    "EXTREME_SKEW_DELTA",
    "FundingDivergence",
    "PerpsMarketSnapshot",
    "WARN_FUNDING_ABS_APR",
    "compute_cross_chain_divergence",
    "is_integration_enabled",
    "scan_perps_overview",
)
