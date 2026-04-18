"""CLI entrypoint for the LaunchAgent.

Usage:
    python3 -m lib.content                 # run today's scheduled slots
    python3 -m lib.content --kind weekly_crypto_brief
    python3 -m lib.content --all           # generate every report kind
    python3 -m lib.content --list-drafts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or anywhere: add repo to sys.path
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.content import publisher, report_generator, scheduler  # noqa: E402

GENERATORS = {
    "weekly_crypto_brief": report_generator.generate_weekly_crypto_brief,
    "ai_intel": report_generator.generate_ai_intel_report,
    "security_digest": report_generator.generate_security_digest,
    "market_pulse": report_generator.generate_market_pulse_tweet,
}


def run_kind(kind: str) -> dict:
    gen = GENERATORS.get(kind)
    if gen is None:
        raise SystemExit(f"unknown report kind: {kind}")
    report = gen()
    return publisher.publish(report)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lib.content")
    ap.add_argument("--kind", help="Generate a specific report kind")
    ap.add_argument("--all", action="store_true", help="Run every report kind")
    ap.add_argument("--list-drafts", action="store_true")
    args = ap.parse_args(argv)

    if args.list_drafts:
        print(json.dumps(publisher.list_drafts(), indent=2, default=str))
        return 0

    if args.kind:
        out = run_kind(args.kind)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.all:
        results = {k: run_kind(k) for k in GENERATORS}
        print(json.dumps(results, indent=2, default=str))
        return 0

    # Default: run today's scheduled slots
    results = []
    for slot in scheduler.today_plan():
        results.append(run_kind(slot.report_kind))
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
