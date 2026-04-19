#!/usr/bin/env python3
"""Report Sapphire worktree and Claude-session fragmentation.

This is a read-only helper for consolidation work. It inventories:

- Git worktrees attached to the Sapphire repo
- Local Claude branches and how far they diverge from ``main``
- Claude desktop project/session traces under ``~/.claude/projects``

It does not modify git state, prune worktrees, or delete session metadata.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPO = Path.home() / "Code" / "Sapphire"
DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


@dataclass
class WorktreeRecord:
    path: str
    branch: str
    head: str
    ahead: int
    behind: int
    dirty_count: int
    prunable: bool
    locked: bool
    updated_at: str


@dataclass
class BranchRecord:
    branch: str
    head: str
    ahead: int
    behind: int
    attached_path: str | None
    updated_at: str


@dataclass
class ClaudeSessionRecord:
    project_dir: str
    branch: str
    latest_file: str
    updated_at: str
    last_prompt: str


def run_cmd(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def sanitize_project_prefix(path: Path) -> str:
    return str(path).replace("/", "-")


def iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return ""


def short_head(repo: Path, ref: str) -> str:
    return run_cmd(["git", "rev-parse", "--short", ref], repo)


def rev_count(repo: Path, left: str, right: str) -> int:
    value = run_cmd(["git", "rev-list", "--count", f"{left}..{right}"], repo)
    try:
        return int(value)
    except ValueError:
        return 0


def parse_worktrees(repo: Path, main_branch: str) -> list[WorktreeRecord]:
    raw = run_cmd(["git", "worktree", "list", "--porcelain"], repo)
    records: list[WorktreeRecord] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if not current.get("worktree"):
            return
        wt_path = Path(current["worktree"])
        branch_ref = current.get("branch", "")
        branch = branch_ref.removeprefix("refs/heads/")
        if current.get("detached") == "true":
            branch = "(detached)"
        head = current.get("HEAD", "")[:8]
        if wt_path.exists():
            dirty_raw = run_cmd(["git", "status", "--short"], wt_path)
            dirty_count = len([line for line in dirty_raw.splitlines() if line.strip()])
            updated_at = iso_mtime(wt_path)
        else:
            dirty_count = 0
            updated_at = ""
        ahead = rev_count(repo, main_branch, branch) if branch and not branch.startswith("(") else 0
        behind = rev_count(repo, branch, main_branch) if branch and not branch.startswith("(") else 0
        records.append(
            WorktreeRecord(
                path=str(wt_path),
                branch=branch or "(unknown)",
                head=head,
                ahead=ahead,
                behind=behind,
                dirty_count=dirty_count,
                prunable="prunable" in current,
                locked="locked" in current,
                updated_at=updated_at,
            )
        )

    for line in raw.splitlines():
        if not line.strip():
            flush()
            current = {}
            continue
        if " " in line:
            key, value = line.split(" ", 1)
            current[key] = value
        else:
            current[line] = "true"
    flush()
    return records


def collect_branches(repo: Path, main_branch: str, worktrees: list[WorktreeRecord]) -> list[BranchRecord]:
    attached = {wt.branch: wt.path for wt in worktrees if wt.branch and not wt.branch.startswith("(")}
    branches = run_cmd(["git", "for-each-ref", "refs/heads", "--format=%(refname:short)"], repo)
    records: list[BranchRecord] = []

    for branch in branches.splitlines():
        branch = branch.strip()
        if not branch or branch == main_branch:
            continue
        ahead = rev_count(repo, main_branch, branch)
        behind = rev_count(repo, branch, main_branch)
        if ahead == 0 and behind == 0 and branch not in attached:
            continue
        records.append(
            BranchRecord(
                branch=branch,
                head=short_head(repo, branch),
                ahead=ahead,
                behind=behind,
                attached_path=attached.get(branch),
                updated_at=run_cmd(
                    ["git", "log", "-1", "--format=%aI", branch],
                    repo,
                ),
            )
        )
    return sorted(records, key=lambda item: (-item.ahead, -item.behind, item.branch))


def extract_last_prompt(jsonl_path: Path) -> tuple[str, str]:
    last_prompt = ""
    branch = ""
    try:
        for line in jsonl_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not branch:
                branch = str(payload.get("gitBranch") or "")
            if payload.get("type") == "last-prompt":
                last_prompt = str(payload.get("lastPrompt") or "")
            elif payload.get("type") == "user":
                message = payload.get("message") or {}
                content = message.get("content")
                if isinstance(content, str):
                    last_prompt = content
    except OSError:
        return "", ""
    return branch, " ".join(last_prompt.split())


def collect_claude_sessions(repo: Path, projects_root: Path) -> list[ClaudeSessionRecord]:
    prefix = sanitize_project_prefix(repo)
    sessions: list[ClaudeSessionRecord] = []
    for project_dir in sorted(projects_root.glob(f"{prefix}*")):
        jsonl_files = sorted(project_dir.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not jsonl_files:
            continue
        latest = jsonl_files[0]
        branch, last_prompt = extract_last_prompt(latest)
        sessions.append(
            ClaudeSessionRecord(
                project_dir=str(project_dir),
                branch=branch or infer_branch_from_project_dir(project_dir.name),
                latest_file=str(latest),
                updated_at=iso_mtime(latest),
                last_prompt=truncate(last_prompt, 180),
            )
        )
    return sorted(sessions, key=lambda item: item.updated_at, reverse=True)


def infer_branch_from_project_dir(name: str) -> str:
    marker = "--claude-worktrees-"
    if marker in name:
        return "claude/" + name.split(marker, 1)[1]
    return "main"


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def recommend_actions(worktrees: list[WorktreeRecord], branches: list[BranchRecord]) -> dict[str, list[str]]:
    merge_candidates = [
        f"{branch.branch} (ahead {branch.ahead}, behind {branch.behind})"
        for branch in branches
        if branch.ahead > 0
    ]
    prune_candidates = [
        f"{Path(wt.path).name} [{wt.branch}]"
        for wt in worktrees
        if wt.branch != "main" and wt.ahead == 0 and wt.dirty_count == 0
    ]
    dirty_review = [
        f"{Path(wt.path).name} [{wt.branch}] changes={wt.dirty_count}"
        for wt in worktrees
        if wt.dirty_count > 0 and wt.branch != "main"
    ]
    return {
        "merge_candidates": merge_candidates,
        "prune_candidates": prune_candidates,
        "dirty_review": dirty_review,
    }


def render_markdown(
    repo: Path,
    main_branch: str,
    repo_status_count: int,
    worktrees: list[WorktreeRecord],
    branches: list[BranchRecord],
    sessions: list[ClaudeSessionRecord],
    recommendations: dict[str, list[str]],
) -> str:
    lines: list[str] = []
    lines.append(f"# Sapphire Consolidation Report — {datetime.now(UTC).date().isoformat()}")
    lines.append("")
    lines.append(f"- Repo: `{repo}`")
    lines.append(f"- Main branch baseline: `{main_branch}`")
    lines.append(f"- Main working tree changes: `{repo_status_count}`")
    lines.append(f"- Attached worktrees: `{len(worktrees)}`")
    lines.append(f"- Diverged local branches: `{len(branches)}`")
    lines.append(f"- Claude project traces: `{len(sessions)}`")
    lines.append("")
    lines.append("## Worktrees")
    lines.append("")
    lines.append("| Worktree | Branch | Ahead | Behind | Dirty | Updated |")
    lines.append("|---|---|---:|---:|---:|---|")
    for wt in worktrees:
        label = Path(wt.path).name
        lines.append(
            f"| `{label}` | `{wt.branch}` | {wt.ahead} | {wt.behind} | {wt.dirty_count} | `{wt.updated_at}` |"
        )
    lines.append("")
    lines.append("## Diverged Branches")
    lines.append("")
    lines.append("| Branch | Head | Ahead | Behind | Attached Worktree | Updated |")
    lines.append("|---|---|---:|---:|---|---|")
    for branch in branches:
        attached = Path(branch.attached_path).name if branch.attached_path else "—"
        lines.append(
            f"| `{branch.branch}` | `{branch.head}` | {branch.ahead} | {branch.behind} | `{attached}` | `{branch.updated_at}` |"
        )
    lines.append("")
    lines.append("## Recent Claude Sessions")
    lines.append("")
    lines.append("| Branch | Updated | Last Prompt |")
    lines.append("|---|---|---|")
    for session in sessions[:12]:
        lines.append(
            f"| `{session.branch or 'unknown'}` | `{session.updated_at}` | {session.last_prompt or '—'} |"
        )
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")
    lines.append("### Merge candidates")
    if recommendations["merge_candidates"]:
        lines.extend([f"- {item}" for item in recommendations["merge_candidates"]])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("### Prune candidates")
    if recommendations["prune_candidates"]:
        lines.extend([f"- {item}" for item in recommendations["prune_candidates"]])
    else:
        lines.append("- None")
    lines.append("")
    lines.append("### Dirty worktrees to review first")
    if recommendations["dirty_review"]:
        lines.extend([f"- {item}" for item in recommendations["dirty_review"]])
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def build_report(repo: Path, projects_root: Path, main_branch: str) -> dict[str, Any]:
    worktrees = parse_worktrees(repo, main_branch)
    branches = collect_branches(repo, main_branch, worktrees)
    sessions = collect_claude_sessions(repo, projects_root)
    repo_status_count = len(
        [
            line
            for line in run_cmd(["git", "status", "--short"], repo).splitlines()
            if line.strip()
        ]
    )
    recommendations = recommend_actions(worktrees, branches)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo": str(repo),
        "main_branch": main_branch,
        "repo_status_count": repo_status_count,
        "worktrees": [record.__dict__ for record in worktrees],
        "branches": [record.__dict__ for record in branches],
        "sessions": [record.__dict__ for record in sessions],
        "recommendations": recommendations,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT)
    parser.add_argument("--main-branch", default="main")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.repo.expanduser(), args.projects_root.expanduser(), args.main_branch)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(
            render_markdown(
                repo=Path(report["repo"]),
                main_branch=str(report["main_branch"]),
                repo_status_count=int(report["repo_status_count"]),
                worktrees=[WorktreeRecord(**record) for record in report["worktrees"]],
                branches=[BranchRecord(**record) for record in report["branches"]],
                sessions=[ClaudeSessionRecord(**record) for record in report["sessions"]],
                recommendations=report["recommendations"],
            ),
            end="",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
