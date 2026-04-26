#!/usr/bin/env python3
"""Sapphire autonomous organization status collector.

Read-only control-tower helper. It combines the org manifest with local git
state and, unless disabled, lightweight GitHub/GCP/launchd/Docker probes.
Failures are reported inline instead of aborting the whole status report.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - CI installs pyyaml
    raise SystemExit("PyYAML is required: python -m pip install pyyaml") from exc

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "infra" / "org-repos.yaml"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    report = collect_status(manifest, external=not args.no_external)
    rendered = render_markdown(report) if args.markdown else json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    elif args.markdown:
        print(rendered, end="")
    else:
        print(rendered, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--no-external", action="store_true", help="Skip gh/gcloud/launchctl/docker probes")
    return parser


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a mapping: {path}")
    return data


def collect_status(manifest: dict[str, Any], *, external: bool = True) -> dict[str, Any]:
    repos = [repo_status(repo, external=external) for repo in manifest.get("repos", [])]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "generated_for": manifest.get("generated_for"),
            "updated_at": manifest.get("updated_at"),
        },
        "summary": summarize(manifest, repos),
        "repos": repos,
        "gcp_projects": gcp_status(manifest.get("gcp_projects", []), external=external),
        "local_runtime": local_runtime_status(manifest.get("local_runtime", {}), external=external),
        "routines": manifest.get("routines", []),
        "waves": manifest.get("waves", []),
    }
    return report


def summarize(manifest: dict[str, Any], repos: list[dict[str, Any]]) -> dict[str, Any]:
    classifications: dict[str, int] = {}
    for repo in manifest.get("repos", []):
        key = str(repo.get("classification") or "unknown")
        classifications[key] = classifications.get(key, 0) + 1
    return {
        "repo_count": len(repos),
        "repo_classifications": classifications,
        "dirty_repos": [repo["id"] for repo in repos if (repo.get("dirty_count") or 0) > 0],
        "missing_local_repos": [repo["id"] for repo in repos if not repo.get("exists")],
        "open_pr_count": sum(len(repo.get("open_prs", [])) for repo in repos),
        "routine_stages": stage_counts(manifest.get("routines", [])),
    }


def stage_counts(routines: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for routine in routines:
        stage = str(routine.get("stage") or "unknown")
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def repo_status(repo: dict[str, Any], *, external: bool) -> dict[str, Any]:
    path = Path(str(repo.get("local_path") or ""))
    status: dict[str, Any] = {
        "id": repo.get("id"),
        "name": repo.get("name"),
        "classification": repo.get("classification"),
        "role": repo.get("role"),
        "local_path": str(path),
        "github": repo.get("github"),
        "default_branch": repo.get("default_branch"),
        "production_adjacent": bool(repo.get("production_adjacent")),
        "migration_state": repo.get("migration_state"),
        "exists": path.exists(),
        "branch": None,
        "head": None,
        "dirty_count": None,
        "clean": None,
        "open_prs": [],
        "open_issues": [],
        "errors": [],
    }
    if not path.exists():
        status["errors"].append("local path missing")
        return status
    branch = run(["git", "branch", "--show-current"], cwd=path)
    head = run(["git", "log", "-1", "--oneline", "--decorate"], cwd=path)
    dirty = run(["git", "status", "--porcelain=v1"], cwd=path)
    status["branch"] = branch["stdout"].strip() if branch["ok"] else None
    status["head"] = head["stdout"].strip() if head["ok"] else None
    dirty_lines = dirty["stdout"].splitlines() if dirty["ok"] else []
    status["dirty_count"] = len(dirty_lines)
    status["clean"] = dirty["ok"] and len(dirty_lines) == 0
    for result_name, result in (("branch", branch), ("head", head), ("dirty", dirty)):
        if not result["ok"]:
            status["errors"].append(f"git {result_name} failed: {result['stderr'][:160]}")
    if external and repo.get("github"):
        status["open_prs"] = gh_items("pr", str(repo["github"]))
        status["open_issues"] = gh_items("issue", str(repo["github"]))
    return status


def gh_items(kind: str, repo: str) -> list[dict[str, Any]]:
    if kind == "pr":
        fields = "number,title,headRefName,isDraft,updatedAt"
        jq = ".[] | {number,title,headRefName,isDraft,updatedAt}"
        args = ["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "10"]
    else:
        fields = "number,title,updatedAt"
        jq = ".[] | {number,title,updatedAt}"
        args = ["gh", "issue", "list", "--repo", repo, "--state", "open", "--limit", "10"]
    result = run([*args, "--json", fields, "--jq", f"[{jq}]"], timeout=20)
    if not result["ok"]:
        return [{"error": result["stderr"][:200]}]
    try:
        data = json.loads(result["stdout"] or "[]")
    except json.JSONDecodeError:
        return [{"error": "gh returned non-json"}]
    return data if isinstance(data, list) else []


def gcp_status(projects: list[dict[str, Any]], *, external: bool) -> list[dict[str, Any]]:
    rows = []
    for project in projects:
        row = {
            "project_id": project.get("project_id"),
            "role": project.get("role"),
            "region": project.get("region"),
            "expected_services": project.get("services", []),
            "cloud_run_services": [],
            "errors": [],
        }
        if external:
            result = run(
                [
                    "gcloud",
                    "run",
                    "services",
                    "list",
                    "--project",
                    str(project.get("project_id")),
                    "--region",
                    str(project.get("region") or "us-central1"),
                    "--format=json",
                ],
                timeout=30,
            )
            if result["ok"]:
                try:
                    row["cloud_run_services"] = [
                        {
                            "name": item.get("metadata", {}).get("name"),
                            "url": item.get("status", {}).get("url"),
                            "latest_ready_revision": item.get("status", {}).get("latestReadyRevisionName"),
                        }
                        for item in json.loads(result["stdout"] or "[]")
                    ]
                except json.JSONDecodeError:
                    row["errors"].append("gcloud returned non-json")
            else:
                row["errors"].append(result["stderr"][:200])
        rows.append(row)
    return rows


def local_runtime_status(config: dict[str, Any], *, external: bool) -> dict[str, Any]:
    return {
        "launchagents": launchagent_status(config.get("launchagents", []), external=external),
        "docker": docker_status(config.get("docker_expected", []), external=external),
    }


def launchagent_status(labels: list[str], *, external: bool) -> list[dict[str, Any]]:
    if not external:
        return [{"label": label, "status": "not_checked"} for label in labels]
    result = run(["launchctl", "list"], timeout=10)
    if not result["ok"]:
        return [{"label": label, "status": "unknown", "error": result["stderr"][:200]} for label in labels]
    parsed = parse_launchctl(result["stdout"])
    rows = []
    for label in labels:
        info = parsed.get(label)
        rows.append({"label": label, **info} if info else {"label": label, "loaded": False})
    return rows


def parse_launchctl(output: str) -> dict[str, dict[str, Any]]:
    agents: dict[str, dict[str, Any]] = {}
    for line in output.splitlines()[1:]:
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid, status, label = parts
        agents[label] = {
            "loaded": True,
            "pid": None if pid == "-" else int(pid),
            "last_status": int(status) if status.lstrip("-").isdigit() else status,
        }
    return agents


def docker_status(expected: list[str], *, external: bool) -> dict[str, Any]:
    if not external:
        return {"checked": False, "expected": expected, "containers": []}
    result = run(["docker", "ps", "--format", "{{json .}}"], timeout=10)
    if not result["ok"]:
        return {"checked": True, "expected": expected, "containers": [], "error": result["stderr"][:200]}
    containers = []
    for line in result["stdout"].splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append({"name": item.get("Names"), "status": item.get("Status"), "ports": item.get("Ports")})
    return {
        "checked": True,
        "expected": expected,
        "containers": containers,
        "missing_expected": sorted(set(expected) - {item["name"] for item in containers}),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Sapphire Autonomous Org Status - {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Repos tracked: {summary['repo_count']}",
        f"- Open PRs: {summary['open_pr_count']}",
        f"- Dirty repos: {', '.join(summary['dirty_repos']) or 'none'}",
        f"- Missing local repos: {', '.join(summary['missing_local_repos']) or 'none'}",
        f"- Routine stages: {json.dumps(summary['routine_stages'], sort_keys=True)}",
        "",
        "## Repos",
        "",
        "| Repo | Class | Branch | Clean | Open PRs | State |",
        "|---|---|---|:---:|---:|---|",
    ]
    for repo in report["repos"]:
        lines.append(
            f"| {repo['id']} | {repo['classification']} | {repo.get('branch') or '-'} | "
            f"{'yes' if repo.get('clean') else 'no'} | {len(repo.get('open_prs', []))} | "
            f"{repo.get('migration_state') or '-'} |"
        )
    lines.extend(["", "## Waves", ""])
    for wave in report.get("waves", []):
        lines.append(f"- **{wave.get('id')}** ({wave.get('status')}): {wave.get('objective')}")
    return "\n".join(lines) + "\n"


def run(args: list[str], *, cwd: Path | None = None, timeout: int = 10) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


if __name__ == "__main__":
    raise SystemExit(main())
