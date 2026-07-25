"""Cross-chain alpha surface for the Sentinel demo + dashboard.

Wraps the cross-chain primitives (Aave APY arb + Pyth price divergence)
in synchronous, JSON-friendly entry points so the dashboard, the agent
plugin tool, and the Telegram operator can consume cross-chain signals
without re-implementing the chain wiring.

Why this matters: per-chain wrappers (megaeth/arbitrum/optimism) each
expose a single chain's view. Single-chain consumers cannot see
cross-chain dislocation. This module composes the primitives across
chains and exports *positive* signals — capital-rotation and
oracle-divergence opportunities Sapphire's multi-chain stack uniquely
surfaces. Together :func:`scan_aave_arb` and
:func:`scan_pyth_divergence` substantiate "Sapphire is the canonical
multi-chain alpha-discovery layer" rather than just claiming
portability.

Read-only. Signal generators never execute — routing is a separate,
gated decision the operator (or a future executor) makes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from lib.chains.cross_chain.pyth_divergence import (
    DEFAULT_TOP_ASSETS as PYTH_DEFAULT_TOP_ASSETS,
)
from lib.chains.cross_chain.pyth_divergence import (
    EXTREME_DIVERGENCE_BPS,
    MIN_SIGNAL_DIVERGENCE_BPS,
    CrossChainPythScanner,
    PythDivergenceSignal,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aave APY arb — first cross-chain primitive (companion to Pyth divergence)
# ---------------------------------------------------------------------------


async def _scan_aave_arb_async(top_n: int, scanner: Any | None = None) -> list[Any]:
    """Internal async helper so :func:`scan_aave_arb` can be sync.

    ``scanner`` is injectable so callers (and tests) can supply per-chain
    protocol facades. A bare ``CrossChainAaveScanner()`` registers **no**
    facades and therefore silently yields zero signals — see
    :func:`scan_aave_arb`, which rejects that case rather than reporting an
    empty scan as a successful one.
    """
    if scanner is None:
        from lib.chains.cross_chain.aave_apy_arb import CrossChainAaveScanner

        scanner = CrossChainAaveScanner()
    return await scanner.scan_top_assets(n=top_n)


def scan_aave_arb(top_n: int = 5, scanner: Any | None = None) -> dict[str, Any]:
    """Synchronous JSON-serializable cross-chain Aave APY arbitrage summary.

    Returns a dict with this shape::

        {
            "top_n": 5,
            "signals": [ {<summary>}, ... ],   # length 0..top_n
            "signal_count": <int>,
            "max_spread_bps": "<Decimal-as-str>" | None,
            "thresholds": {
                "min_signal_spread_bps": "50",
                "extreme_spread_bps": "200",
            },
            "candidate_assets": ["USDC", "USDT", "DAI", "WETH", "WBTC"],
            "error": "<str>" | not present,
        }

    On *any* uncaught failure returns a structured error dict so the
    dashboard / plugin tool surface a graceful empty state rather than
    a 500.

    When no ``scanner`` is supplied, the default has zero per-chain facades
    wired and cannot produce signals. That is reported as an explicit
    ``error`` — an unwired scanner must not be presented as "scanned
    successfully, no opportunities found".
    """
    from lib.chains.cross_chain.aave_apy_arb import (
        DEFAULT_TOP_ASSETS,
        EXTREME_SPREAD_BPS,
        MIN_SIGNAL_SPREAD_BPS,
    )

    def _empty(error: str) -> dict[str, Any]:
        return {
            "top_n": top_n,
            "signals": [],
            "signal_count": 0,
            "max_spread_bps": None,
            "thresholds": {
                "min_signal_spread_bps": str(MIN_SIGNAL_SPREAD_BPS),
                "extreme_spread_bps": str(EXTREME_SPREAD_BPS),
            },
            "candidate_assets": list(DEFAULT_TOP_ASSETS),
            "error": error,
        }

    if scanner is None:
        return _empty(
            "not wired: no per-chain Aave facades configured. Pass scanner= "
            "with MegaETHProtocols / ArbitrumProtocols / OptimismProtocols "
            "built on live RPC clients."
        )

    try:
        signals = asyncio.run(_scan_aave_arb_async(top_n=top_n, scanner=scanner))
    except Exception as exc:
        logger.exception("scan_aave_arb failed")
        return _empty(f"{type(exc).__name__}: {exc}")

    summaries = []
    for s in signals:
        summaries.append(
            {
                "asset": s.asset,
                "severity": s.severity,
                "direction": s.direction,
                "max_supply_spread_bps": str(s.max_supply_spread_bps),
                "max_borrow_spread_bps": str(s.max_borrow_spread_bps),
                "chains": {
                    name: {
                        "supply_apy": str(v["supply_apy"]),
                        "borrow_apy": str(v["borrow_apy"]),
                    }
                    for name, v in s.chains.items()
                },
                "chains_unavailable": list(s.chains_unavailable),
            }
        )

    max_spread = max((s.max_supply_spread_bps for s in signals), default=None) if signals else None

    return {
        "top_n": top_n,
        "signals": summaries,
        "signal_count": len(summaries),
        "max_spread_bps": str(max_spread) if max_spread is not None else None,
        "thresholds": {
            "min_signal_spread_bps": str(MIN_SIGNAL_SPREAD_BPS),
            "extreme_spread_bps": str(EXTREME_SPREAD_BPS),
        },
        "candidate_assets": list(DEFAULT_TOP_ASSETS),
    }


# ---------------------------------------------------------------------------
# Pyth divergence — second cross-chain primitive (companion to Aave arb)
# ---------------------------------------------------------------------------


def _build_pyth_scanner_from_default_clients() -> CrossChainPythScanner:
    """Construct a Pyth scanner wired to the per-chain registries.

    Each registry is constructed lazily and independently so a missing
    or unhealthy client on one chain does not block the others —
    matches the graceful-degradation guarantee the scanner already
    enforces internally.

    MegaETH and Optimism Pyth wrappers ship in parallel branches; until
    they land on main this function gracefully ends up with only the
    Arbitrum registry wired and the scanner correctly returns no
    signals (need >=2 chains for a divergence). That's the right
    behaviour: the scanner reports what it can see honestly rather
    than fabricating a single-chain "divergence".
    """
    megaeth_pyth: Any | None = None
    arbitrum_pyth: Any | None = None
    optimism_pyth: Any | None = None

    try:
        from lib.chains.megaeth.client import MegaETHClient  # noqa: PLC0415
        from lib.chains.megaeth.contracts.pyth_oracle import (  # noqa: PLC0415
            PythRegistry as MegaPythRegistry,
        )

        megaeth_pyth = MegaPythRegistry(MegaETHClient())
    except Exception as exc:  # pragma: no cover — exercised by integration test
        logger.warning("MegaETH Pyth registry unavailable: %s", exc)

    try:
        from lib.chains.arbitrum.client import ArbitrumClient  # noqa: PLC0415
        from lib.chains.arbitrum.contracts.pyth_oracle import (  # noqa: PLC0415
            PythRegistry as ArbPythRegistry,
        )

        arbitrum_pyth = ArbPythRegistry(ArbitrumClient())
    except Exception as exc:  # pragma: no cover
        logger.warning("Arbitrum Pyth registry unavailable: %s", exc)

    try:
        from lib.chains.optimism.client import OptimismClient  # noqa: I001, PLC0415
        from lib.chains.optimism.contracts.pyth_oracle import (  # noqa: PLC0415
            PythRegistry as OpPythRegistry,
        )

        optimism_pyth = OpPythRegistry(OptimismClient())
    except Exception as exc:  # pragma: no cover
        logger.warning("Optimism Pyth registry unavailable: %s", exc)

    return CrossChainPythScanner(
        megaeth_pyth=megaeth_pyth,
        arbitrum_pyth=arbitrum_pyth,
        optimism_pyth=optimism_pyth,
    )


def _pyth_signal_to_summary(sig: PythDivergenceSignal) -> dict[str, Any]:
    """Flatten one Pyth divergence signal to a dashboard-friendly dict.

    Decimals → strings; per-chain payload preserves the chain-name
    keys so the dashboard table can group rows by chain consistently
    with the Aave-arb table.
    """
    return {
        "asset": sig.asset,
        "severity": sig.severity,
        "max_divergence_bps": str(sig.max_divergence_bps),
        "freshest_chain": sig.freshest_chain,
        "stalest_chain": sig.stalest_chain,
        "any_stale": bool(sig.any_stale),
        "chains": {
            name: {
                "price": str(payload["price"]),
                "publish_time": int(payload["publish_time"]),
                "stale": bool(payload["stale"]),
                "source_address": str(payload["source_address"]),
            }
            for name, payload in sig.chains.items()
        },
        "chains_unavailable": list(sig.chains_unavailable),
    }


async def _scan_pyth_divergence_async(
    top_n: int,
    scanner: CrossChainPythScanner | None,
) -> list[PythDivergenceSignal]:
    """Internal async helper so :func:`scan_pyth_divergence` can be sync."""
    s = scanner if scanner is not None else _build_pyth_scanner_from_default_clients()
    return await s.scan_top_assets(n=top_n)


def scan_pyth_divergence(
    top_n: int = 5,
    *,
    scanner: CrossChainPythScanner | None = None,
) -> dict[str, Any]:
    """Synchronous JSON-serializable cross-chain Pyth divergence summary.

    Designed to be called from:

    * the dashboard (``/api/cross-chain/pyth-divergence`` endpoint, future)
    * a Sapphire plugin tool
    * the Sentinel decision engine as a *positive* signal source

    Returns a dict with this shape::

        {
            "top_n": 5,
            "signals": [ {<summary>}, ... ],   # length 0..top_n
            "signal_count": <int>,
            "max_divergence_bps": "<Decimal-as-str>" | None,
            "any_stale": <bool>,
            "thresholds": {
                "min_signal_divergence_bps": "20",
                "extreme_divergence_bps": "100",
            },
            "candidate_assets": ["BTC", "ETH", "SOL", "USDC", "USDT"],
            "error": "<str>" | not present,
        }

    On *any* uncaught failure (e.g. the entire chain stack offline),
    returns a structured error dict so the dashboard / plugin tool
    surface a graceful empty state rather than a 500.

    ``scanner`` is injectable for tests; production callers pass
    nothing and accept the default chain-client wiring.
    """
    try:
        signals = asyncio.run(_scan_pyth_divergence_async(top_n=top_n, scanner=scanner))
    except Exception as exc:
        logger.exception("scan_pyth_divergence failed")
        return {
            "top_n": top_n,
            "signals": [],
            "signal_count": 0,
            "max_divergence_bps": None,
            "any_stale": False,
            "thresholds": {
                "min_signal_divergence_bps": str(MIN_SIGNAL_DIVERGENCE_BPS),
                "extreme_divergence_bps": str(EXTREME_DIVERGENCE_BPS),
            },
            "candidate_assets": list(PYTH_DEFAULT_TOP_ASSETS),
            "error": f"{type(exc).__name__}: {exc}",
        }

    summaries = [_pyth_signal_to_summary(s) for s in signals]
    max_div = max((s.max_divergence_bps for s in signals), default=None) if signals else None
    any_stale = any(s.any_stale for s in signals)

    return {
        "top_n": top_n,
        "signals": summaries,
        "signal_count": len(summaries),
        "max_divergence_bps": str(max_div) if max_div is not None else None,
        "any_stale": any_stale,
        "thresholds": {
            "min_signal_divergence_bps": str(MIN_SIGNAL_DIVERGENCE_BPS),
            "extreme_divergence_bps": str(EXTREME_DIVERGENCE_BPS),
        },
        "candidate_assets": list(PYTH_DEFAULT_TOP_ASSETS),
    }


def is_integration_enabled() -> bool:
    """Helper used by the gated integration test + future cron-style task."""
    return os.getenv("SAPPHIRE_CROSS_CHAIN_INTEGRATION") == "1"


__all__ = (
    "is_integration_enabled",
    "scan_aave_arb",
    "scan_pyth_divergence",
)
