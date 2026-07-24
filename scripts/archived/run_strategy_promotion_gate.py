#!/usr/bin/env python3
"""
Generate a promotion-gate artifact for one strategy/timeframe lane.

Pipeline stages:
  backtest -> paper -> capped_live -> scale

The artifact is deterministic JSON so automation can gate promotions without
manual interpretation of logs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.api_core.exceptions import PermissionDenied
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
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


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_strategy_tf(row: dict[str, Any]) -> tuple[str, str]:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    strategy = _normalized(
        row.get("strategy")
        or metadata.get("strategy")
        or metadata.get("strategy_id")
        or metadata.get("system")
    )
    timeframe = _normalized(
        row.get("timeframe")
        or metadata.get("timeframe")
        or metadata.get("tf")
        or metadata.get("interval")
    )
    return strategy, timeframe


@dataclass
class Thresholds:
    backtest_min_trades: int
    backtest_min_expectancy_pct: float
    backtest_max_drawdown_pct: float
    paper_min_samples: int
    paper_max_reject_tax_pct: float
    paper_max_hard_fail_pct: float
    paper_min_fill_success_pct: float
    capped_live_min_samples: int
    capped_live_min_net_pnl_usd: float
    capped_live_max_drawdown_pct: float
    scale_min_samples: int
    scale_min_net_pnl_usd: float
    scale_max_reject_tax_pct: float
    scale_max_hard_fail_pct: float


def _query_execution_metrics(
    client: firestore.Client,
    *,
    platform: str,
    strategy: str,
    timeframe: str,
    since: datetime,
    limit: int = 3000,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    try:
        query = (
            client.collection("execution_verifications")
            .where(filter=FieldFilter("platform", "==", platform))
            .where(filter=FieldFilter("strategy", "==", strategy))
            .where(filter=FieldFilter("timeframe", "==", timeframe))
            .where(filter=FieldFilter("recorded_at", ">=", since))
            .order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        rows = [doc.to_dict() or {} for doc in query.stream()]
    except Exception:
        try:
            query = (
                client.collection("execution_verifications")
                .order_by("recorded_at", direction=firestore.Query.DESCENDING)
                .limit(max(limit * 2, 4000))
            )
            for doc in query.stream():
                row = doc.to_dict() or {}
                if _normalized(row.get("platform")) != platform:
                    continue
                ts = _to_dt(row.get("recorded_at") or row.get("timestamp"))
                if ts and ts < since:
                    continue
                row_strategy = _normalized(row.get("strategy"))
                row_timeframe = _normalized(row.get("timeframe"))
                if row_strategy != strategy or row_timeframe != timeframe:
                    continue
                rows.append(row)
        except Exception:
            for doc in client.collection("execution_verifications").limit(max(limit * 3, 6000)).stream():
                row = doc.to_dict() or {}
                if _normalized(row.get("platform")) != platform:
                    continue
                ts = _to_dt(row.get("recorded_at") or row.get("timestamp"))
                if ts and ts < since:
                    continue
                row_strategy = _normalized(row.get("strategy"))
                row_timeframe = _normalized(row.get("timeframe"))
                if row_strategy != strategy or row_timeframe != timeframe:
                    continue
                rows.append(row)

    total = len(rows)
    filled_success = sum(1 for row in rows if _normalized(row.get("outcome")) == "filled_success")
    reject_skip = sum(
        1
        for row in rows
        if _normalized(row.get("outcome")) in {"policy_noop", "policy_reject", "noop"}
    )
    hard_failed = sum(1 for row in rows if _normalized(row.get("outcome")) == "hard_failed")
    accepted_no_fill = sum(1 for row in rows if _normalized(row.get("outcome")) == "accepted_no_fill")
    total_safe = max(1, total)
    return {
        "sample_size": total,
        "filled_success_count": filled_success,
        "reject_skip_count": reject_skip,
        "hard_failed_count": hard_failed,
        "accepted_no_fill_count": accepted_no_fill,
        "filled_success_pct": round((filled_success / total_safe) * 100.0, 2),
        "reject_tax_pct": round((reject_skip / total_safe) * 100.0, 2),
        "hard_fail_pct": round((hard_failed / total_safe) * 100.0, 2),
    }


def _query_realized_pnl(
    client: firestore.Client,
    *,
    strategy: str,
    timeframe: str,
    since: datetime,
    limit: int = 3000,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    try:
        query = (
            client.collection("trade_executions")
            .where(filter=FieldFilter("timestamp", ">=", since.isoformat()))
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        rows = [doc.to_dict() or {} for doc in query.stream()]
    except Exception:
        query = (
            client.collection("trade_executions")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(max(limit * 2, 5000))
        )
        rows = [doc.to_dict() or {} for doc in query.stream()]

    matched = []
    for row in rows:
        ts = _to_dt(row.get("timestamp"))
        if ts and ts < since:
            continue
        row_strategy, row_tf = _extract_strategy_tf(row)
        if row_strategy != strategy or row_tf != timeframe:
            continue
        matched.append(row)

    pnl = sum(_to_float(row.get("realized_pnl"), 0.0) for row in matched)
    return {
        "trade_count": len(matched),
        "net_realized_pnl_usd": round(float(pnl), 6),
    }


def _query_max_drawdown_pct(
    client: firestore.Client,
    *,
    platform: str,
    since: datetime,
    limit: int = 2500,
) -> float:
    try:
        query = (
            client.collection("equity_snapshots")
            .where(filter=FieldFilter("platform", "==", platform))
            .where(filter=FieldFilter("recorded_at", ">=", since))
            .order_by("recorded_at", direction=firestore.Query.ASCENDING)
            .limit(limit)
        )
        snapshots = [doc.to_dict() or {} for doc in query.stream()]
    except Exception:
        try:
            query = (
                client.collection("equity_snapshots")
                .order_by("recorded_at", direction=firestore.Query.DESCENDING)
                .limit(max(limit * 2, 3500))
            )
            snapshots = [doc.to_dict() or {} for doc in query.stream()]
            snapshots = [row for row in snapshots if _normalized(row.get("platform")) == platform]
            snapshots = list(reversed(snapshots))
        except Exception:
            snapshots = [
                doc.to_dict() or {}
                for doc in client.collection("equity_snapshots").limit(max(limit * 3, 4500)).stream()
            ]
            snapshots = [row for row in snapshots if _normalized(row.get("platform")) == platform]

    peak = 0.0
    worst_dd = 0.0
    for row in snapshots:
        ts = _to_dt(row.get("recorded_at") or row.get("timestamp"))
        if ts and ts < since:
            continue
        equity = _to_float(row.get("equity_estimate"), 0.0)
        if equity <= 0:
            continue
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = ((equity - peak) / peak) * 100.0
            if dd < worst_dd:
                worst_dd = dd
    return round(float(worst_dd), 6)


def _load_backtest_metrics(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"backtest metrics file not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    metrics = payload.get("metrics", payload) if isinstance(payload, dict) else {}
    return metrics if isinstance(metrics, dict) else {}


def _gate(pass_ok: bool, reasons: list[str]) -> dict[str, Any]:
    return {"pass": bool(pass_ok), "reasons": reasons}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate strategy promotion-gate artifact.")
    parser.add_argument("--project", default="sapphire-479610")
    parser.add_argument("--platform", default="lighter")
    parser.add_argument("--strategy", required=True, help="normalized strategy id")
    parser.add_argument("--timeframe", required=True, help="normalized timeframe token (e.g. 5m)")
    parser.add_argument("--lookback-days-paper", type=int, default=14)
    parser.add_argument("--lookback-days-live", type=int, default=14)
    parser.add_argument("--backtest-metrics-json", default="", help="optional backtest metrics JSON path")
    parser.add_argument("--output", default="", help="artifact output path")

    parser.add_argument("--backtest-min-trades", type=int, default=150)
    parser.add_argument("--backtest-min-expectancy-pct", type=float, default=0.10)
    parser.add_argument("--backtest-max-drawdown-pct", type=float, default=15.0)
    parser.add_argument("--paper-min-samples", type=int, default=30)
    parser.add_argument("--paper-max-reject-tax-pct", type=float, default=65.0)
    parser.add_argument("--paper-max-hard-fail-pct", type=float, default=10.0)
    parser.add_argument("--paper-min-fill-success-pct", type=float, default=20.0)
    parser.add_argument("--capped-live-min-samples", type=int, default=40)
    parser.add_argument("--capped-live-min-net-pnl-usd", type=float, default=0.0)
    parser.add_argument("--capped-live-max-drawdown-pct", type=float, default=8.0)
    parser.add_argument("--scale-min-samples", type=int, default=80)
    parser.add_argument("--scale-min-net-pnl-usd", type=float, default=5.0)
    parser.add_argument("--scale-max-reject-tax-pct", type=float, default=55.0)
    parser.add_argument("--scale-max-hard-fail-pct", type=float, default=5.0)
    args = parser.parse_args()

    strategy = _normalized(args.strategy)
    timeframe = _normalized(args.timeframe)
    platform = _normalized(args.platform)
    now = datetime.now(UTC)
    paper_since = now - timedelta(days=max(1, int(args.lookback_days_paper)))
    live_since = now - timedelta(days=max(1, int(args.lookback_days_live)))
    thresholds = Thresholds(
        backtest_min_trades=int(args.backtest_min_trades),
        backtest_min_expectancy_pct=float(args.backtest_min_expectancy_pct),
        backtest_max_drawdown_pct=float(args.backtest_max_drawdown_pct),
        paper_min_samples=int(args.paper_min_samples),
        paper_max_reject_tax_pct=float(args.paper_max_reject_tax_pct),
        paper_max_hard_fail_pct=float(args.paper_max_hard_fail_pct),
        paper_min_fill_success_pct=float(args.paper_min_fill_success_pct),
        capped_live_min_samples=int(args.capped_live_min_samples),
        capped_live_min_net_pnl_usd=float(args.capped_live_min_net_pnl_usd),
        capped_live_max_drawdown_pct=float(args.capped_live_max_drawdown_pct),
        scale_min_samples=int(args.scale_min_samples),
        scale_min_net_pnl_usd=float(args.scale_min_net_pnl_usd),
        scale_max_reject_tax_pct=float(args.scale_max_reject_tax_pct),
        scale_max_hard_fail_pct=float(args.scale_max_hard_fail_pct),
    )

    client = firestore.Client(project=args.project)
    try:
        backtest = _load_backtest_metrics(args.backtest_metrics_json)
        paper_exec = _query_execution_metrics(
            client,
            platform=platform,
            strategy=strategy,
            timeframe=timeframe,
            since=paper_since,
        )
        live_exec = _query_execution_metrics(
            client,
            platform=platform,
            strategy=strategy,
            timeframe=timeframe,
            since=live_since,
        )
        live_pnl = _query_realized_pnl(
            client,
            strategy=strategy,
            timeframe=timeframe,
            since=live_since,
        )
        equity_drawdown_pct = _query_max_drawdown_pct(
            client,
            platform=platform,
            since=live_since,
        )
    except PermissionDenied as exc:
        print(f"ERROR: Firestore permission denied: {exc}")
        return 2

    backtest_trades = int(_to_float(backtest.get("trades", backtest.get("trade_count", 0)), 0))
    backtest_expectancy_pct = _to_float(
        backtest.get("expectancy_pct", backtest.get("net_expectancy_pct", backtest.get("expectancy", 0.0))),
        0.0,
    )
    backtest_max_dd = abs(
        _to_float(backtest.get("max_drawdown_pct", backtest.get("drawdown_pct", 999.0)), 999.0)
    )

    bt_reasons: list[str] = []
    if backtest_trades < thresholds.backtest_min_trades:
        bt_reasons.append(f"backtest_trades {backtest_trades} < {thresholds.backtest_min_trades}")
    if backtest_expectancy_pct < thresholds.backtest_min_expectancy_pct:
        bt_reasons.append(
            f"backtest_expectancy {backtest_expectancy_pct:.3f}% < {thresholds.backtest_min_expectancy_pct:.3f}%"
        )
    if backtest_max_dd > thresholds.backtest_max_drawdown_pct:
        bt_reasons.append(
            f"backtest_drawdown {backtest_max_dd:.3f}% > {thresholds.backtest_max_drawdown_pct:.3f}%"
        )

    paper_reasons: list[str] = []
    if int(paper_exec["sample_size"]) < thresholds.paper_min_samples:
        paper_reasons.append(f"paper_samples {paper_exec['sample_size']} < {thresholds.paper_min_samples}")
    if float(paper_exec["reject_tax_pct"]) > thresholds.paper_max_reject_tax_pct:
        paper_reasons.append(
            f"paper_reject_tax {paper_exec['reject_tax_pct']:.2f}% > {thresholds.paper_max_reject_tax_pct:.2f}%"
        )
    if float(paper_exec["hard_fail_pct"]) > thresholds.paper_max_hard_fail_pct:
        paper_reasons.append(
            f"paper_hard_fail {paper_exec['hard_fail_pct']:.2f}% > {thresholds.paper_max_hard_fail_pct:.2f}%"
        )
    if float(paper_exec["filled_success_pct"]) < thresholds.paper_min_fill_success_pct:
        paper_reasons.append(
            f"paper_fill_success {paper_exec['filled_success_pct']:.2f}% < {thresholds.paper_min_fill_success_pct:.2f}%"
        )

    capped_reasons: list[str] = []
    if int(live_exec["sample_size"]) < thresholds.capped_live_min_samples:
        capped_reasons.append(f"live_samples {live_exec['sample_size']} < {thresholds.capped_live_min_samples}")
    if float(live_pnl["net_realized_pnl_usd"]) < thresholds.capped_live_min_net_pnl_usd:
        capped_reasons.append(
            f"live_net_pnl {live_pnl['net_realized_pnl_usd']:.4f} < {thresholds.capped_live_min_net_pnl_usd:.4f}"
        )
    if abs(equity_drawdown_pct) > thresholds.capped_live_max_drawdown_pct:
        capped_reasons.append(
            f"equity_drawdown {abs(equity_drawdown_pct):.3f}% > {thresholds.capped_live_max_drawdown_pct:.3f}%"
        )

    scale_reasons: list[str] = []
    if int(live_exec["sample_size"]) < thresholds.scale_min_samples:
        scale_reasons.append(f"scale_samples {live_exec['sample_size']} < {thresholds.scale_min_samples}")
    if float(live_pnl["net_realized_pnl_usd"]) < thresholds.scale_min_net_pnl_usd:
        scale_reasons.append(
            f"scale_net_pnl {live_pnl['net_realized_pnl_usd']:.4f} < {thresholds.scale_min_net_pnl_usd:.4f}"
        )
    if float(live_exec["reject_tax_pct"]) > thresholds.scale_max_reject_tax_pct:
        scale_reasons.append(
            f"scale_reject_tax {live_exec['reject_tax_pct']:.2f}% > {thresholds.scale_max_reject_tax_pct:.2f}%"
        )
    if float(live_exec["hard_fail_pct"]) > thresholds.scale_max_hard_fail_pct:
        scale_reasons.append(
            f"scale_hard_fail {live_exec['hard_fail_pct']:.2f}% > {thresholds.scale_max_hard_fail_pct:.2f}%"
        )

    gate_backtest = _gate(pass_ok=(len(bt_reasons) == 0), reasons=bt_reasons)
    gate_paper = _gate(pass_ok=(len(paper_reasons) == 0), reasons=paper_reasons)
    gate_capped = _gate(pass_ok=(len(capped_reasons) == 0), reasons=capped_reasons)
    gate_scale = _gate(pass_ok=(len(scale_reasons) == 0), reasons=scale_reasons)

    if not gate_backtest["pass"]:
        recommended_stage = "backtest"
        summary = "Backtest gate failed; do not promote."
    elif not gate_paper["pass"]:
        recommended_stage = "paper"
        summary = "Paper gate not satisfied; continue paper-only validation."
    elif not gate_capped["pass"]:
        recommended_stage = "capped_live"
        summary = "Capped-live gate not satisfied; keep capped notional."
    elif not gate_scale["pass"]:
        recommended_stage = "capped_live"
        summary = "Scale gate failed; remain capped-live while improving quality."
    else:
        recommended_stage = "scale_ready"
        summary = "All gates passed; eligible for controlled scale-up."

    artifact = {
        "generated_at": now.isoformat(),
        "project": args.project,
        "platform": platform,
        "strategy": strategy,
        "timeframe": timeframe,
        "windows": {
            "paper_since": paper_since.isoformat(),
            "live_since": live_since.isoformat(),
        },
        "thresholds": thresholds.__dict__,
        "metrics": {
            "backtest": {
                "trades": backtest_trades,
                "expectancy_pct": round(backtest_expectancy_pct, 6),
                "max_drawdown_pct": round(backtest_max_dd, 6),
                "source": str(args.backtest_metrics_json or "none"),
            },
            "paper_execution": paper_exec,
            "live_execution": live_exec,
            "live_realized": live_pnl,
            "equity_drawdown_pct": round(equity_drawdown_pct, 6),
        },
        "gates": {
            "backtest_to_paper": gate_backtest,
            "paper_to_capped_live": gate_paper,
            "capped_live_safety": gate_capped,
            "capped_live_to_scale": gate_scale,
        },
        "recommended_stage": recommended_stage,
        "decision_summary": summary,
    }

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        out_dir = Path("output/promotion_gates").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{strategy}_{timeframe}_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True))

    print(json.dumps({"recommended_stage": recommended_stage, "summary": summary, "artifact": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
