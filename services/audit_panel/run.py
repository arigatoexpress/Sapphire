#!/usr/bin/env python3
"""Read-only weekly audit panel runner backed by the GitHub CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.audit_panel.heuristics import Finding, MergedPR, Review, run_heuristics  # noqa: E402
from lib.audit_panel.reporter import MAX_REPORT_BYTES, render_markdown_report  # noqa: E402
from lib.audit_panel.scorer import score_findings, score_panel, score_pr  # noqa: E402
from lib.core.provenance import write_envelope_sidecar  # noqa: E402

MAX_PRS_PER_RUN = 200
MAX_LIVE_GH_API_CALLS_PER_HOUR = 30
DEFAULT_REPO = "arigatoexpress/Sapphire"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "audit_panel"
ROLLING_SUMMARY_TITLE = "Sapphire audit-panel rolling summary"
AUDIT_LABEL = "audit-panel"


@dataclass(frozen=True)
class PanelRunResult:
    report_path: str
    json_path: str
    envelope_path: str
    issue_action: str
    issue_url: str | None
    pr_count: int
    finding_count: int
    histogram: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GhClient:
    """Small subprocess wrapper that tracks live gh call count."""

    def __init__(
        self,
        *,
        repo: str = DEFAULT_REPO,
        max_calls: int = MAX_LIVE_GH_API_CALLS_PER_HOUR,
        runner: Any = subprocess.run,
    ) -> None:
        self.repo = repo
        self.max_calls = max_calls
        self.runner = runner
        self.calls = 0

    def run(self, args: list[str], *, timeout: int = 20) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError("MAX_LIVE_GH_API_CALLS_PER_HOUR exceeded")
        self.calls += 1
        result = self.runner(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "gh command failed").strip())
        return result.stdout

    def json(self, args: list[str], *, timeout: int = 20) -> Any:
        out = self.run(args, timeout=timeout)
        return json.loads(out or "null")


def _parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def weekly_window(now: datetime | None = None, *, days: int = 7) -> tuple[datetime, str]:
    anchor = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    start = anchor - timedelta(days=days)
    return start, start.date().isoformat()


def _author_login(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("login") or "")
    return str(payload or "")


def _status_conclusion(payload: dict[str, Any]) -> str | None:
    rollup = payload.get("statusCheckRollup") or []
    if not isinstance(rollup, list) or not rollup:
        return None
    conclusions = []
    for item in rollup:
        if not isinstance(item, dict):
            continue
        conclusion = item.get("conclusion") or item.get("state") or item.get("status")
        if conclusion:
            conclusions.append(str(conclusion).upper())
    if any(value in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED"} for value in conclusions):
        return "FAILURE"
    if any(value in {"PENDING", "IN_PROGRESS", "QUEUED"} for value in conclusions):
        return "PENDING"
    if any(value in {"SUCCESS", "COMPLETED"} for value in conclusions):
        return "SUCCESS"
    return None


def _commit_subjects(payload: dict[str, Any]) -> tuple[str, ...]:
    commits = payload.get("commits") or []
    subjects: list[str] = []
    if isinstance(commits, list):
        for item in commits:
            if not isinstance(item, dict):
                continue
            message = str(item.get("messageHeadline") or item.get("message") or "")
            if message.strip():
                subjects.append(message.splitlines()[0][:180])
    return tuple(subjects)


def _file_paths(payload: dict[str, Any]) -> tuple[str, ...]:
    files = payload.get("files") or []
    paths: list[str] = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item["path"]))
            elif isinstance(item, str):
                paths.append(item)
    return tuple(paths)


def pr_from_gh_payload(payload: dict[str, Any]) -> MergedPR:
    merge_commit = payload.get("mergeCommit") or {}
    additions = sum(int(item.get("additions") or 0) for item in payload.get("files", []) if isinstance(item, dict))
    deletions = sum(int(item.get("deletions") or 0) for item in payload.get("files", []) if isinstance(item, dict))
    labels = tuple(
        str(item.get("name"))
        for item in payload.get("labels", []) or []
        if isinstance(item, dict) and item.get("name")
    )
    return MergedPR(
        number=int(payload.get("number") or 0),
        title=str(payload.get("title") or ""),
        url=str(payload.get("url") or ""),
        author=_author_login(payload.get("author")),
        merged_at=str(payload.get("mergedAt") or ""),
        merge_commit=str(merge_commit.get("oid") or payload.get("mergeCommitOid") or ""),
        additions=additions or int(payload.get("additions") or 0),
        deletions=deletions or int(payload.get("deletions") or 0),
        changed_files=_file_paths(payload),
        commits=_commit_subjects(payload),
        reviews=tuple(
            Review.from_dict(item)
            for item in payload.get("reviews", []) or []
            if isinstance(item, dict)
        ),
        status_conclusion=_status_conclusion(payload),
        diff_snippets=tuple(str(item) for item in payload.get("diff_snippets", []) or []),
        labels=labels,
    )


def collect_merged_prs(
    *,
    repo: str = DEFAULT_REPO,
    since: str | None = None,
    limit: int = MAX_PRS_PER_RUN,
    gh: GhClient | None = None,
) -> tuple[MergedPR, ...]:
    client = gh or GhClient(repo=repo)
    capped = max(0, min(int(limit), MAX_PRS_PER_RUN))
    if not since:
        _, since = weekly_window()
    summaries = client.json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--search",
            f"merged:>={since}",
            "--limit",
            str(capped),
            "--json",
            "number,title,url,author,mergedAt,labels",
        ],
        timeout=20,
    )
    if not isinstance(summaries, list):
        return ()
    remaining_detail_calls = max(0, client.max_calls - client.calls)
    prs: list[MergedPR] = []
    fields = (
        "number,title,url,author,mergedAt,mergeCommit,files,commits,reviews,"
        "statusCheckRollup,labels"
    )
    for summary in summaries[:remaining_detail_calls]:
        if not isinstance(summary, dict):
            continue
        number = int(summary.get("number") or 0)
        detail = client.json(
            ["pr", "view", str(number), "--repo", repo, "--json", fields],
            timeout=20,
        )
        if isinstance(detail, dict):
            prs.append(pr_from_gh_payload({**summary, **detail}))
    return tuple(prs)


def run_panel(
    *,
    repo: str = DEFAULT_REPO,
    since: str | None = None,
    limit: int = MAX_PRS_PER_RUN,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    gh: GhClient | None = None,
    open_issue: bool = True,
    now: datetime | None = None,
) -> PanelRunResult:
    start, default_since = weekly_window(now)
    since = since or default_since
    prs = collect_merged_prs(repo=repo, since=since, limit=limit, gh=gh)
    findings_by_pr = {pr.number: run_heuristics(pr) for pr in prs}
    findings = tuple(finding for items in findings_by_pr.values() for finding in items)
    histogram = score_panel(prs)
    generated = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat()
    report = render_markdown_report(prs, generated_at=generated, source=f"gh:{repo}")

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    stamp = start.date().isoformat()
    report_path = cache / f"audit-panel-{stamp}.md"
    json_path = cache / f"audit-panel-{stamp}.json"
    report_path.write_text(report, encoding="utf-8")
    payload = {
        "generated_at": generated,
        "repo": repo,
        "since": since,
        "prs": [pr.to_dict() for pr in prs],
        "findings": [finding.to_dict() for finding in findings],
        "scores": [
            score_findings(number, pr_findings).to_dict()
            for number, pr_findings in findings_by_pr.items()
        ],
        "histogram": histogram.to_dict(),
        "caps": {
            "MAX_PRS_PER_RUN": MAX_PRS_PER_RUN,
            "MAX_REPORT_BYTES": MAX_REPORT_BYTES,
            "MAX_LIVE_GH_API_CALLS_PER_HOUR": MAX_LIVE_GH_API_CALLS_PER_HOUR,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    envelope_path = write_envelope_sidecar(
        json_path,
        generator="services.audit_panel.run",
        source_paths=("lib/audit_panel/heuristics.py", "lib/audit_panel/scorer.py"),
        metadata={"repo": repo, "since": since, "pr_count": len(prs)},
    )
    issue_action, issue_url = maybe_publish_issue(
        report=report,
        findings=findings,
        repo=repo,
        gh=gh,
        enabled=open_issue,
    )
    return PanelRunResult(
        report_path=str(report_path),
        json_path=str(json_path),
        envelope_path=str(envelope_path),
        issue_action=issue_action,
        issue_url=issue_url,
        pr_count=len(prs),
        finding_count=len(findings),
        histogram=histogram.to_dict(),
    )


def maybe_publish_issue(
    *,
    report: str,
    findings: tuple[Finding, ...],
    repo: str,
    gh: GhClient | None = None,
    enabled: bool = True,
) -> tuple[str, str | None]:
    if not enabled:
        return "skipped", None
    client = gh or GhClient(repo=repo)
    severe = [finding for finding in findings if finding.severity in {"critical", "high"}]
    title = (
        f"Sapphire audit-panel findings: {len(severe)} high-or-critical"
        if severe
        else ROLLING_SUMMARY_TITLE
    )
    body = report[:MAX_REPORT_BYTES]
    try:
        if severe:
            url = client.run(
                [
                    "issue",
                    "create",
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--body",
                    body,
                    "--label",
                    AUDIT_LABEL,
                ],
                timeout=20,
            ).strip()
            return "created_findings_issue", url
        existing = client.json(
            [
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--label",
                AUDIT_LABEL,
                "--search",
                ROLLING_SUMMARY_TITLE,
                "--json",
                "number,url,title",
                "--limit",
                "10",
            ],
            timeout=20,
        )
        match = next(
            (
                item
                for item in existing or []
                if isinstance(item, dict) and item.get("title") == ROLLING_SUMMARY_TITLE
            ),
            None,
        )
        if match:
            number = str(match["number"])
            client.run(["issue", "comment", number, "--repo", repo, "--body", body], timeout=20)
            return "commented_rolling_summary", str(match.get("url") or "")
        url = client.run(
            [
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                ROLLING_SUMMARY_TITLE,
                "--body",
                body,
                "--label",
                AUDIT_LABEL,
            ],
            timeout=20,
        ).strip()
        return "created_rolling_summary", url
    except Exception as exc:  # pragma: no cover - defensive path is still reported to callers.
        return f"publish_failed:{type(exc).__name__}", None


def latest_report(cache_dir: Path | str = DEFAULT_CACHE_DIR) -> dict[str, Any]:
    cache = Path(cache_dir)
    reports = sorted(cache.glob("audit-panel-*.json"))
    if not reports:
        return {"error": "no audit-panel report found", "cache_dir": str(cache)}
    path = reports[-1]
    return {"path": str(path), "report": json.loads(path.read_text(encoding="utf-8"))}


def pr_score(payload: dict[str, Any]) -> dict[str, Any]:
    pr = MergedPR.from_dict(payload)
    return score_pr(pr).to_dict()


def histogram_from_payload(prs: list[dict[str, Any]]) -> dict[str, Any]:
    return score_panel(MergedPR.from_dict(item) for item in prs).to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("SAPPHIRE_AUDIT_PANEL_REPO", DEFAULT_REPO))
    parser.add_argument("--since", default=None)
    parser.add_argument("--limit", type=int, default=MAX_PRS_PER_RUN)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--no-issue", action="store_true", help="do not create/comment GitHub issues")
    args = parser.parse_args(argv)
    result = run_panel(
        repo=args.repo,
        since=args.since,
        limit=args.limit,
        cache_dir=args.cache_dir,
        open_issue=not args.no_issue,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
