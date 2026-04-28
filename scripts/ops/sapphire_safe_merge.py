#!/usr/bin/env python3
"""Squash-merge Sapphire PRs without losing the no-spend `[skip ci]` guard."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_REPO = "arigatoexpress/Sapphire"
RUN_FIELDS = "databaseId,status,headSha,headBranch,displayTitle,event"
PR_FIELDS = "title,headRefName,headRefOid"
ACTIVE_RUN_STATUSES = {"queued", "in_progress"}
SKIP_CI_RE = re.compile(r"\[\s*skip\s+ci\s*\]", re.IGNORECASE)


class SafeMergeError(RuntimeError):
    """Raised when a safe-merge precondition or gh command fails."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    title: str
    head_ref_name: str
    head_ref_oid: str


@dataclass(frozen=True)
class SafeMergeResult:
    pr_number: int
    subject: str
    cancelled_runs: tuple[int, ...]
    dry_run: bool = False


Runner = Callable[[list[str]], CommandResult]


def subprocess_runner(cmd: list[str]) -> CommandResult:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_pr_number(raw: str | int) -> int:
    text = str(raw).strip()
    if not text.isdecimal():
        raise SafeMergeError(f"bad PR number: {raw!r}")
    number = int(text)
    if number <= 0:
        raise SafeMergeError(f"bad PR number: {raw!r}")
    return number


def build_subject(title: str) -> str:
    normalized = " ".join(str(title or "").split())
    if not normalized:
        raise SafeMergeError("PR title is empty")
    if SKIP_CI_RE.search(normalized):
        return normalized
    return f"{normalized} [skip ci]"


def _run(cmd: list[str], *, runner: Runner, purpose: str) -> CommandResult:
    result = runner(cmd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SafeMergeError(f"{purpose} failed: {detail or 'gh returned non-zero'}")
    return result


def _load_json(stdout: str, *, purpose: str) -> Any:
    try:
        return json.loads(stdout or "null")
    except json.JSONDecodeError as exc:
        raise SafeMergeError(f"{purpose} returned invalid JSON") from exc


def fetch_pr_info(
    pr_number: int,
    *,
    repo: str = DEFAULT_REPO,
    runner: Runner = subprocess_runner,
) -> PullRequestInfo:
    result = _run(
        ["gh", "-R", repo, "pr", "view", str(pr_number), "--json", PR_FIELDS],
        runner=runner,
        purpose="gh pr view",
    )
    payload = _load_json(result.stdout, purpose="gh pr view")
    if not isinstance(payload, dict):
        raise SafeMergeError("gh pr view returned a non-object payload")
    title = str(payload.get("title") or "").strip()
    head_ref_name = str(payload.get("headRefName") or "").strip()
    head_ref_oid = str(payload.get("headRefOid") or "").strip()
    if not title or not head_ref_name or not head_ref_oid:
        raise SafeMergeError("gh pr view did not return title/head ref metadata")
    return PullRequestInfo(
        number=pr_number,
        title=title,
        head_ref_name=head_ref_name,
        head_ref_oid=head_ref_oid,
    )


def run_matches_pr(run: dict[str, Any], *, pr: PullRequestInfo, subject: str) -> bool:
    if str(run.get("status") or "") not in ACTIVE_RUN_STATUSES:
        return False
    head_sha = str(run.get("headSha") or "")
    head_branch = str(run.get("headBranch") or "")
    display_title = str(run.get("displayTitle") or "")
    if head_sha and head_sha == pr.head_ref_oid:
        return True
    if head_branch and head_branch == pr.head_ref_name:
        return True
    return display_title == subject and head_branch in {"main", "master"}


def active_runs_for_pr(
    *,
    pr: PullRequestInfo,
    subject: str,
    repo: str = DEFAULT_REPO,
    runner: Runner = subprocess_runner,
    limit: int = 20,
) -> list[dict[str, Any]]:
    result = _run(
        [
            "gh",
            "-R",
            repo,
            "run",
            "list",
            "--limit",
            str(limit),
            "--json",
            RUN_FIELDS,
        ],
        runner=runner,
        purpose="gh run list",
    )
    payload = _load_json(result.stdout, purpose="gh run list")
    if not isinstance(payload, list):
        raise SafeMergeError("gh run list returned a non-list payload")
    return [run for run in payload if isinstance(run, dict) and run_matches_pr(run, pr=pr, subject=subject)]


def cancel_runs(
    runs: list[dict[str, Any]],
    *,
    repo: str = DEFAULT_REPO,
    runner: Runner = subprocess_runner,
) -> tuple[int, ...]:
    cancelled: list[int] = []
    for run in runs:
        raw_id = run.get("databaseId")
        try:
            run_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        _run(
            ["gh", "-R", repo, "run", "cancel", str(run_id)],
            runner=runner,
            purpose=f"gh run cancel {run_id}",
        )
        cancelled.append(run_id)
    return tuple(cancelled)


def safe_merge(
    raw_pr_number: str | int,
    *,
    repo: str = DEFAULT_REPO,
    runner: Runner = subprocess_runner,
    dry_run: bool = False,
) -> SafeMergeResult:
    pr_number = parse_pr_number(raw_pr_number)
    pr = fetch_pr_info(pr_number, repo=repo, runner=runner)
    subject = build_subject(pr.title)
    if dry_run:
        return SafeMergeResult(pr_number=pr.number, subject=subject, cancelled_runs=(), dry_run=True)
    _run(
        [
            "gh",
            "-R",
            repo,
            "pr",
            "merge",
            str(pr.number),
            "--squash",
            "--admin",
            "--delete-branch",
            "-t",
            subject,
        ],
        runner=runner,
        purpose="gh pr merge",
    )
    runs = active_runs_for_pr(pr=pr, subject=subject, repo=repo, runner=runner)
    cancelled = cancel_runs(runs, repo=repo, runner=runner)
    return SafeMergeResult(pr_number=pr.number, subject=subject, cancelled_runs=cancelled)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="Pull request number to squash-merge.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo, default: {DEFAULT_REPO}")
    parser.add_argument("--dry-run", action="store_true", help="Resolve subject without merging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        result = safe_merge(args.pr, repo=args.repo, dry_run=args.dry_run)
    except SafeMergeError as exc:
        print(f"safe-merge error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "pr_number": result.pr_number,
                "subject": result.subject,
                "cancelled_runs": list(result.cancelled_runs),
                "dry_run": result.dry_run,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
