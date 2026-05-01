#!/usr/bin/env python3
"""Cross-asset correlation/regime daemon.

Cache-first by default. Live source pulls require ``--live`` and
``SAPPHIRE_CROSS_ASSET_LIVE=1``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import stamp, write_envelope_sidecar  # noqa: E402
from lib.cross_asset import (  # noqa: E402
    analyze_lead_lag,
    build_correlation_matrix,
    detect_regime,
    fetch_universe,
    to_close_series,
)

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "cross_asset"
GENERATOR = "services.cross_asset.run"
VERSION = "0.1.0"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def build_snapshot(
    *,
    assets: list[str] | None = None,
    live: bool = False,
    now: datetime | None = None,
    limit: int = 24 * 120,
) -> dict[str, Any]:
    """Build one cross-asset snapshot without publishing or persisting."""
    issued_at = now or _now()
    rows = fetch_universe(assets, live=live, limit=limit, now=issued_at)
    close_series = to_close_series(rows)
    matrix = build_correlation_matrix(close_series, now=issued_at)
    try:
        regime_matrix = matrix.matrix_for(window="7d", method="pearson")
    except KeyError:
        first_window = next(iter(matrix.windows))
        regime_matrix = matrix.matrix_for(window=first_window, method="pearson")
    regime = detect_regime(regime_matrix, timestamp=matrix.generated_at)
    lead_lag = analyze_lead_lag(close_series, max_lag=6, min_observations=30, limit=12)
    payload = {
        "ok": True,
        "version": VERSION,
        "mode": "live" if live else "cache_or_dry_run",
        "generated_at": issued_at.isoformat(),
        "assets": sorted(close_series),
        "matrix": matrix.to_dict(),
        "regime": regime.to_dict(),
        "breakdowns": [event.to_dict() for event in matrix.breakdown_events],
        "lead_lag": [item.to_dict() for item in lead_lag],
        "source_summary": {
            asset: {
                "points": len(points),
                "source": points[-1].source if points else "missing",
                "latest_timestamp": points[-1].timestamp if points else None,
            }
            for asset, points in rows.items()
        },
    }
    return stamp(
        payload,
        generator=GENERATOR,
        source_paths=(
            "lib/cross_asset/correlation_matrix.py",
            "lib/cross_asset/regime_detector.py",
            "lib/cross_asset/sources.py",
        ),
        metadata={"version": VERSION, "live": live},
    )


def persist_snapshot(
    snapshot: dict[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    now: datetime | None = None,
) -> dict[str, Path]:
    """Write matrix/regime/breakdown artifacts for one snapshot."""
    issued_at = now or _now()
    target = output_root / issued_at.strftime("%Y-%m-%d")
    target.mkdir(parents=True, exist_ok=True)

    matrix_path = target / "matrix.json"
    regime_path = target / "regimes.jsonl"
    breakdown_path = target / "breakdowns.jsonl"
    lead_lag_path = target / "lead_lag.json"

    matrix_payload = {
        "generated_at": snapshot["generated_at"],
        "matrix": snapshot["matrix"],
        "source_summary": snapshot["source_summary"],
        "provenance": snapshot["provenance"],
    }
    matrix_path.write_text(
        json.dumps(matrix_payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    write_envelope_sidecar(
        matrix_path,
        generator=GENERATOR,
        source_paths=("services/cross_asset/run.py",),
        metadata={"artifact": "matrix"},
    )

    regime_row = stamp(
        snapshot["regime"],
        generator=GENERATOR,
        source_paths=("lib/cross_asset/regime_detector.py",),
        metadata={"artifact": "regime"},
    )
    with regime_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(regime_row, sort_keys=True, default=_json_default) + "\n")

    with breakdown_path.open("a", encoding="utf-8") as fh:
        for event in snapshot.get("breakdowns", []):
            row = stamp(
                event,
                generator=GENERATOR,
                source_paths=("lib/cross_asset/correlation_matrix.py",),
                metadata={"artifact": "breakdown"},
            )
            fh.write(json.dumps(row, sort_keys=True, default=_json_default) + "\n")

    lead_lag_path.write_text(
        json.dumps(
            {
                "generated_at": snapshot["generated_at"],
                "lead_lag": snapshot.get("lead_lag", []),
                "provenance": snapshot["provenance"],
            },
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "matrix": matrix_path,
        "matrix_sidecar": matrix_path.with_name("matrix.json.envelope.json"),
        "regimes": regime_path,
        "breakdowns": breakdown_path,
        "lead_lag": lead_lag_path,
    }


def publish_snapshot(snapshot: dict[str, Any]) -> dict[str, int]:
    """Publish detected shifts/breakdowns to the local event bus."""
    from lib.core.event_bus import get_bus

    bus = get_bus(source="cross-asset")
    published = {"regime.shift.detected": 0, "correlation.breakdown": 0}
    regime = snapshot.get("regime") or {}
    if regime.get("label") and regime.get("label") != "regime_uncertain":
        bus.publish("regime.shift.detected", regime, source="cross-asset")
        published["regime.shift.detected"] += 1
    for event in snapshot.get("breakdowns", []):
        bus.publish("correlation.breakdown", event, source="cross-asset")
        published["correlation.breakdown"] += 1
    return published


def run_once(
    *,
    assets: list[str] | None = None,
    live: bool = False,
    publish: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    snapshot = build_snapshot(assets=assets, live=live, now=now)
    artifacts = persist_snapshot(snapshot, output_root=output_root, now=now)
    published = publish_snapshot(snapshot) if publish else {}
    return {
        "ok": True,
        "snapshot": snapshot,
        "artifacts": {key: str(value) for key, value in artifacts.items()},
        "published": published,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run once and exit")
    parser.add_argument(
        "--live", action="store_true", help="allow live adapters when env gate is set"
    )
    parser.add_argument("--publish", action="store_true", help="publish local event-bus events")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--assets", default="", help="comma-separated asset list")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)

    requested_assets = [item.strip().upper() for item in args.assets.split(",") if item.strip()]
    live = bool(args.live) and os.environ.get("SAPPHIRE_CROSS_ASSET_LIVE", "") == "1"

    while True:
        result = run_once(
            assets=requested_assets or None,
            live=live,
            publish=bool(args.publish),
            output_root=args.output_root,
        )
        summary = {
            "ok": result["ok"],
            "artifacts": result["artifacts"],
            "published": result["published"],
            "mode": "live" if live else "cache_or_dry_run",
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.once:
            return 0
        time.sleep(max(60, int(args.interval_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
