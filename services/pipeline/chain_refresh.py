"""Chain intelligence refresh — every 15 minutes via LaunchAgent.

Snapshots regime/funding/OI/TVL/stablecoins into:
    data/chain/chain_<ISO>.json        per-run snapshot (picked up by gcp_sync)
    data/intelligence/latest/chain.json symlink-friendly latest copy

The gcp_sync "regime" source discovers data/chain/*.json — every snapshot becomes
a row in sapphire.market_regime via the Cloud Function loader.

Publishes to the event bus on every run:
    regime.snapshot — always (pulse)
    regime.shifted  — only when the regime state changes from the prior run
    funding.extreme — when any perp has a crowded_* or elevated_* flag

Usage:
    python -m services.pipeline.chain_refresh
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.chain.intelligence import ChainIntelligence  # noqa: E402
from lib.core.routine_pause import abort_if_paused  # noqa: E402

log = logging.getLogger("chain_refresh")

CHAIN_DIR = ROOT / "data" / "chain"
LATEST_DIR = ROOT / "data" / "intelligence" / "latest"


def _prior_regime_state() -> str | None:
    """Read the previously-persisted chain.json and return its regime state."""
    path = LATEST_DIR / "chain.json"
    if not path.exists():
        return None
    try:
        prior = json.loads(path.read_text())
        return ((prior.get("regime") or {}).get("state")) or None
    except Exception:
        return None


def _publish_events(snap: dict, prior_state: str | None) -> None:
    """Publish regime.snapshot, regime.shifted, and funding.extreme events."""
    try:
        from lib.core.event_bus import get_bus
    except Exception as e:
        log.warning("event_bus unavailable: %s", e)
        return

    bus = get_bus()
    regime = snap.get("regime") or {}
    state = regime.get("state") or "UNKNOWN"
    payload = {
        "regime": state,
        "score": regime.get("score"),
        "confidence": regime.get("confidence"),
        "reasoning": regime.get("reasoning"),
        "since": snap.get("timestamp"),
    }
    # Always emit a pulse snapshot so subscribers can sync.
    bus.publish("regime.snapshot", payload, source="chain_refresh")

    # Emit shift only on genuine state changes (ignores score-only drift).
    if prior_state and prior_state != state:
        bus.publish(
            "regime.shifted",
            {**payload, "prior": prior_state},
            source="chain_refresh",
        )
        log.info("regime shift: %s → %s", prior_state, state)

    # Funding extremes — one event per run, batched by flag type.
    perps = ((snap.get("funding") or {}).get("perps")) or []
    flagged = [p for p in perps if (p.get("extreme_flag") or "") not in {"", None}]
    if flagged:
        # Determine a coarse bias: majority flag direction among crowded_* entries.
        crowded = [p for p in flagged if (p.get("extreme_flag") or "").startswith("crowded_")]
        bias = "neutral"
        if crowded:
            longs = sum(1 for p in crowded if p["extreme_flag"] == "crowded_long")
            shorts = sum(1 for p in crowded if p["extreme_flag"] == "crowded_short")
            bias = "long" if longs > shorts else "short" if shorts > longs else "neutral"
        bus.publish(
            "funding.extreme",
            {
                "bias": bias,
                "count": len(flagged),
                "crowded_count": len(crowded),
                "perps": [
                    {
                        "coin": p.get("coin"),
                        "rate_8h": p.get("funding_rate_8h"),
                        "flag": p.get("extreme_flag"),
                    }
                    for p in flagged[:8]
                ],
            },
            source="chain_refresh",
        )


def run() -> dict:
    CHAIN_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    prior_state = _prior_regime_state()

    ci = ChainIntelligence()
    snap = ci.snapshot()
    ts = snap.get("generated_at") or datetime.now(UTC).isoformat()
    snap["timestamp"] = ts

    fname = f"chain_{ts.replace(':', '-')}.json"
    per_run = CHAIN_DIR / fname
    per_run.write_text(json.dumps(snap, indent=2, default=str))

    latest = LATEST_DIR / "chain.json"
    latest.write_text(json.dumps(snap, indent=2, default=str))

    _publish_events(snap, prior_state)

    log.info("chain snapshot written: %s", per_run)
    return {
        "path": str(per_run),
        "regime": (snap.get("regime") or {}).get("state"),
        "prior_regime": prior_state,
        "shifted": bool(prior_state and prior_state != ((snap.get("regime") or {}).get("state"))),
    }


def main() -> int:
    abort_if_paused("chain-refresh")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        # Route INFO/DEBUG to stdout so the LaunchAgent's *-err.log only
        # captures real errors and exceptions (tracebacks still go to
        # stderr naturally).
        stream=sys.stdout,
    )
    try:
        out = run()
    except Exception as e:
        log.exception("chain refresh failed: %s", e)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
