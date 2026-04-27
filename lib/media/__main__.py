"""Command line entry point for offline media helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import REPO_ROOT
from .factory import (
    DEFAULT_RUN_ROOT,
    MediaFactorySafetyError,
    discover_work_orders,
    load_work_order,
    media_factory_status,
    run_media_factory,
    validate_work_order,
)
from .work_orders import generate_work_orders


def _print_json(data: dict, *, pretty: bool) -> None:
    print(json.dumps(data, indent=2 if pretty else None, sort_keys=True))


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
    _print_json(summary, pretty=args.pretty)
    return 0


def _selected_work_orders(args: argparse.Namespace) -> list[Path]:
    if args.work_orders:
        return list(args.work_orders)
    return discover_work_orders(args.work_order_root, limit=args.limit)


def _validate(args: argparse.Namespace) -> int:
    validations = []
    for work_order_path in _selected_work_orders(args):
        try:
            work_order = load_work_order(work_order_path)
            validation = validate_work_order(work_order, root=args.root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            validation = {
                "ok": False,
                "errors": [{"field": "$", "message": str(exc)}],
                "warnings": [],
            }
        validations.append({"path": str(work_order_path), **validation})

    summary = {
        "count": len(validations),
        "ok": all(item["ok"] for item in validations),
        "validations": validations,
    }
    _print_json(summary, pretty=args.pretty)
    return 0 if summary["ok"] else 1


def _compact_run(result: dict) -> dict:
    return {
        "work_order_id": result["work_order_id"],
        "status": result["status"],
        "dry_run": result["dry_run"],
        "run_dir": result["run_dir"],
        "factory_run_path": result["factory_run_path"],
        "manifest_path": result["manifest_path"],
        "readiness": result["readiness"],
    }


def _run(args: argparse.Namespace) -> int:
    runs = []
    errors = []
    for work_order_path in _selected_work_orders(args):
        try:
            result = run_media_factory(
                work_order_path,
                root=args.root,
                run_root=args.run_root,
            )
            runs.append(_compact_run(result))
        except MediaFactorySafetyError as exc:
            errors.append(
                {
                    "path": str(exc.work_order_path or work_order_path),
                    "validation": exc.validation,
                }
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"path": str(work_order_path), "error": str(exc)})

    summary = {
        "count": len(runs),
        "ok": not errors,
        "runs": runs,
        "errors": errors,
    }
    _print_json(summary, pretty=args.pretty)
    return 0 if summary["ok"] else 1


def _status(args: argparse.Namespace) -> int:
    summary = media_factory_status(
        run_root=args.run_root,
        root=args.root,
        work_order_id=args.work_order_id,
    )
    _print_json(summary, pretty=args.pretty)
    return 0


def _add_factory_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "work_orders",
        nargs="*",
        type=Path,
        help="Work-order JSON files. Defaults to --work-order-root/*.json.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used for relative paths.",
    )
    parser.add_argument(
        "--work-order-root",
        type=Path,
        default=REPO_ROOT / "data" / "media" / "work_orders",
        help="Directory to scan when no work-order paths are provided.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of discovered work orders to process.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON summary output.",
    )


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

    validate = sub.add_parser(
        "validate",
        help="Validate media work orders for dry-run factory safety.",
    )
    _add_factory_io_args(validate)
    validate.set_defaults(func=_validate)

    run = sub.add_parser(
        "run",
        help="Write local image/audio/video readiness artifacts for work orders.",
    )
    _add_factory_io_args(run)
    run.add_argument(
        "--run-root",
        type=Path,
        default=DEFAULT_RUN_ROOT,
        help="Output directory for dry-run media readiness artifacts.",
    )
    run.set_defaults(func=_run)

    status = sub.add_parser(
        "status",
        help="Summarize local dry-run media factory artifacts.",
    )
    status.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used for relative paths.",
    )
    status.add_argument(
        "--run-root",
        type=Path,
        default=DEFAULT_RUN_ROOT,
        help="Directory containing dry-run media readiness artifacts.",
    )
    status.add_argument(
        "--work-order-id",
        help="Limit status output to one work order id.",
    )
    status.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON summary output.",
    )
    status.set_defaults(func=_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
