#!/usr/bin/env python3
"""Read-only status report for remote-shadow routine soak gates."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - CI installs pyyaml
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "infra" / "org-repos.yaml"
DEFAULT_REPO = "arigatoexpress/Sapphire"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    report = build_report(
        manifest,
        repo=args.repo,
        external=not args.no_external,
        run_limit=args.run_limit,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--run-limit", type=int, default=50)
    parser.add_argument("--no-external", action="store_true", help="Skip GitHub Actions probes")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a mapping: {path}")
    return data


def build_report(
    manifest: dict[str, Any],
    *,
    repo: str = DEFAULT_REPO,
    external: bool = True,
    run_limit: int = 50,
) -> dict[str, Any]:
    routines = [
        routine
        for routine in manifest.get("routines", [])
        if routine.get("stage") == "soaking" and routine.get("remote_workflow")
    ]
    rows = [
        routine_soak_status(routine, repo=repo, external=external, run_limit=run_limit)
        for routine in routines
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "repo": repo,
        "external": external,
        "routine_count": len(rows),
        "summary": {
            "ready_for_artifact_review": sum(
                1 for row in rows if row["gate_state"] == "ready_for_artifact_review"
            ),
            "collecting": sum(1 for row in rows if row["gate_state"] == "collecting"),
            "blocked": sum(1 for row in rows if row["gate_state"] == "blocked"),
            "external_disabled": sum(1 for row in rows if row["gate_state"] == "external_disabled"),
        },
        "routines": rows,
    }


def routine_soak_status(
    routine: dict[str, Any],
    *,
    repo: str,
    external: bool,
    run_limit: int,
) -> dict[str, Any]:
    tracking = routine.get("soak_tracking", {})
    started_at = parse_started_at(tracking.get("started_at"))
    runs_result = (
        github_workflow_runs(repo=repo, workflow=str(routine["remote_workflow"]), limit=run_limit)
        if external
        else {"available": False, "runs": [], "error": "external probes disabled"}
    )
    runs = [sanitize_run(run) for run in runs_result.get("runs", [])]
    run_summary = summarize_runs(runs, started_at=started_at)
    required = int(tracking.get("required_scheduled_successes") or 0)
    gate_state = gate_state_for(
        available=bool(runs_result.get("available")),
        error=str(runs_result.get("error") or ""),
        scheduled_success=run_summary["scheduled_success_since_start"],
        required=required,
    )
    return {
        "id": routine["id"],
        "local_label": routine.get("local_label"),
        "stage": routine.get("stage"),
        "remote_workflow": routine.get("remote_workflow"),
        "workflow_name": Path(str(routine.get("remote_workflow"))).name,
        "comparator": routine.get("comparator"),
        "started_at": tracking.get("started_at"),
        "evidence_doc": tracking.get("evidence_doc"),
        "cutover_gate": routine.get("soak_tracking", {}).get("cutover_gate"),
        "required_scheduled_successes": required,
        "latest_comparison": tracking.get("latest_comparison", {}),
        "github_runs": {
            "available": runs_result.get("available"),
            "error": runs_result.get("error") or "",
            **run_summary,
        },
        "gate_state": gate_state,
    }


def github_workflow_runs(*, repo: str, workflow: str, limit: int) -> dict[str, Any]:
    if shutil.which("gh") is None:
        return {"available": False, "runs": [], "error": "gh not found on PATH"}
    workflow_name = Path(workflow).name
    cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow_name,
        "--limit",
        str(limit),
        "--json",
        "databaseId,status,conclusion,createdAt,event,headBranch,displayTitle",
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"available": False, "runs": [], "error": "gh run list timed out"}
    if proc.returncode != 0:
        return {"available": False, "runs": [], "error": compact_error(proc.stderr or proc.stdout)}
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        return {"available": False, "runs": [], "error": f"gh returned invalid JSON: {exc}"}
    return {"available": True, "runs": data if isinstance(data, list) else [], "error": ""}


def sanitize_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "database_id": run.get("databaseId"),
        "status": str(run.get("status") or ""),
        "conclusion": str(run.get("conclusion") or ""),
        "created_at": str(run.get("createdAt") or ""),
        "event": str(run.get("event") or ""),
        "head_branch": str(run.get("headBranch") or ""),
        "display_title": str(run.get("displayTitle") or ""),
    }


def summarize_runs(runs: list[dict[str, Any]], *, started_at: datetime | None) -> dict[str, Any]:
    runs_since_start = [
        run
        for run in runs
        if started_at is None or parse_github_time(run["created_at"]) >= started_at
    ]
    by_event = Counter(run["event"] or "unknown" for run in runs_since_start)
    by_conclusion = Counter(run["conclusion"] or "unknown" for run in runs_since_start)
    scheduled = [run for run in runs_since_start if run["event"] == "schedule"]
    manual = [run for run in runs_since_start if run["event"] == "workflow_dispatch"]
    latest = max(runs_since_start, key=lambda run: run["created_at"], default=None)
    return {
        "total_since_start": len(runs_since_start),
        "scheduled_total_since_start": len(scheduled),
        "scheduled_success_since_start": sum(
            1 for run in scheduled if run["conclusion"] == "success"
        ),
        "manual_total_since_start": len(manual),
        "manual_success_since_start": sum(1 for run in manual if run["conclusion"] == "success"),
        "by_event": dict(sorted(by_event.items())),
        "by_conclusion": dict(sorted(by_conclusion.items())),
        "latest_run": latest or {},
    }


def gate_state_for(
    *,
    available: bool,
    error: str,
    scheduled_success: int,
    required: int,
) -> str:
    if not available:
        return "external_disabled" if error == "external probes disabled" else "blocked"
    if required <= 0:
        return "collecting"
    return "ready_for_artifact_review" if scheduled_success >= required else "collecting"


def parse_started_at(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    text = str(value)
    if len(text) == 10:
        return datetime.combine(datetime.fromisoformat(text).date(), time.min, tzinfo=UTC)
    return parse_github_time(text)


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def compact_error(text: str, *, limit: int = 240) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sapphire Routine Soak Status",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Repo: `{report['repo']}`",
        f"- External probes: {'yes' if report['external'] else 'no'}",
        "",
        "## Summary",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for key, value in report["summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Routines",
            "",
            "| Routine | Workflow | Scheduled OK | Required | Manual OK | Latest Run | Latest Comparison | Gate State |",
            "|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for routine in report["routines"]:
        runs = routine["github_runs"]
        latest = runs.get("latest_run") or {}
        latest_run = "-"
        if latest:
            latest_run = "{id} {event}/{conclusion} {created}".format(
                id=latest.get("database_id") or "-",
                event=latest.get("event") or "-",
                conclusion=latest.get("conclusion") or latest.get("status") or "-",
                created=latest.get("created_at") or "-",
            )
        latest_comparison = routine.get("latest_comparison") or {}
        comparison = latest_comparison.get("verdict") or "-"
        if latest_comparison.get("rows_fail") is not None:
            comparison = f"{comparison} ({latest_comparison.get('rows_fail')} fail)"
        lines.append(
            "| {routine} | {workflow} | {scheduled} | {required} | {manual} | {latest} | {comparison} | {gate} |".format(
                routine=routine["id"],
                workflow=routine["workflow_name"],
                scheduled=runs["scheduled_success_since_start"],
                required=routine["required_scheduled_successes"],
                manual=runs["manual_success_since_start"],
                latest=latest_run,
                comparison=comparison,
                gate=routine["gate_state"],
            )
        )
        if runs.get("error"):
            lines.append(
                f"| {routine['id']} note | - |  |  |  | {runs['error']} | - | {routine['gate_state']} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
