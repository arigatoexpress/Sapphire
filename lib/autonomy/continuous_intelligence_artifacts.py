"""Artifact sink and dry-run leases for continuous intelligence tasks.

This module is the persistence bridge after ``continuous_intelligence``. It can
materialize task snapshots, produce lease records for local/Windows/GitHub
workers, and record reviewed results. Writes are opt-in; API consumers should
use the preview/status helpers unless an operator explicitly enables local
artifact writes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from lib.autonomy.continuous_intelligence import build_continuous_intelligence_plan
from lib.core.provenance import write_envelope_sidecar

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = ROOT / "data" / ".autonomy" / "continuous_intelligence"
TASK_SNAPSHOT_FILE = "task_snapshots.jsonl"
LEASE_FILE = "task_leases.jsonl"
RESULT_FILE = "task_results.jsonl"
DAILY_PACKET_FILE = "daily_autonomy_packets.jsonl"
DAILY_PACKET_LATEST_FILE = "daily_autonomy_packet_latest.json"
SCHEMA_VERSION = 1
SAFE_MODES = {"read_only", "dry_run", "paper"}
RESULT_STATUSES = {"completed", "failed", "blocked", "rejected", "needs_review"}
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}
SENSITIVE_KEY_RE = re.compile(
    r"(secret|token|password|private[_-]?key|api[_-]?key|seed|mnemonic|credential)",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def _safe_token(value: str, *, default: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value or "").strip()).strip("-")
    return cleaned[:96] or default


def _artifact_paths(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Path]:
    return {
        "task_snapshots": artifact_dir / TASK_SNAPSHOT_FILE,
        "task_leases": artifact_dir / LEASE_FILE,
        "task_results": artifact_dir / RESULT_FILE,
        "daily_packets": artifact_dir / DAILY_PACKET_FILE,
    }


def _task_capabilities(task: dict[str, Any]) -> set[str]:
    values = {
        str(task.get("lane") or ""),
        str(task.get("target_runtime") or ""),
        str(task.get("model_tier") or ""),
        str(task.get("safe_mode") or ""),
    }
    values.update(str(item) for item in task.get("inputs") or [])
    values.update(str(item) for item in task.get("symbols") or [])
    return {value for value in values if value}


def _blocked(task: dict[str, Any]) -> bool:
    return bool(task.get("blocked_by"))


def _validate_task(task: dict[str, Any]) -> None:
    task_id = str(task.get("id") or "").strip()
    if not task_id:
        raise ValueError("task is missing id")
    safe_mode = str(task.get("safe_mode") or "")
    if safe_mode not in SAFE_MODES:
        raise ValueError(f"unsafe task mode {safe_mode!r} for {task_id}")


def _runtime_guard(
    *,
    target_runtime: str | None,
    runtime_status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a dry-run dispatch guard for runtime-specific leases."""
    if target_runtime != "windows-gpu":
        return {
            "applied": False,
            "status": "not_required",
            "target_runtime": target_runtime,
            "reason": None,
            "message": None,
        }
    if not runtime_status:
        return {
            "applied": False,
            "status": "unknown",
            "target_runtime": target_runtime,
            "reason": "runtime_status_absent",
            "message": "Windows GPU lease preview did not receive failover status.",
        }

    windows_offline = bool(runtime_status.get("windows_offline"))
    fallback_ready = bool(runtime_status.get("fallback_ready"))
    mode = str(runtime_status.get("mode") or "unknown")
    if windows_offline:
        return {
            "applied": True,
            "status": "blocked",
            "target_runtime": target_runtime,
            "reason": "windows_gpu_primary_unavailable",
            "mode": mode,
            "active_route": runtime_status.get("active_route"),
            "fallback_ready": fallback_ready,
            "message": (
                "Windows GPU is offline; GPU-primary dry-run leases are paused "
                "until the primary tier is healthy."
            ),
        }

    return {
        "applied": True,
        "status": "pass",
        "target_runtime": target_runtime,
        "reason": None,
        "mode": mode,
        "active_route": runtime_status.get("active_route"),
        "fallback_ready": fallback_ready,
        "message": "Windows GPU primary tier is available for dry-run lease preview.",
    }


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _append_jsonl(path: Path, rows: list[dict[str, Any]], *, write: bool) -> None:
    if not write:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    write_envelope_sidecar(
        path,
        generator="lib.autonomy.continuous_intelligence_artifacts",
        metadata={
            "record_count": len(_jsonl_rows(path)),
            "artifact_family": "continuous_intelligence",
        },
    )


def _write_json(path: Path, payload: dict[str, Any], *, write: bool) -> None:
    if not write:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_envelope_sidecar(
        path,
        generator="lib.autonomy.continuous_intelligence_artifacts",
        metadata={
            "artifact_family": "continuous_intelligence",
            "artifact_kind": "daily_autonomy_packet_latest",
        },
    )


def _assert_no_sensitive_keys(payload: Any, *, path: str = "result") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_str = str(key)
            if SENSITIVE_KEY_RE.search(key_str):
                raise ValueError(f"sensitive result key rejected: {path}.{key_str}")
            _assert_no_sensitive_keys(value, path=f"{path}.{key_str}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _assert_no_sensitive_keys(item, path=f"{path}[{index}]")


def _plan_tasks(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = plan or build_continuous_intelligence_plan(fetch_live=False)
    tasks = [dict(task) for task in payload.get("tasks") or []]
    for task in tasks:
        _validate_task(task)
    return tasks


def build_task_snapshot_records(
    plan: dict[str, Any] | None = None,
    *,
    generated_by: str = "continuous_intelligence",
    captured_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return one snapshot record per planner task without writing files."""
    payload = plan or build_continuous_intelligence_plan(fetch_live=False)
    captured = _iso(captured_at)
    records: list[dict[str, Any]] = []
    for task in _plan_tasks(payload):
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "continuous_intelligence_task_snapshot",
                "captured_at": captured,
                "plan_generated_at": payload.get("generated_at"),
                "generated_by": generated_by,
                "task_id": task["id"],
                "lane": task.get("lane"),
                "priority": task.get("priority"),
                "target_runtime": task.get("target_runtime"),
                "model_tier": task.get("model_tier"),
                "safe_mode": task.get("safe_mode"),
                "status": "blocked" if _blocked(task) else "queued",
                "blocked_by": list(task.get("blocked_by") or []),
                "expected_artifacts": list(task.get("expected_artifacts") or []),
                "task": task,
                "safety": {
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                },
            }
        )
    return records


def snapshot_tasks(
    plan: dict[str, Any] | None = None,
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    write: bool = False,
    generated_by: str = "continuous_intelligence",
) -> dict[str, Any]:
    """Preview or append task snapshot records.

    ``write=False`` is the default and does not create directories or files.
    """
    records = build_task_snapshot_records(plan, generated_by=generated_by)
    target = _artifact_paths(artifact_dir)["task_snapshots"]
    _append_jsonl(target, records, write=write)
    lanes = Counter(str(record.get("lane") or "") for record in records)
    return {
        "mode": "local_artifact_snapshot",
        "write_enabled": bool(write),
        "writes_by_default": False,
        "artifact_dir": str(artifact_dir),
        "target_file": str(target),
        "records": len(records),
        "blocked": sum(1 for record in records if record.get("status") == "blocked"),
        "lanes": dict(sorted(lanes.items())),
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
        },
    }


def lease_tasks(
    plan: dict[str, Any] | None = None,
    *,
    agent_id: str,
    capabilities: list[str] | None = None,
    target_runtime: str | None = None,
    runtime_status: dict[str, Any] | None = None,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    lease_seconds: int = 1800,
    limit: int = 3,
    write: bool = False,
) -> dict[str, Any]:
    """Preview or append dry-run lease records for unblocked safe tasks."""
    cleaned_agent = _safe_token(agent_id, default="agent")
    capability_set = {str(item) for item in (capabilities or []) if str(item).strip()}
    effective_limit = max(1, min(int(limit or 1), 20))
    effective_lease_seconds = max(60, min(int(lease_seconds or 1800), 24 * 3600))
    now = _now()
    expires = now + timedelta(seconds=effective_lease_seconds)
    tasks = _plan_tasks(plan)

    candidates: list[dict[str, Any]] = []
    for task in tasks:
        if _blocked(task):
            continue
        if target_runtime and task.get("target_runtime") != target_runtime:
            continue
        if capability_set and capability_set.isdisjoint(_task_capabilities(task)):
            continue
        candidates.append(task)

    candidates.sort(
        key=lambda task: (
            PRIORITY_ORDER.get(str(task.get("priority") or ""), 99),
            str(task.get("lane") or ""),
            str(task.get("id") or ""),
        )
    )
    runtime_guard = _runtime_guard(target_runtime=target_runtime, runtime_status=runtime_status)
    selected = [] if runtime_guard["status"] == "blocked" else candidates[:effective_limit]
    records = []
    for task in selected:
        task_id = str(task["id"])
        lease_id = "-".join((now.strftime("%Y%m%dT%H%M%SZ"), cleaned_agent, _safe_token(task_id)))
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "continuous_intelligence_task_lease",
                "lease_id": lease_id,
                "leased_at": _iso(now),
                "expires_at": _iso(expires),
                "agent_id": cleaned_agent,
                "task_id": task_id,
                "status": "leased",
                "safe_mode": task.get("safe_mode"),
                "target_runtime": task.get("target_runtime"),
                "capabilities": sorted(capability_set),
                "task": task,
                "safety": {
                    "dry_run_dispatch_only": True,
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                },
            }
        )

    target = _artifact_paths(artifact_dir)["task_leases"]
    _append_jsonl(target, records, write=write)
    return {
        "mode": "dry_run_task_lease",
        "write_enabled": bool(write),
        "writes_by_default": False,
        "agent_id": cleaned_agent,
        "target_runtime": target_runtime,
        "lease_seconds": effective_lease_seconds,
        "artifact_dir": str(artifact_dir),
        "target_file": str(target),
        "candidate_count": len(candidates),
        "blocked_by_runtime": len(candidates) if runtime_guard["status"] == "blocked" else 0,
        "leased_count": len(records),
        "leases": records,
        "runtime_guard": runtime_guard,
        "safety": {
            "dry_run_dispatch_only": True,
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
        },
    }


def record_task_result(
    *,
    task_id: str,
    agent_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    write: bool = False,
) -> dict[str, Any]:
    """Preview or append a reviewed task result.

    This rejects obvious secret-bearing keys before any optional write.
    """
    cleaned_status = str(status or "").strip().lower()
    if cleaned_status not in RESULT_STATUSES:
        raise ValueError(f"status must be one of {sorted(RESULT_STATUSES)}")
    payload = result or {}
    _assert_no_sensitive_keys(payload)
    safe_artifacts = artifacts or []
    _assert_no_sensitive_keys(safe_artifacts, path="artifacts")
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "continuous_intelligence_task_result",
        "recorded_at": _iso(),
        "task_id": _safe_token(task_id, default="task"),
        "agent_id": _safe_token(agent_id, default="agent"),
        "status": cleaned_status,
        "result": payload,
        "artifacts": safe_artifacts,
        "safety": {
            "operator_review_required": cleaned_status in {"completed", "needs_review"},
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "writes_by_default": False,
        },
    }
    target = _artifact_paths(artifact_dir)["task_results"]
    _append_jsonl(target, [record], write=write)
    return {
        "mode": "task_result_record",
        "write_enabled": bool(write),
        "writes_by_default": False,
        "target_file": str(target),
        "record": record,
    }


def daily_autonomy_packet(
    plan: dict[str, Any] | None = None,
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    agent_id: str = "continuous-intelligence-daily",
    lease_targets: list[str] | None = None,
    lease_seconds: int = 24 * 3600,
    limit_per_target: int = 3,
    write: bool = False,
) -> dict[str, Any]:
    """Build or write the daily autonomy packet without executing tasks.

    A write appends the task snapshot, appends dry-run leases for the requested
    runtimes, appends the packet itself, and refreshes a latest JSON pointer.
    It never dispatches workers, sends Telegram, or changes trading state.
    """
    payload = plan or build_continuous_intelligence_plan(fetch_live=False)
    generated_at = _iso()
    cleaned_agent = _safe_token(agent_id, default="continuous-intelligence-daily")
    default_targets = ["mac-local", "windows-gpu"]
    targets = [
        _safe_token(target, default="runtime") for target in (lease_targets or default_targets)
    ]
    snapshot = snapshot_tasks(
        payload,
        artifact_dir=artifact_dir,
        write=write,
        generated_by="daily_autonomy_packet",
    )
    leases = [
        lease_tasks(
            payload,
            agent_id=f"{cleaned_agent}-{target}",
            target_runtime=target,
            artifact_dir=artifact_dir,
            lease_seconds=lease_seconds,
            limit=limit_per_target,
            write=write,
        )
        for target in targets
    ]
    snapshot_records = build_task_snapshot_records(
        payload,
        generated_by="daily_autonomy_packet",
        captured_at=_now(),
    )
    queued = [record for record in snapshot_records if record.get("status") == "queued"]
    blocked = [record for record in snapshot_records if record.get("status") == "blocked"]
    lanes = Counter(str(record.get("lane") or "") for record in snapshot_records)
    priorities = Counter(str(record.get("priority") or "") for record in snapshot_records)
    packet_id = f"{_safe_token(generated_at, default='packet')}-{cleaned_agent}"
    packet = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "continuous_intelligence_daily_autonomy_packet",
        "mode": "daily_autonomy_packet",
        "packet_id": packet_id,
        "generated_at": generated_at,
        "plan_generated_at": payload.get("generated_at"),
        "agent_id": cleaned_agent,
        "write_enabled": bool(write),
        "writes_by_default": False,
        "artifact_dir": str(artifact_dir),
        "target_file": str(_artifact_paths(artifact_dir)["daily_packets"]),
        "latest_file": str(artifact_dir / DAILY_PACKET_LATEST_FILE),
        "totals": {
            "tasks": len(snapshot_records),
            "queued": len(queued),
            "blocked": len(blocked),
            "leased": sum(int(lease.get("leased_count") or 0) for lease in leases),
        },
        "lanes": dict(sorted(lanes.items())),
        "priorities": dict(sorted(priorities.items())),
        "snapshot": snapshot,
        "leases": leases,
        "next_tasks": [_packet_task_summary(record) for record in queued[:10]],
        "blocked_tasks": [_packet_task_summary(record) for record in blocked[:5]],
        "safety": {
            "dry_run_dispatch_only": True,
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "scheduler_writes_local_artifacts_only": True,
        },
    }
    paths = _artifact_paths(artifact_dir)
    _append_jsonl(paths["daily_packets"], [packet], write=write)
    _write_json(artifact_dir / DAILY_PACKET_LATEST_FILE, packet, write=write)
    packet["artifact_status"] = artifact_status(artifact_dir=artifact_dir)
    return packet


def _packet_task_summary(record: dict[str, Any]) -> dict[str, Any]:
    task = record.get("task") or {}
    return {
        "task_id": record.get("task_id"),
        "lane": record.get("lane"),
        "priority": record.get("priority"),
        "target_runtime": record.get("target_runtime"),
        "safe_mode": record.get("safe_mode"),
        "title": task.get("title"),
        "blocked_by": list(record.get("blocked_by") or []),
        "expected_artifacts": list(record.get("expected_artifacts") or [])[:4],
    }


def artifact_status(*, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> dict[str, Any]:
    """Summarize local continuous-intelligence artifacts without mutating state."""
    paths = _artifact_paths(artifact_dir)
    files: dict[str, dict[str, Any]] = {}
    totals: dict[str, int] = {}
    for label, path in paths.items():
        rows = _jsonl_rows(path)
        totals[label] = len(rows)
        latest = rows[-1] if rows else None
        files[label] = {
            "path": str(path),
            "exists": path.exists(),
            "rows": len(rows),
            "latest_at": (
                latest.get("captured_at")
                or latest.get("leased_at")
                or latest.get("recorded_at")
                or latest.get("generated_at")
                if latest
                else None
            ),
        }
    latest_packet = artifact_dir / DAILY_PACKET_LATEST_FILE
    files["daily_packet_latest"] = {
        "path": str(latest_packet),
        "exists": latest_packet.exists(),
        "rows": 1 if latest_packet.exists() else 0,
        "latest_at": None,
    }
    return {
        "mode": "continuous_intelligence_artifact_status",
        "artifact_dir": str(artifact_dir),
        "writes_by_default": False,
        "execution_enabled": False,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "files": files,
        "totals": totals,
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status_parser = sub.add_parser("status", help="Read local artifact status.")
    status_parser.add_argument("--pretty", action="store_true")

    snapshot_parser = sub.add_parser("snapshot", help="Preview or write task snapshots.")
    snapshot_parser.add_argument("--write", action="store_true")
    snapshot_parser.add_argument("--pretty", action="store_true")

    lease_parser = sub.add_parser("lease", help="Preview or write dry-run task leases.")
    lease_parser.add_argument("--agent-id", required=True)
    lease_parser.add_argument("--target-runtime")
    lease_parser.add_argument("--capability", action="append", default=[])
    lease_parser.add_argument("--limit", type=int, default=3)
    lease_parser.add_argument("--lease-seconds", type=int, default=1800)
    lease_parser.add_argument("--write", action="store_true")
    lease_parser.add_argument("--pretty", action="store_true")

    packet_parser = sub.add_parser(
        "daily-packet",
        help="Preview or write the daily autonomy packet and dry-run leases.",
    )
    packet_parser.add_argument("--agent-id", default="continuous-intelligence-daily")
    packet_parser.add_argument(
        "--lease-target",
        action="append",
        default=[],
        help="Runtime to lease tasks for; defaults to mac-local and windows-gpu.",
    )
    packet_parser.add_argument("--limit-per-target", type=int, default=3)
    packet_parser.add_argument("--lease-seconds", type=int, default=24 * 3600)
    packet_parser.add_argument("--write", action="store_true")
    packet_parser.add_argument("--pretty", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "status":
        payload = artifact_status()
    elif args.command == "snapshot":
        payload = snapshot_tasks(write=bool(args.write))
    elif args.command == "lease":
        payload = lease_tasks(
            agent_id=args.agent_id,
            capabilities=list(args.capability or []),
            target_runtime=args.target_runtime,
            lease_seconds=args.lease_seconds,
            limit=args.limit,
            write=bool(args.write),
        )
    elif args.command == "daily-packet":
        payload = daily_autonomy_packet(
            agent_id=args.agent_id,
            lease_targets=list(args.lease_target or []) or None,
            lease_seconds=args.lease_seconds,
            limit_per_target=args.limit_per_target,
            write=bool(args.write),
        )
    else:
        raise AssertionError(args.command)

    pretty = bool(getattr(args, "pretty", False))
    print(json.dumps(payload, indent=2 if pretty else None, sort_keys=pretty))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())


__all__ = [
    "artifact_status",
    "build_task_snapshot_records",
    "daily_autonomy_packet",
    "lease_tasks",
    "record_task_result",
    "snapshot_tasks",
    "cli",
]
