"""Cross-chain alpha surface for the Sentinel demo + dashboard.

Wraps :class:`lib.chains.cross_chain.aave_apy_arb.CrossChainAaveScanner`
in a synchronous, JSON-friendly entry point so the dashboard, the agent
plugin tool, and the Telegram operator can all consume cross-chain Aave
APY arbitrage signals without re-implementing the chain wiring.

Why this matters: per-chain wrappers (megaeth/arbitrum/optimism) each
expose a single chain's lend overview. Single-chain consumers cannot see
cross-chain dislocation. This module composes all three wrappers and
exports a *positive* signal — a cross-chain capital-rotation
opportunity Sapphire's multi-chain stack uniquely surfaces. Sentinel
historically traded only in *defensive* signals (chain-health BLOCK);
``scan_aave_arb`` is the first entry on the offensive side of the
ledger.

Read-only. The signal generator never executes — routing is a separate,
gated decision the operator (or a future executor) makes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from lib.chains.cross_chain.aave_apy_arb import (
    AaveApyArbSignal,
    CrossChainAaveScanner,
    DEFAULT_TOP_ASSETS,
    EXTREME_SPREAD_BPS,
    MIN_SIGNAL_SPREAD_BPS,
)

logger = logging.getLogger(__name__)


def _build_scanner_from_default_clients() -> CrossChainAaveScanner:
    """Construct a scanner wired to the three production chain facades.

    Each facade is constructed lazily (and independently) so a missing
    or unhealthy client on one chain does not block the other two —
    matches the graceful-degradation guarantee the scanner already
    enforces internally.

    Returns a scanner with whichever facades successfully wired; the
    scanner itself permits ``None`` for any per-chain facade and just
    skips that chain.
    """
    megaeth_protocols: Any | None = None
    arbitrum_protocols: Any | None = None
    optimism_protocols: Any | None = None

    # MegaETH transport ships in PR #529 (lib.chains.megaeth.client). Until
    # that lands, the client lives at plugins/claw-sapphire/tools/internal/
    # megaeth.py — try the post-merge path first, then the plugin path.
    try:
        from lib.chains.megaeth.protocols import MegaETHProtocols  # noqa: PLC0415

        megaeth_client = None
        try:
            from lib.chains.megaeth.client import MegaETHClient  # noqa: PLC0415

            megaeth_client = MegaETHClient()
        except ImportError:
            try:
                # Fallback to the plugin-tool location.
                from plugins.claw_sapphire.tools.internal.megaeth import (  # noqa: PLC0415
                    MegaETHClient as _PluginMegaETHClient,
                )

                megaeth_client = _PluginMegaETHClient()
            except Exception:
                megaeth_client = None
        if megaeth_client is not None:
            megaeth_protocols = MegaETHProtocols(megaeth_client)
    except Exception as exc:  # pragma: no cover - exercised by integration test
        logger.warning("megaeth facade unavailable: %s", exc)

    try:
        from lib.chains.arbitrum.client import ArbitrumClient  # noqa: PLC0415
        from lib.chains.arbitrum.protocols import ArbitrumProtocols  # noqa: PLC0415

        arbitrum_protocols = ArbitrumProtocols(ArbitrumClient())
    except Exception as exc:  # pragma: no cover - exercised by integration test
        logger.warning("arbitrum facade unavailable: %s", exc)

    try:
        from lib.chains.optimism.client import OptimismClient  # noqa: PLC0415
        from lib.chains.optimism.protocols import OptimismProtocols  # noqa: PLC0415

        optimism_protocols = OptimismProtocols(OptimismClient())
    except Exception as exc:  # pragma: no cover - exercised by integration test
        logger.warning("optimism facade unavailable: %s", exc)

    return CrossChainAaveScanner(
        megaeth_protocols=megaeth_protocols,
        arbitrum_protocols=arbitrum_protocols,
        optimism_protocols=optimism_protocols,
    )


def _signal_to_summary(sig: AaveApyArbSignal) -> dict[str, Any]:
    """Flatten one signal to a dashboard-friendly dict.

    All Decimals become strings; the per-chain APY snapshot keeps the
    existing chain-name keys so the dashboard table can group rows by
    chain consistently.
    """
    return {
        "asset": sig.asset,
        "severity": sig.severity,
        "direction": sig.direction,
        "max_supply_spread_bps": str(sig.max_supply_spread_bps),
        "max_borrow_spread_bps": str(sig.max_borrow_spread_bps),
        "chains": {
            name: {k: str(v) for k, v in payload.items()}
            for name, payload in sig.chains.items()
        },
        "chains_unavailable": list(sig.chains_unavailable),
    }


async def _scan_aave_arb_async(
    top_n: int,
    scanner: CrossChainAaveScanner | None,
) -> list[AaveApyArbSignal]:
    """Internal async helper so :func:`scan_aave_arb` can be sync."""
    s = scanner if scanner is not None else _build_scanner_from_default_clients()
    return await s.scan_top_assets(n=top_n)


def scan_aave_arb(
    top_n: int = 5,
    *,
    scanner: CrossChainAaveScanner | None = None,
) -> dict[str, Any]:
    """Synchronous JSON-serializable cross-chain Aave APY arb summary.

    Designed to be called from:

    * the dashboard (``/api/cross-chain/aave-arb`` endpoint, future)
    * a Sapphire plugin tool (``cross_chain_alpha.py``, future)
    * the Sentinel decision engine as a *positive* signal source

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

    On *any* uncaught failure (e.g. the entire chain stack is offline),
    returns a structured error dict so the dashboard / plugin tool
    surface a graceful empty state rather than a 500.

    ``scanner`` is injectable for tests; production callers pass nothing
    and accept the default chain-client wiring.
    """
    try:
        signals = asyncio.run(_scan_aave_arb_async(top_n=top_n, scanner=scanner))
    except Exception as exc:
        logger.exception("scan_aave_arb failed")
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
            "error": f"{type(exc).__name__}: {exc}",
        }

    summaries = [_signal_to_summary(s) for s in signals]
    max_spread = (
        max(
            (
                max(s.max_supply_spread_bps, s.max_borrow_spread_bps)
                for s in signals
            ),
            default=None,
        )
        if signals
        else None
    )

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


def is_integration_enabled() -> bool:
    """Helper used by the gated integration test + future cron-style task."""
    return os.getenv("SAPPHIRE_CROSS_CHAIN_INTEGRATION") == "1"


__all__ = (
    "is_integration_enabled",
    "scan_aave_arb",
)
