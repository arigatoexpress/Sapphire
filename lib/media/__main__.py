"""Command line entry point for offline media helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import REPO_ROOT
from .work_orders import generate_work_orders


def _work_orders(args: argparse.Namespace) -> int:
    results = generate_work_orders(
        content_root=args.content_root,
        root=args.root,
        output_root=args.output_root,
        manifest_root=args.manifest_root,
        kinds=args.kind,
        latest=args.latest,
        limit=args.limit,
    )
    summary = {
        "count": len(results),
        "work_orders": [
            {
                "work_order_id": item["work_order"]["work_order_id"],
                "path": str(item["path"]),
                "manifest_path": item["manifest"]["manifest_path"],
                "report_kind": item["work_order"]["report"]["kind"],
                "title": item["work_order"]["report"]["title"],
            }
            for item in results
        ],
    }
    print(json.dumps(summary, indent=2 if args.pretty else None, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m lib.media")
    sub = parser.add_subparsers(dest="command", required=True)

    work_orders = sub.add_parser(
        "work-orders",
        help="Create offline media work orders from content draft manifests.",
    )
    work_orders.add_argument(
        "--kind",
        action="append",
        help="Content kind to include. May be repeated.",
    )
    work_orders.add_argument(
        "--latest",
        action="store_true",
        help="Use only the newest draft per selected kind.",
    )
    work_orders.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of draft manifests to process.",
    )
    work_orders.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used for relative paths.",
    )
    work_orders.add_argument(
        "--content-root",
        type=Path,
        default=REPO_ROOT / "data" / "content",
        help="Content artifact root.",
    )
    work_orders.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "data" / "media" / "work_orders",
        help="Output directory for work-order JSON files.",
    )
    work_orders.add_argument(
        "--manifest-root",
        type=Path,
        default=REPO_ROOT / "data" / "media" / "manifests",
        help="Output directory for provenance manifests.",
    )
    work_orders.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON summary output.",
    )
    work_orders.set_defaults(func=_work_orders)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
