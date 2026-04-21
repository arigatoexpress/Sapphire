"""Correlation matrix refresh — hourly via LaunchAgent.

Recomputes the cross-asset correlation matrix and writes:
    data/intelligence/latest/correlations.json   latest report
    data/intelligence/correlations_history.jsonl history appended by the engine

Usage:
    python -m services.pipeline.correlation_refresh
    python -m services.pipeline.correlation_refresh --window 60
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.home() / "Code" / "Sapphire"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.correlation import CorrelationEngine  # noqa: E402

log = logging.getLogger("correlation_refresh")

LATEST_DIR = ROOT / "data" / "intelligence" / "latest"


def run(window_days: int = 30) -> dict:
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    engine = CorrelationEngine()
    report = engine.report(window_days=window_days)

    out = {
        "timestamp": report.timestamp,
        "window_days": window_days,
        "matrix": report.matrix.matrix,
        "symbols": report.matrix.symbols,
        "decorrelation_events": [asdict(e) for e in report.decorrelation_events],
        "risk_on_matrix":  asdict(report.risk_on_matrix)  if report.risk_on_matrix  else None,
        "risk_off_matrix": asdict(report.risk_off_matrix) if report.risk_off_matrix else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    dest = LATEST_DIR / "correlations.json"
    dest.write_text(json.dumps(out, indent=2, default=str))
    log.info("correlations written: %s (%d symbols, %d events)",
             dest, len(out["symbols"]), len(out["decorrelation_events"]))
    return {"path": str(dest), "symbols": len(out["symbols"]),
            "events": len(out["decorrelation_events"])}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, default=30, help="correlation window in days")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        # Route INFO/DEBUG to stdout so the LaunchAgent's *-err.log only
        # captures real errors (tracebacks still go to stderr naturally).
        stream=sys.stdout,
    )
    try:
        out = run(window_days=args.window)
    except Exception as e:
        log.exception("correlation refresh failed: %s", e)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
