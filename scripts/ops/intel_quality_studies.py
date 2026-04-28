#!/usr/bin/env python3
"""Run offline intelligence quality studies against local JSON/JSONL artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.intel.quality_studies import (  # noqa: E402
    analyze_counterparty_leaderboard_stability,
    analyze_regime_stability,
)


def load_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        records.extend(_load_one(path))
    return records


def _load_one(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            rows.append(value)
        return rows

    value = json.loads(text)
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise ValueError(f"{path}: expected list of JSON objects")
        return list(value)
    if isinstance(value, dict):
        for key in ("snapshots", "records", "items"):
            nested = value.get(key)
            if isinstance(nested, list) and all(isinstance(item, dict) for item in nested):
                return list(nested)
        return [value]
    raise ValueError(f"{path}: expected JSON object or list")


def write_or_print(report: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    regime = sub.add_parser("regime-stability", help="Study cross-asset regime label stability")
    regime.add_argument("--input", required=True, type=Path, action="append")
    regime.add_argument("--output", type=Path)

    counterparty = sub.add_parser(
        "counterparty-stability",
        help="Study public Hyperliquid counterparty leaderboard stability",
    )
    counterparty.add_argument("--input", required=True, type=Path, action="append")
    counterparty.add_argument("--output", type=Path)
    counterparty.add_argument("--top-n", type=int, default=20)
    counterparty.add_argument("--min-appearance-rate", type=float, default=0.67)
    counterparty.add_argument("--max-rank-stdev", type=float, default=3.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        records = load_records(args.input)
        if args.command == "regime-stability":
            report = analyze_regime_stability(records).to_dict()
        else:
            report = analyze_counterparty_leaderboard_stability(
                records,
                top_n=args.top_n,
                min_appearance_rate=args.min_appearance_rate,
                max_rank_stdev=args.max_rank_stdev,
            ).to_dict()
        write_or_print(report, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"intel quality study error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
