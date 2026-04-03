#!/usr/bin/env python3
"""
Lighter reliability gate.

Reads Firestore runtime telemetry and enforces objective health thresholds:
  - data freshness (balance + position sync ages/stale flags)
  - risk posture (drawdown / position notional / open position count)
  - execution quality (lookback success rate, real fills)
  - exchange-jurisdiction signal quality (warning or hard-fail mode)
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


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


def _snapshot_rank(snapshot: dict[str, Any]) -> tuple[float, float, float]:
    """
    Lower rank is better.
    Priority:
      1) fewer stale flags
      2) lower max sync age
      3) newer recorded_at / timestamp
    """
    balance_stale = _to_bool(snapshot.get("balance_sync_stale"), default=True)
    position_stale = _to_bool(snapshot.get("position_check_stale"), default=True)
    stale_score = float(int(balance_stale) + int(position_stale))

    balance_age_raw = snapshot.get("balance_sync_age_sec")
    position_age_raw = snapshot.get("position_check_age_sec")
    balance_age = _to_float(balance_age_raw, default=1e9) if balance_age_raw is not None else 1e9
    position_age = _to_float(position_age_raw, default=1e9) if position_age_raw is not None else 1e9
    age_score = max(balance_age, position_age)

    ts = _to_dt(snapshot.get("recorded_at")) or _to_dt(snapshot.get("timestamp"))
    recency_score = -(ts.timestamp() if ts else 0.0)
    return (stale_score, age_score, recency_score)


@dataclass
class GateIssue:
    severity: str  # "error" | "warn"
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Run objective reliability gate checks for lighter runtime.")
    parser.add_argument("--project", default="sapphire-479610")
    parser.add_argument("--platform", default="lighter")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--max-balance-age-sec", type=float, default=900.0)
    parser.add_argument("--max-position-age-sec", type=float, default=900.0)
    parser.add_argument("--max-drawdown-pct", type=float, default=-8.0, help="Negative percent floor (e.g. -8.0)")
    parser.add_argument("--max-position-notional-usd", type=float, default=8.0)
    parser.add_argument("--max-open-positions", type=int, default=1)
    parser.add_argument("--min-success-rate", type=float, default=0.50)
    parser.add_argument("--min-real-fills", type=int, default=0)
    parser.add_argument("--strict-jurisdiction", action="store_true")
    parser.add_argument(
        "--allow-partial-permissions",
        action="store_true",
        help="Do not fail when Firestore read permissions are unavailable; emit warning-only result.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON path. Default: output/reliability_gates/<timestamp>.json",
    )
    args = parser.parse_args()

    platform = str(args.platform).lower().strip()
    now = _now_utc()
    since = now - timedelta(hours=max(1, int(args.lookback_hours)))

    client = firestore.Client(project=args.project)
    issues: list[GateIssue] = []

    # Current equity / freshness snapshot
    snapshot_available = True
    snapshot_source = "equity_snapshots_current"
    try:
        snap_doc = client.collection("equity_snapshots_current").document(platform).get()
        if not snap_doc.exists:
            issues.append(GateIssue("error", f"Missing equity_snapshots_current/{platform}"))
            snapshot: dict[str, Any] = {}
        else:
            snapshot = snap_doc.to_dict() or {}
    except PermissionDenied as exc:
        if args.allow_partial_permissions:
            issues.append(GateIssue("warn", f"Firestore read permission denied for equity snapshot: {exc}"))
            snapshot_available = False
            snapshot = {}
        else:
            raise

    # If current snapshot is stale/empty, recover the best recent candidate from
    # equity_snapshots so active lane health isn't masked by a stale writer.
    if snapshot_available:
        current_rank = _snapshot_rank(snapshot)
        current_bad = (
            current_rank[0] >= 2.0
            or (
                _to_float(snapshot.get("equity_estimate"), 0.0) == 0.0
                and _to_int(snapshot.get("positions_count"), 0) == 0
                and _to_bool(snapshot.get("balance_sync_stale"), default=True)
                and _to_bool(snapshot.get("position_check_stale"), default=True)
            )
        )
        if current_bad:
            try:
                fallback_since = now - timedelta(minutes=45)
                query = (
                    client.collection("equity_snapshots")
                    .where(filter=FieldFilter("platform", "==", platform))
                    .where(filter=FieldFilter("recorded_at", ">=", fallback_since))
                    .order_by("recorded_at", direction=firestore.Query.DESCENDING)
                    .limit(80)
                )
                candidates: list[dict[str, Any]] = []
                for doc in query.stream():
                    row = doc.to_dict() or {}
                    if str(row.get("platform", "")).lower() != platform:
                        continue
                    candidates.append(row)
                if candidates:
                    best = min(candidates, key=_snapshot_rank)
                    best_rank = _snapshot_rank(best)
                    if best_rank < current_rank:
                        snapshot = best
                        snapshot_source = "equity_snapshots_recent_fallback"
                        issues.append(
                            GateIssue(
                                "warn",
                                "Using recent equity snapshot fallback due stale/empty current snapshot",
                            )
                        )
            except PermissionDenied as exc:
                if args.allow_partial_permissions:
                    issues.append(
                        GateIssue("warn", f"Firestore read permission denied for equity snapshot fallback: {exc}")
                    )
                else:
                    raise

    balance_age = _to_float(snapshot.get("balance_sync_age_sec"), default=0.0)
    position_age = _to_float(snapshot.get("position_check_age_sec"), default=0.0)
    balance_stale = _to_bool(snapshot.get("balance_sync_stale"), default=False)
    position_stale = _to_bool(snapshot.get("position_check_stale"), default=False)
    drawdown_pct = _to_float(snapshot.get("drawdown_pct"), default=0.0)
    position_notional = _to_float(snapshot.get("position_notional_usd"), default=0.0)
    positions_count = _to_int(snapshot.get("positions_count"), default=0)

    if snapshot_available:
        if balance_age > args.max_balance_age_sec:
            issues.append(GateIssue("error", f"Balance sync age too high: {balance_age:.1f}s > {args.max_balance_age_sec:.1f}s"))
        if position_age > args.max_position_age_sec:
            issues.append(GateIssue("error", f"Position sync age too high: {position_age:.1f}s > {args.max_position_age_sec:.1f}s"))
        if balance_stale:
            issues.append(GateIssue("error", "Balance sync is marked stale"))
        if position_stale:
            issues.append(GateIssue("error", "Position sync is marked stale"))
        if drawdown_pct < args.max_drawdown_pct:
            issues.append(GateIssue("error", f"Drawdown breach: {drawdown_pct:.3f}% < {args.max_drawdown_pct:.3f}%"))
        if position_notional > args.max_position_notional_usd:
            issues.append(
                GateIssue(
                    "error",
                    f"Position notional breach: ${position_notional:.4f} > ${args.max_position_notional_usd:.4f}",
                )
            )
        if positions_count > args.max_open_positions:
            issues.append(GateIssue("error", f"Open position count breach: {positions_count} > {args.max_open_positions}"))
    elif args.allow_partial_permissions:
        issues.append(GateIssue("warn", "Skipped snapshot-derived checks due to partial Firestore permissions"))

    # Live positions collection cross-check
    live_available = True
    try:
        live_doc = client.collection("live_positions").document(platform).get()
    except PermissionDenied as exc:
        if args.allow_partial_permissions:
            issues.append(GateIssue("warn", f"Firestore read permission denied for live_positions: {exc}"))
            live_available = False
            live_doc = None
        else:
            raise
    live_position_count = 0
    if live_doc and live_doc.exists:
        live_data = live_doc.to_dict() or {}
        live_position_count = _to_int(live_data.get("position_count"), default=0)
        if live_position_count > args.max_open_positions:
            issues.append(
                GateIssue("error", f"live_positions/{platform} count breach: {live_position_count} > {args.max_open_positions}")
            )
    elif not live_available and args.allow_partial_permissions:
        issues.append(GateIssue("warn", "Skipped live position cross-check due to partial Firestore permissions"))

    # Execution quality lookback
    exec_rows = []
    exec_available = True
    query = (
        client.collection("execution_verifications")
        .where(filter=FieldFilter("recorded_at", ">=", since))
        .order_by("recorded_at", direction=firestore.Query.ASCENDING)
    )
    try:
        for doc in query.stream():
            row = doc.to_dict() or {}
            if str(row.get("platform", "")).lower() != platform:
                continue
            exec_rows.append(row)
    except PermissionDenied as exc:
        if args.allow_partial_permissions:
            issues.append(GateIssue("warn", f"Firestore read permission denied for execution_verifications: {exc}"))
            exec_available = False
            exec_rows = []
        else:
            raise

    policy_noops = sum(
        1
        for x in exec_rows
        if str(x.get("outcome", "")).lower() in {"policy_noop", "noop"}
        or _to_bool((x.get("result_metadata") or {}).get("noop"), default=False)
    )
    effective_exec_rows = max(
        0,
        len(exec_rows) - policy_noops,
    )
    success_exec = sum(
        1
        for x in exec_rows
        if bool(x.get("success", False))
        and not (
            str(x.get("outcome", "")).lower() in {"policy_noop", "noop"}
            or _to_bool((x.get("result_metadata") or {}).get("noop"), default=False)
        )
    )
    real_fills = sum(
        1
        for x in exec_rows
        if _to_float(x.get("filled_quantity"), 0.0) > 0.0
        and not (
            str(x.get("outcome", "")).lower() in {"policy_noop", "noop"}
            or _to_bool((x.get("result_metadata") or {}).get("noop"), default=False)
        )
    )
    restricted_errs = sum(
        1
        for x in exec_rows
        if "restricted jurisdiction" in str(x.get("error_message", "") or "").lower()
    )

    success_rate = (success_exec / effective_exec_rows) if effective_exec_rows > 0 else 1.0

    if exec_available:
        if effective_exec_rows > 0 and success_rate < args.min_success_rate:
            issues.append(
                GateIssue(
                    "error",
                    f"Execution success rate low: {success_rate:.3f} < {args.min_success_rate:.3f} "
                    f"({success_exec}/{effective_exec_rows})",
                )
            )
        if real_fills < args.min_real_fills:
            issues.append(GateIssue("error", f"Real fills below minimum: {real_fills} < {args.min_real_fills}"))

        if restricted_errs > 0:
            sev = "error" if args.strict_jurisdiction else "warn"
            issues.append(GateIssue(sev, f"Restricted-jurisdiction execution errors in lookback: {restricted_errs}"))
    elif args.allow_partial_permissions:
        issues.append(GateIssue("warn", "Skipped execution-quality checks due to partial Firestore permissions"))

    error_count = sum(1 for i in issues if i.severity == "error")
    warn_count = sum(1 for i in issues if i.severity == "warn")
    passed = error_count == 0

    result = {
        "timestamp": now.isoformat(),
        "project": args.project,
        "platform": platform,
        "lookback_hours": args.lookback_hours,
        "passed": passed,
        "errors": error_count,
        "warnings": warn_count,
        "thresholds": {
            "max_balance_age_sec": args.max_balance_age_sec,
            "max_position_age_sec": args.max_position_age_sec,
            "max_drawdown_pct": args.max_drawdown_pct,
            "max_position_notional_usd": args.max_position_notional_usd,
            "max_open_positions": args.max_open_positions,
            "min_success_rate": args.min_success_rate,
            "min_real_fills": args.min_real_fills,
            "strict_jurisdiction": bool(args.strict_jurisdiction),
        },
        "snapshot": {
            "source": snapshot_source,
            "balance_sync_age_sec": balance_age,
            "position_check_age_sec": position_age,
            "balance_sync_stale": balance_stale,
            "position_check_stale": position_stale,
            "drawdown_pct": drawdown_pct,
            "position_notional_usd": position_notional,
            "positions_count": positions_count,
            "live_positions_count": live_position_count,
            "equity_estimate": _to_float(snapshot.get("equity_estimate"), 0.0),
            "cash_balance": _to_float(snapshot.get("cash_balance"), 0.0),
            "progress_pct": _to_float(snapshot.get("progress_pct"), 0.0),
        },
        "execution_window": {
            "rows": len(exec_rows),
            "effective_rows": effective_exec_rows,
            "successes": success_exec,
            "real_fills": real_fills,
            "policy_noops": policy_noops,
            "success_rate": round(success_rate, 6),
            "restricted_jurisdiction_errors": restricted_errs,
            "window_start": since.isoformat(),
            "window_end": now.isoformat(),
        },
        "data_availability": {
            "snapshot": snapshot_available,
            "live_positions": live_available,
            "execution_window": exec_available,
            "partial_permissions_mode": bool(args.allow_partial_permissions),
        },
        "issues": [{"severity": i.severity, "message": i.message} for i in issues],
    }

    if args.output:
        out_path = Path(args.output).expanduser()
    else:
        out_path = Path("output/reliability_gates") / f"lighter_gate_{now.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"\nSaved: {out_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
