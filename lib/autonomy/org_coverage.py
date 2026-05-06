"""Read-only organization coverage contract for the Sapphire dashboard.

The org manifest is the source of truth for Sapphire plus satellite repos.
This module folds that manifest together with the local ``org_status`` sweep
into a compact, paste-safe payload that UI surfaces can render without knowing
YAML field names or shell probe details.
"""

from __future__ import annotations

import importlib.util
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "infra" / "org-repos.yaml"
ORG_STATUS_SCRIPT = ROOT / "scripts" / "ops" / "org_status.py"
SCHEMA_VERSION = 1

MODULE_ORDER = (
    "core",
    "satellite",
    "integration",
    "candidate_absorb",
    "candidate_archive",
    "upstream",
)

MODULE_META = {
    "core": {
        "title": "Sapphire Core",
        "description": "Primary Sapphire OS control plane and operator-facing runtime.",
    },
    "satellite": {
        "title": "Satellite Repos",
        "description": "Independent apps and automations governed by Sapphire posture.",
    },
    "integration": {
        "title": "Integration Services",
        "description": "Connected production-adjacent services, bridges, and protected demos.",
    },
    "candidate_absorb": {
        "title": "Absorb Candidates",
        "description": "Repos that may become first-class Sapphire modules.",
    },
    "candidate_archive": {
        "title": "Archive Candidates",
        "description": "Repos kept visible while the retirement decision stays reversible.",
    },
    "upstream": {
        "title": "Upstream Watchlist",
        "description": "Forks and upstream integrations tracked for local-only sync risk.",
    },
}

SAFETY = {
    "execution_enabled": False,
    "live_trading_enabled": False,
    "telegram_sends_enabled": False,
    "writes_by_default": False,
    "guards": [
        "dashboard_read_only",
        "manifest_driven_repo_inventory",
        "local_git_probe_only_by_default",
        "operator_review_required_for_mutations",
    ],
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_org_status() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sapphire_org_status_for_coverage", ORG_STATUS_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load org_status from {ORG_STATUS_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _path_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    parts = path.parts
    if "Code" in parts:
        index = parts.index("Code")
        return "/".join(parts[index:])
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return path.name or text


def _github_url(repo: str | None) -> str | None:
    if not repo:
        return None
    cleaned = str(repo).strip()
    if not cleaned:
        return None
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return f"https://github.com/{cleaned}"


def _state(row: dict[str, Any]) -> str:
    if "exists" in row and not row.get("exists"):
        return "missing"
    if row.get("clean") is True:
        return "clean"
    dirty_count = row.get("dirty_count")
    if isinstance(dirty_count, int) and dirty_count > 0:
        return "dirty"
    if row.get("errors"):
        return "needs_probe"
    return "unknown"


def _badge_class(state: str) -> str:
    return {
        "clean": "online",
        "dirty": "warning",
        "missing": "error",
        "needs_probe": "warning",
        "unknown": "offline",
    }.get(state, "offline")


def _status_label(state: str) -> str:
    return {
        "clean": "clean",
        "dirty": "needs attention",
        "missing": "missing",
        "needs_probe": "probe warning",
        "unknown": "unknown",
    }.get(state, state.replace("_", " "))


def _next_step(state: str, row: dict[str, Any], manifest_repo: dict[str, Any] | None = None) -> str:
    manifest_repo = manifest_repo or {}
    if state == "missing":
        return "Add local checkout or mark repo as remote-only."
    if state == "dirty":
        return "Inspect local WIP before merge, cleanup, or automation changes."
    if state == "needs_probe":
        return "Refresh local git probe and resolve reported errors."
    if manifest_repo.get("migration_state"):
        return str(manifest_repo["migration_state"]).replace("_", " ")
    return "Covered by manifest and local status sweep."


def _repo_row(
    status: dict[str, Any], manifest_repo: dict[str, Any] | None = None
) -> dict[str, Any]:
    manifest_repo = manifest_repo or {}
    state = _state(status)
    guardrails = list(manifest_repo.get("required_guardrails") or [])
    open_prs = list(status.get("open_prs") or [])
    open_issues = list(status.get("open_issues") or [])
    return {
        "id": status.get("id") or manifest_repo.get("id"),
        "name": status.get("name") or manifest_repo.get("name"),
        "classification": status.get("classification")
        or manifest_repo.get("classification")
        or "unknown",
        "role": status.get("role") or manifest_repo.get("role"),
        "state": state,
        "status_label": _status_label(state),
        "badge_class": _badge_class(state),
        "exists": bool(status.get("exists")),
        "clean": status.get("clean"),
        "dirty_count": status.get("dirty_count") or 0,
        "dirty_summary": status.get("dirty_summary") or {},
        "branch": status.get("branch"),
        "head": status.get("head"),
        "default_branch": status.get("default_branch") or manifest_repo.get("default_branch"),
        "ci_strategy": status.get("ci_strategy") or manifest_repo.get("ci_strategy"),
        "migration_state": status.get("migration_state") or manifest_repo.get("migration_state"),
        "production_adjacent": bool(
            status.get("production_adjacent") or manifest_repo.get("production_adjacent")
        ),
        "guardrails": guardrails,
        "guardrail_count": len(guardrails),
        "github": status.get("github") or manifest_repo.get("github"),
        "github_url": _github_url(status.get("github") or manifest_repo.get("github")),
        "pr_github_url": _github_url(status.get("pr_github") or manifest_repo.get("pr_github")),
        "issue_github_url": _github_url(
            status.get("issue_github") or manifest_repo.get("issue_github")
        ),
        "local_path_label": _path_label(
            status.get("local_path") or manifest_repo.get("local_path")
        ),
        "open_pr_count": len(open_prs),
        "open_issue_count": len(open_issues),
        "errors": list(status.get("errors") or []),
        "runtime": _runtime_row(status.get("runtime")),
        "next_step": _next_step(state, status, manifest_repo),
    }


def _runtime_row(runtime: Any) -> dict[str, Any] | None:
    if not isinstance(runtime, dict):
        return None
    state = _state(runtime)
    return {
        "launchagent_label": runtime.get("launchagent_label"),
        "state": state,
        "status_label": _status_label(state),
        "badge_class": _badge_class(state),
        "exists": bool(runtime.get("exists")),
        "branch": runtime.get("branch"),
        "head": runtime.get("head"),
        "dirty_count": runtime.get("dirty_count") or 0,
        "dirty_summary": runtime.get("dirty_summary") or {},
        "expected_branch": runtime.get("expected_branch"),
        "local_path_label": _path_label(runtime.get("runtime_path")),
        "errors": list(runtime.get("errors") or []),
    }


def _upstream_row(status: dict[str, Any]) -> dict[str, Any]:
    state = _state(status)
    return {
        "id": status.get("id"),
        "name": status.get("name"),
        "classification": "upstream",
        "role": status.get("integration_surface"),
        "state": state,
        "status_label": _status_label(state),
        "badge_class": _badge_class(state),
        "exists": bool(status.get("exists")),
        "clean": status.get("clean"),
        "dirty_count": status.get("dirty_count") or 0,
        "dirty_summary": status.get("dirty_summary") or {},
        "branch": status.get("branch"),
        "head": status.get("head"),
        "sync_state": status.get("sync_state"),
        "upstream": status.get("upstream"),
        "upstream_url": _github_url(status.get("upstream")),
        "ari_fork": status.get("ari_fork"),
        "ari_fork_url": _github_url(status.get("ari_fork")),
        "local_path_label": _path_label(status.get("local_path")),
        "errors": list(status.get("errors") or []),
        "next_step": _next_step(state, status),
    }


def _worktree_row(status: dict[str, Any]) -> dict[str, Any]:
    state = _state(status)
    return {
        "branch": status.get("branch") or "detached",
        "state": state,
        "status_label": _status_label(state),
        "badge_class": _badge_class(state),
        "clean": status.get("clean"),
        "dirty_count": status.get("dirty_count") or 0,
        "dirty_summary": status.get("dirty_summary") or {},
        "head": status.get("head"),
        "upstream": status.get("upstream"),
        "main_checkout": bool(status.get("main_checkout")),
        "detached": bool(status.get("detached")),
        "locked": bool(status.get("locked")),
        "prunable": bool(status.get("prunable")),
        "local_path_label": _path_label(status.get("path")),
        "errors": list(status.get("errors") or []),
    }


def _module_rows(
    repos: list[dict[str, Any]], upstream: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in MODULE_ORDER}
    for repo in repos:
        grouped.setdefault(str(repo.get("classification") or "unknown"), []).append(repo)
    grouped["upstream"] = upstream

    modules: list[dict[str, Any]] = []
    for module_id in MODULE_ORDER:
        rows = grouped.get(module_id, [])
        if not rows and module_id == "upstream":
            continue
        total = len(rows)
        clean_count = sum(1 for row in rows if row.get("state") == "clean")
        dirty_count = sum(1 for row in rows if row.get("state") == "dirty")
        missing_count = sum(1 for row in rows if row.get("state") == "missing")
        attention_count = sum(1 for row in rows if row.get("state") != "clean")
        coverage_pct = round((clean_count / total) * 100) if total else 0
        meta = MODULE_META.get(
            module_id,
            {
                "title": module_id.replace("_", " ").title(),
                "description": "Manifest-governed repository group.",
            },
        )
        modules.append(
            {
                "id": module_id,
                "title": meta["title"],
                "description": meta["description"],
                "repo_count": total,
                "clean_count": clean_count,
                "dirty_count": dirty_count,
                "missing_count": missing_count,
                "attention_count": attention_count,
                "coverage_pct": coverage_pct,
                "badge_class": "online"
                if total and attention_count == 0
                else ("warning" if total else "offline"),
                "repos": rows,
            }
        )
    return modules


def _count_map_rows(counts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, value in sorted((counts or {}).items()):
        rows.append({"id": str(key), "label": str(key).replace("_", " "), "count": int(value or 0)})
    return rows


def build_org_coverage(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    status_report: dict[str, Any] | None = None,
    external: bool = False,
) -> dict[str, Any]:
    """Return a dashboard-ready coverage packet for Sapphire and satellites."""
    org_status = _load_org_status()
    manifest = org_status.load_manifest(manifest_path)
    report = status_report or org_status.collect_status(manifest, external=external)
    manifest_by_id = {
        str(repo.get("id")): repo
        for repo in manifest.get("repos", [])
        if isinstance(repo, dict) and repo.get("id")
    }

    repos = [
        _repo_row(row, manifest_by_id.get(str(row.get("id")))) for row in report.get("repos", [])
    ]
    upstream = [_upstream_row(row) for row in report.get("upstream_repos", [])]
    worktrees = [_worktree_row(row) for row in report.get("worktrees", [])]
    modules = _module_rows(repos, upstream)

    repo_states = Counter(row["state"] for row in repos)
    upstream_states = Counter(row["state"] for row in upstream)
    summary = {
        "repos_tracked": len(repos),
        "satellite_repos": sum(1 for row in repos if row.get("classification") == "satellite"),
        "core_repos": sum(1 for row in repos if row.get("classification") == "core"),
        "integration_repos": sum(1 for row in repos if row.get("classification") == "integration"),
        "production_adjacent_repos": sum(1 for row in repos if row.get("production_adjacent")),
        "clean_repos": repo_states["clean"],
        "dirty_repos": repo_states["dirty"],
        "missing_repos": repo_states["missing"],
        "upstream_tracked": len(upstream),
        "clean_upstreams": upstream_states["clean"],
        "dirty_upstreams": upstream_states["dirty"],
        "missing_upstreams": upstream_states["missing"],
        "modules_tracked": len(modules),
        "worktree_count": len(worktrees),
        "dirty_worktree_count": sum(1 for row in worktrees if row.get("state") == "dirty"),
        "routine_count": len(report.get("routines") or []),
        "open_pr_count": (report.get("summary") or {}).get("open_pr_count", 0),
        "external_checked": bool((report.get("summary") or {}).get("open_prs_checked")),
    }
    summary["attention_items"] = (
        summary["dirty_repos"]
        + summary["missing_repos"]
        + summary["dirty_upstreams"]
        + summary["missing_upstreams"]
        + summary["dirty_worktree_count"]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "org_coverage",
        "generated_at": report.get("generated_at") or _now_iso(),
        "manifest": report.get("manifest", {}),
        "summary": summary,
        "safety": dict(SAFETY),
        "execution_enabled": False,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "writes_by_default": False,
        "modules": modules,
        "repos": repos,
        "upstream_repos": upstream,
        "worktrees": worktrees,
        "ci_strategies": _count_map_rows((report.get("summary") or {}).get("ci_strategies", {})),
        "routine_stages": _count_map_rows((report.get("summary") or {}).get("routine_stages", {})),
        "hermes_skill_classes": _count_map_rows(
            (report.get("summary") or {}).get("hermes_skill_classes", {})
        ),
        "programs": [
            {
                "name": module["title"],
                "status": "active" if module["attention_count"] == 0 else "needs_attention",
                "progress": module["coverage_pct"],
                "repo_count": module["repo_count"],
            }
            for module in modules
        ],
    }
