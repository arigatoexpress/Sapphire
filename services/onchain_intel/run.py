#!/usr/bin/env python3
"""Run the Sapphire on-chain intelligence daemon.

The daemon is read-only and fixture-first. Provider live calls are controlled
inside provider clients by per-provider ``SAPPHIRE_*_LIVE`` gates plus
credentials/RPC URLs; this wrapper never enables live mode by itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.onchain_intel.service import (  # noqa: E402
    build_status,
    collect_snapshot,
    write_snapshot,
)

DEFAULT_POLL_INTERVAL_SECONDS = 30 * 60
GENERATOR = "services.onchain_intel.run"
EVENT_TOPIC = "onchain.snapshot.updated"


def _parse_assets(value: str | None) -> list[str] | None:
    if not value:
        return None
    assets = [part.strip().upper() for part in value.split(",") if part.strip()]
    return assets or None


def _publish(snapshot: dict[str, Any], *, requested: bool) -> dict[str, Any]:
    if not requested or os.getenv("SAPPHIRE_ONCHAIN_LIVE_BUS") != "1":
        return {"requested": requested, "actual": False, "published": 0}
    try:
        from lib.core.event_bus import get_bus

        bus = get_bus(source="onchain-intel")
        bus.publish(EVENT_TOPIC, snapshot, source="onchain-intel")
    except Exception as exc:  # noqa: BLE001 - publishing must not break collection.
        return {
            "requested": requested,
            "actual": False,
            "published": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"requested": requested, "actual": True, "published": 1}


def run_once(
    *,
    assets: list[str] | None = None,
    backfill_days: int | None = None,
    write: bool = True,
    publish: bool = False,
) -> dict[str, Any]:
    snapshot = collect_snapshot(assets=assets, backfill_days=backfill_days)
    if write:
        snapshot["paths"] = write_snapshot(snapshot)
    snapshot["published"] = _publish(snapshot, requested=publish)
    snapshot["service"] = {"generator": GENERATOR, "event_topic": EVENT_TOPIC}
    return snapshot


def daemon(
    *,
    assets: list[str] | None = None,
    backfill_days: int | None = None,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    write: bool = True,
    publish: bool = False,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    iterations = 0
    last: dict[str, Any] | None = None
    while True:
        last = run_once(
            assets=assets,
            backfill_days=backfill_days,
            write=write,
            publish=publish,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        sleep(max(1, int(poll_interval_seconds)))
    return {"iterations": iterations, "last": last}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    once = sub.add_parser("run-once", help="collect one on-chain snapshot")
    once.add_argument("--assets", default="", help="comma-separated assets, default BTC,ETH,SOL")
    once.add_argument("--backfill-days", type=int, default=30)
    once.add_argument("--no-write", action="store_true", help="do not write latest/archive JSON")
    once.add_argument("--publish", action="store_true", help="publish event if bus env gate is enabled")

    daemon_p = sub.add_parser("daemon", help="run continuous snapshot loop")
    daemon_p.add_argument("--assets", default="", help="comma-separated assets, default BTC,ETH,SOL")
    daemon_p.add_argument("--backfill-days", type=int, default=30)
    daemon_p.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    daemon_p.add_argument("--max-iterations", type=int, default=None)
    daemon_p.add_argument("--no-write", action="store_true")
    daemon_p.add_argument("--publish", action="store_true")

    sub.add_parser("status", help="print provider gate status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "status":
        result = build_status()
    elif args.action == "run-once":
        result = run_once(
            assets=_parse_assets(args.assets),
            backfill_days=args.backfill_days,
            write=not args.no_write,
            publish=args.publish,
        )
    elif args.action == "daemon":
        result = daemon(
            assets=_parse_assets(args.assets),
            backfill_days=args.backfill_days,
            poll_interval_seconds=args.poll_interval_seconds,
            max_iterations=args.max_iterations,
            write=not args.no_write,
            publish=args.publish,
        )
    else:  # pragma: no cover - argparse enforces choices.
        result = {"error": f"unknown action {args.action}"}
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 1 if isinstance(result, dict) and result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
