#!/usr/bin/env python3
"""
Generate a weekly strategy scorecard from live execution telemetry.

Outputs:
  - JSON artifact with ranked strategy/timeframe lanes.
  - Markdown summary suitable for reviews and Linear updates.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _strategy_tf_from_row(row: dict[str, Any]) -> tuple[str, str]:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    strategy = _norm(
        row.get("strategy")
        or metadata.get("strategy")
        or metadata.get("strategy_id")
        or metadata.get("system")
    )
    timeframe = _norm(
        row.get("timeframe")
        or metadata.get("timeframe")
        or metadata.get("tf")
        or metadata.get("interval")
    )
    return strategy or "unknown", timeframe or "unknown"


def _lane_key(strategy: str, timeframe: str) -> str:
    return f"{strategy}@{timeframe}"


def _safe_div(numer: float, denom: float) -> float:
    if denom <= 0:
        return 0.0
    return float(numer) / float(denom)


def _lane_stage_recommendation(row: dict[str, Any]) -> str:
    samples = int(row["sample_size"])
    reject_tax = float(row["reject_tax_pct"])
    hard_fail = float(row["hard_fail_pct"])
    score = float(row["score"])
    pnl = float(row["net_realized_pnl_usd"])
    if samples < 20:
        return "research"
    if reject_tax >= 70.0 or hard_fail >= 15.0:
        return "hold"
    if score >= 20.0 and pnl > 0:
        return "promote"
    if score >= 5.0:
        return "monitor"
    return "deprioritize"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly strategy scorecard artifact.")
    parser.add_argument("--project", default="sapphire-479610")
    parser.add_argument("--platform", default="lighter")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    now = datetime.now(UTC)
    since = now - timedelta(days=max(1, int(args.days)))
    platform = _norm(args.platform)
    max_rows = max(500, min(int(args.max_rows), 10000))

    client = firestore.Client(project=args.project)

    exec_rows: list[dict[str, Any]] = []
    try:
        query = (
            client.collection("execution_verifications")
            .where(filter=FieldFilter("platform", "==", platform))
            .where(filter=FieldFilter("recorded_at", ">=", since))
            .order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(max_rows)
        )
        exec_rows = [doc.to_dict() or {} for doc in query.stream()]
    except Exception:
        try:
            query = (
                client.collection("execution_verifications")
                .order_by("recorded_at", direction=firestore.Query.DESCENDING)
                .limit(max_rows * 2)
            )
            for doc in query.stream():
                row = doc.to_dict() or {}
                if _norm(row.get("platform")) != platform:
                    continue
                ts = _to_dt(row.get("recorded_at") or row.get("timestamp"))
                if ts and ts < since:
                    continue
                exec_rows.append(row)
        except Exception:
            for doc in (
                client.collection("execution_verifications")
                .limit(max_rows * 3)
                .stream()
            ):
                row = doc.to_dict() or {}
                if _norm(row.get("platform")) != platform:
                    continue
                ts = _to_dt(row.get("recorded_at") or row.get("timestamp"))
                if ts and ts < since:
                    continue
                exec_rows.append(row)

    pnl_rows: list[dict[str, Any]] = []
    try:
        query = (
            client.collection("trade_executions")
            .where(filter=FieldFilter("timestamp", ">=", since.isoformat()))
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(max_rows)
        )
        pnl_rows = [doc.to_dict() or {} for doc in query.stream()]
    except Exception:
        try:
            query = (
                client.collection("trade_executions")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(max_rows * 2)
            )
            for doc in query.stream():
                row = doc.to_dict() or {}
                ts = _to_dt(row.get("timestamp"))
                if ts and ts < since:
                    continue
                pnl_rows.append(row)
        except Exception:
            for doc in client.collection("trade_executions").limit(max_rows * 3).stream():
                row = doc.to_dict() or {}
                ts = _to_dt(row.get("timestamp"))
                if ts and ts < since:
                    continue
                pnl_rows.append(row)

    agg = defaultdict(
        lambda: {
            "strategy": "",
            "timeframe": "",
            "sample_size": 0,
            "filled_success_count": 0,
            "reject_skip_count": 0,
            "hard_failed_count": 0,
            "accepted_no_fill_count": 0,
            "net_realized_pnl_usd": 0.0,
            "trade_count": 0,
        }
    )

    for row in exec_rows:
        strategy, timeframe = _strategy_tf_from_row(row)
        key = _lane_key(strategy, timeframe)
        slot = agg[key]
        slot["strategy"] = strategy
        slot["timeframe"] = timeframe
        slot["sample_size"] += 1
        outcome = _norm(row.get("outcome"))
        if outcome == "filled_success":
            slot["filled_success_count"] += 1
        elif outcome in {"policy_noop", "policy_reject", "noop"}:
            slot["reject_skip_count"] += 1
        elif outcome == "hard_failed":
            slot["hard_failed_count"] += 1
        elif outcome == "accepted_no_fill":
            slot["accepted_no_fill_count"] += 1

    for row in pnl_rows:
        strategy, timeframe = _strategy_tf_from_row(row)
        key = _lane_key(strategy, timeframe)
        slot = agg[key]
        slot["strategy"] = strategy
        slot["timeframe"] = timeframe
        slot["net_realized_pnl_usd"] += _to_float(row.get("realized_pnl"), 0.0)
        slot["trade_count"] += 1

    ranked: list[dict[str, Any]] = []
    for lane in agg.values():
        sample = max(1, int(lane["sample_size"]))
        fill_pct = _safe_div(lane["filled_success_count"], sample) * 100.0
        reject_pct = _safe_div(lane["reject_skip_count"], sample) * 100.0
        hard_fail_pct = _safe_div(lane["hard_failed_count"], sample) * 100.0
        pnl = float(lane["net_realized_pnl_usd"])

        # Composite score: execution quality + PnL penalty/boost.
        pnl_term = max(-30.0, min(30.0, pnl * 2.0))
        score = fill_pct - (0.8 * reject_pct) - (1.5 * hard_fail_pct) + pnl_term

        row = {
            **lane,
            "filled_success_pct": round(fill_pct, 2),
            "reject_tax_pct": round(reject_pct, 2),
            "hard_fail_pct": round(hard_fail_pct, 2),
            "net_realized_pnl_usd": round(pnl, 6),
            "score": round(score, 4),
        }
        row["recommendation"] = _lane_stage_recommendation(row)
        ranked.append(row)

    ranked.sort(
        key=lambda item: (
            item["score"],
            item["net_realized_pnl_usd"],
            item["sample_size"],
        ),
        reverse=True,
    )

    totals = {
        "lanes": len(ranked),
        "sample_size": sum(int(item["sample_size"]) for item in ranked),
        "filled_success_count": sum(int(item["filled_success_count"]) for item in ranked),
        "reject_skip_count": sum(int(item["reject_skip_count"]) for item in ranked),
        "hard_failed_count": sum(int(item["hard_failed_count"]) for item in ranked),
        "net_realized_pnl_usd": round(sum(float(item["net_realized_pnl_usd"]) for item in ranked), 6),
    }
    total_safe = max(1, totals["sample_size"])
    totals["reject_tax_pct"] = round((totals["reject_skip_count"] / total_safe) * 100.0, 2)
    totals["hard_fail_pct"] = round((totals["hard_failed_count"] / total_safe) * 100.0, 2)
    totals["filled_success_pct"] = round((totals["filled_success_count"] / total_safe) * 100.0, 2)

    artifact = {
        "generated_at": now.isoformat(),
        "project": args.project,
        "platform": platform,
        "window": {
            "days": int(args.days),
            "since": since.isoformat(),
            "until": now.isoformat(),
        },
        "totals": totals,
        "ranked": ranked,
    }

    default_dir = Path("output/strategy_scorecards").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    default_stem = f"weekly_{platform}_{now.strftime('%Y%m%d')}"
    json_path = (
        Path(args.output_json).expanduser().resolve()
        if args.output_json
        else default_dir / f"{default_stem}.json"
    )
    md_path = (
        Path(args.output_md).expanduser().resolve()
        if args.output_md
        else default_dir / f"{default_stem}.md"
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(artifact, indent=2, sort_keys=True))

    md_lines = [
        f"# Weekly Strategy Scorecard ({platform})",
        "",
        f"- Generated: {now.isoformat()}",
        f"- Window: last {int(args.days)} days",
        f"- Total samples: {totals['sample_size']}",
        f"- Filled success: {totals['filled_success_pct']:.2f}%",
        f"- Reject tax: {totals['reject_tax_pct']:.2f}%",
        f"- Hard fail: {totals['hard_fail_pct']:.2f}%",
        f"- Net realized PnL: {totals['net_realized_pnl_usd']:+.4f}",
        "",
        "| Rank | Lane | Score | Samples | Fill% | Reject% | HardFail% | NetPnL | Recommendation |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(ranked[:20], start=1):
        lane = f"{row['strategy']}@{row['timeframe']}"
        md_lines.append(
            f"| {idx} | {lane} | {row['score']:.2f} | {int(row['sample_size'])} | "
            f"{row['filled_success_pct']:.2f}% | {row['reject_tax_pct']:.2f}% | "
            f"{row['hard_fail_pct']:.2f}% | {row['net_realized_pnl_usd']:+.4f} | "
            f"{row['recommendation']} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n")

    print(
        json.dumps(
            {
                "json_artifact": str(json_path),
                "markdown_report": str(md_path),
                "lanes": len(ranked),
                "top_lane": ranked[0]["strategy"] + "@" + ranked[0]["timeframe"] if ranked else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
