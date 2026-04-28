"""CLI entrypoint for the on-chain intelligence service."""

from __future__ import annotations

import argparse
import json
from typing import Any

from services.onchain_intel.service import build_status, collect_snapshot, write_snapshot


def _parse_assets(value: str | None) -> list[str] | None:
    if not value:
        return None
    assets = [part.strip().upper() for part in value.split(",") if part.strip()]
    return assets or None


def run_once(
    *,
    assets: list[str] | None = None,
    backfill_days: int | None = None,
    write: bool = True,
) -> dict[str, Any]:
    snapshot = collect_snapshot(assets=assets, backfill_days=backfill_days)
    if write:
        snapshot["paths"] = write_snapshot(snapshot)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="print provider gate status only")
    parser.add_argument("--assets", help="comma-separated assets, default BTC,ETH,SOL")
    parser.add_argument("--backfill-days", type=int, default=30)
    parser.add_argument("--no-write", action="store_true", help="do not write latest/archive JSON")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(build_status(), indent=2, sort_keys=True))
        return 0

    snapshot = run_once(
        assets=_parse_assets(args.assets),
        backfill_days=args.backfill_days,
        write=not args.no_write,
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
