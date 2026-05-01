"""Houston home lead pipeline — one-command runner.

Sequence::

    1. Ingest from 311 / permits / Regional Intel
    2. Score every unscored lead via local AI (heuristic fallback)
    3. Geocode every un-mapped lead via Nominatim
    4. Persist to data/leads/houston_leads.jsonl
    5. Emit ``lead.pipeline_run`` event + summary line

Designed to be safe to re-run: every step is idempotent, deduplicates by id,
and tolerates network outages without aborting.

CLI::

    python3 -m lib.intel.pipeline --run
    python3 -m lib.intel.pipeline --run --skip-geocode
    python3 -m lib.intel.pipeline --stats
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from typing import Any

from lib.intel.geocoder import geocode_unmapped
from lib.intel.houston_leads import LEADS_FILE, ingest, load_leads
from lib.intel.lead_scorer import score_unscored

log = logging.getLogger(__name__)

HOT_LEAD_THRESHOLD = 80


def run(
    *,
    region: str = "houston_tx",
    skip_ingest: bool = False,
    skip_score: bool = False,
    skip_geocode: bool = False,
    score_limit: int | None = None,
    geocode_limit: int | None = None,
) -> dict[str, Any]:
    """Execute the full pipeline. Returns a dict suitable for logging."""
    started_at = datetime.now(UTC)

    ingested: dict[str, int] = {}
    if not skip_ingest:
        ingested = ingest(region=region)

    scored = 0 if skip_score else score_unscored(limit=score_limit)
    geocoded = 0 if skip_geocode else geocode_unmapped(limit=geocode_limit)

    leads = load_leads()
    hot = [
        l
        for l in leads
        if isinstance(l.get("score"), (int, float)) and l["score"] >= HOT_LEAD_THRESHOLD
    ]

    finished_at = datetime.now(UTC)
    summary = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "elapsed_secs": round((finished_at - started_at).total_seconds(), 2),
        "ingested": ingested,
        "ingested_total": sum(ingested.values()),
        "scored": scored,
        "geocoded": geocoded,
        "total_leads": len(leads),
        "hot_leads": len(hot),
        "store": str(LEADS_FILE),
    }

    try:
        from lib.core.event_bus import get_bus

        get_bus().publish("lead.pipeline_run", summary, source="lead_pipeline")
    except Exception:
        pass

    log.info(
        "pipeline: ingested=%s scored=%d geocoded=%d total=%d hot=%d in %.2fs",
        summary["ingested"],
        scored,
        geocoded,
        summary["total_leads"],
        summary["hot_leads"],
        summary["elapsed_secs"],
    )
    return summary


def stats() -> dict[str, Any]:
    """Quick aggregate over the current JSONL store — used by /api/leads/stats."""
    leads = load_leads()
    by_source: dict[str, int] = {}
    by_urgency: dict[str, int] = {}
    score_sum = 0.0
    score_n = 0
    hot = 0
    geocoded = 0
    for lead in leads:
        by_source[lead.get("source", "unknown")] = (
            by_source.get(lead.get("source", "unknown"), 0) + 1
        )
        if lead.get("urgency"):
            by_urgency[lead["urgency"]] = by_urgency.get(lead["urgency"], 0) + 1
        if isinstance(lead.get("score"), (int, float)):
            score_sum += float(lead["score"])
            score_n += 1
            if lead["score"] >= HOT_LEAD_THRESHOLD:
                hot += 1
        if lead.get("lat") is not None and lead.get("lng") is not None:
            geocoded += 1

    return {
        "total": len(leads),
        "scored": score_n,
        "geocoded": geocoded,
        "hot_leads": hot,
        "avg_score": round(score_sum / score_n, 1) if score_n else None,
        "by_source": by_source,
        "by_urgency": by_urgency,
        "hot_threshold": HOT_LEAD_THRESHOLD,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--run", action="store_true", help="Run the full pipeline")
    p.add_argument("--stats", action="store_true", help="Print store stats")
    p.add_argument("--region", default="houston_tx")
    p.add_argument("--skip-ingest", action="store_true")
    p.add_argument("--skip-score", action="store_true")
    p.add_argument("--skip-geocode", action="store_true")
    p.add_argument("--score-limit", type=int, default=None)
    p.add_argument("--geocode-limit", type=int, default=None)
    args = p.parse_args()

    if args.run:
        out = run(
            region=args.region,
            skip_ingest=args.skip_ingest,
            skip_score=args.skip_score,
            skip_geocode=args.skip_geocode,
            score_limit=args.score_limit,
            geocode_limit=args.geocode_limit,
        )
    elif args.stats:
        out = stats()
    else:
        p.error("pass --run or --stats")
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
