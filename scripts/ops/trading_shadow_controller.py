#!/usr/bin/env python3
"""Generate a paper-shadow trading controller report.

Default mode may fetch read-only public market data. It never reads Robinhood
secrets and never submits orders. Use ``--offline`` for a deterministic local
report, or ``--output`` to persist the latest report for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.trading.shadow_controller import (  # noqa: E402
    ShadowRiskPolicy,
    build_shadow_trading_report,
    write_shadow_report,
)

DEFAULT_OUTPUT = ROOT / "data" / "trading" / "shadow-controller-latest.json"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = ShadowRiskPolicy(
            requested_candidate_notional_usd=args.notional_usd,
            min_confidence=args.min_confidence,
            max_open_candidates=args.max_candidates,
            max_spread_bps=args.max_spread_bps,
        )
        report = build_shadow_trading_report(fetch_live=not args.offline, policy=policy)
    except Exception as exc:
        print(json.dumps({"verdict": "ERROR", "error": f"{type(exc).__name__}: {exc}"}))
        return 20

    if args.output:
        write_shadow_report(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip public market-data fetches and use the deterministic fallback universe.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        nargs="?",
        const=DEFAULT_OUTPUT,
        help="Write the report to a path; with no value, writes data/trading/shadow-controller-latest.json.",
    )
    parser.add_argument(
        "--notional-usd",
        type=float,
        default=5.0,
        help="Requested paper/manual candidate notional before pilot caps.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.72,
        help="Minimum confidence required to emit a manual-review candidate.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=3,
        help="Maximum number of candidate buys in the report.",
    )
    parser.add_argument(
        "--max-spread-bps",
        type=float,
        default=150.0,
        help="Manual-order dry-run spread threshold to carry into candidate commands.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
