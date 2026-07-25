"""Chain intelligence refresh — every 15 minutes via LaunchAgent.

Snapshots regime/funding/OI/TVL/stablecoins into:
    data/chain/chain_<ISO>.json        per-run snapshot (picked up by gcp_sync)
    data/intelligence/latest/chain.json symlink-friendly latest copy

The gcp_sync "regime" source discovers data/chain/*.json — every snapshot becomes
a row in sapphire.market_regime via the Cloud Function loader.

Publishes to the event bus on every run:
    regime.snapshot — always (pulse)
    regime.shifted  — only when the regime state changes from the prior run
    funding.extreme — when BTC or ETH 8h funding is crowded_* / elevated_*

Snapshot shape reminder — `ChainIntelligence.snapshot()` emits a FLAT dict:
    {timestamp, unix_ts, fear_greed, btc_funding_rate_pct, eth_funding_rate_pct,
     btc_dominance, ..., classification: {regime, score, inputs_ok, inputs_total}}
Regime state lives at `classification.regime`; funding is two scalar rates in
percent (no per-venue perps list — that lives in `lib.intel.market_intelligence`
if wired). Reading a nested `snap["regime"]["state"]` or `snap["funding"]["perps"]`
silently returns "UNKNOWN"/empty and disables every downstream subscriber.

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

from lib.analytics.signal_enhancer import _funding_flag  # noqa: E402 — shared threshold
from lib.chain.intelligence import ChainIntelligence  # noqa: E402
from lib.core.routine_pause import abort_if_paused  # noqa: E402

log = logging.getLogger("chain_refresh")

CHAIN_DIR = ROOT / "data" / "chain"
LATEST_DIR = ROOT / "data" / "intelligence" / "latest"


def _regime_state(snap: dict) -> str:
    """Extract the regime state string from a flat snapshot.

    Handles both the in-process `Regime` enum and the plain string that survives
    a JSON round-trip. Returns "UNKNOWN" when classification is absent so
    downstream never sees None.
    """
    clf = snap.get("classification") or {}
    raw = clf.get("regime")
    if raw is None:
        return "UNKNOWN"
    return raw.value if hasattr(raw, "value") else str(raw)


def _regime_confidence(snap: dict) -> float | None:
    """`inputs_ok / inputs_total` from the classification block, or None."""
    clf = snap.get("classification") or {}
    total = clf.get("inputs_total")
    ok = clf.get("inputs_ok")
    if not total:
        return None
    try:
        return float(ok or 0) / float(total)
    except (TypeError, ValueError):
        return None


def _build_perps(snap: dict) -> list[dict]:
    """Synthesize a perps list from the flat snapshot's BTC/ETH funding rates.

    The chain snapshot only carries two scalar 8h-funding percentages; there is
    no per-venue perps series. This normalizes those two rates into the shape
    downstream subscribers (dashboard, alerts) already expect: `coin`,
    `funding_rate_8h` (as a fraction — matches signal_enhancer's convention),
    `extreme_flag`. Missing rates are skipped, never emitted as 0.
    """
    perps: list[dict] = []
    for coin, key in (("BTC", "btc_funding_rate_pct"), ("ETH", "eth_funding_rate_pct")):
        raw = snap.get(key)
        if raw is None:
            continue
        try:
            pct = float(raw)
        except (TypeError, ValueError):
            continue
        perps.append(
            {
                "coin": coin,
                "funding_rate_8h": pct / 100.0,
                "extreme_flag": _funding_flag(pct),
            }
        )
    return perps


def _prior_regime_state() -> str | None:
    """Read the previously-persisted chain.json and return its regime state.

    Snapshots on disk use the flat shape (`classification.regime`). Legacy
    files written by the pre-fix version had no regime key at all, in which
    case _regime_state() returns "UNKNOWN" and we treat that as "no prior".
    """
    path = LATEST_DIR / "chain.json"
    if not path.exists():
        return None
    try:
        prior = json.loads(path.read_text())
    except Exception:
        return None
    state = _regime_state(prior)
    return state if state != "UNKNOWN" else None


def _publish_events(snap: dict, prior_state: str | None) -> None:
    """Publish regime.snapshot, regime.shifted, and funding.extreme events."""
    try:
        from lib.core.event_bus import get_bus
    except Exception as e:
        log.warning("event_bus unavailable: %s", e)
        return

    bus = get_bus()
    clf = snap.get("classification") or {}
    state = _regime_state(snap)
    payload = {
        "regime": state,
        "score": clf.get("score"),
        "confidence": _regime_confidence(snap),
        "reasons": clf.get("reasons") or [],
        "since": snap.get("timestamp"),
    }
    bus.publish("regime.snapshot", payload, source="chain_refresh")

    if prior_state and prior_state != state and state != "UNKNOWN":
        bus.publish(
            "regime.shifted",
            {**payload, "prior": prior_state},
            source="chain_refresh",
        )
        log.info("regime shift: %s → %s", prior_state, state)

    perps = _build_perps(snap)
    flagged = [p for p in perps if p.get("extreme_flag")]
    if flagged:
        crowded = [p for p in flagged if p["extreme_flag"].startswith("crowded_")]
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
                    for p in flagged
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
    ts = snap.get("timestamp") or datetime.now(UTC).isoformat()
    snap["timestamp"] = ts

    fname = f"chain_{ts.replace(':', '-')}.json"
    per_run = CHAIN_DIR / fname
    per_run.write_text(json.dumps(snap, indent=2, default=str))

    latest = LATEST_DIR / "chain.json"
    latest.write_text(json.dumps(snap, indent=2, default=str))

    _publish_events(snap, prior_state)

    state = _regime_state(snap)
    log.info("chain snapshot written: %s (regime=%s)", per_run, state)
    return {
        "path": str(per_run),
        "regime": state,
        "prior_regime": prior_state,
        "shifted": bool(prior_state and prior_state != state and state != "UNKNOWN"),
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
