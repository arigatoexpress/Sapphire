"""Paste-safe Markdown reporter for audit panel runs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

from .heuristics import Finding, MergedPR, run_heuristics
from .scorer import RiskScore, score_findings, score_panel

MAX_REPORT_BYTES = 50_000
SECTION_ORDER = ("critical", "high", "medium", "low", "info")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe(text: str, *, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    compact = re.sub(
        r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*\S+", r"\1=[redacted]", compact
    )
    return compact[:limit]


def _format_finding(finding: Finding, score: RiskScore | None = None) -> str:
    score_text = f" score={score.score:.2f}" if score else ""
    lines = [
        f"- PR #{finding.pr_number}: `{finding.rule_id}` ({finding.severity}, confidence={finding.confidence:.2f}{score_text})",
        f"  - Summary: {_safe(finding.summary)}",
    ]
    for item in finding.evidence[:3]:
        lines.append(f"  - Evidence: {_safe(item)}")
    lines.append(f"  - Action: `{_safe(finding.recommended_action, limit=120)}`")
    return "\n".join(lines)


def render_markdown_report(
    prs: Iterable[MergedPR],
    *,
    generated_at: str | None = None,
    source: str = "audit-panel",
    max_bytes: int = MAX_REPORT_BYTES,
) -> str:
    """Render a paste-safe Markdown report without full diffs or PR bodies."""
    materialized = tuple(prs)
    findings_by_pr = {pr.number: run_heuristics(pr) for pr in materialized}
    scores = {
        pr_number: score_findings(pr_number, pr_findings)
        for pr_number, pr_findings in findings_by_pr.items()
    }
    findings = tuple(finding for items in findings_by_pr.values() for finding in items)
    histogram = score_panel(materialized)
    generated = generated_at or _now_iso()

    lines = [
        "# Sapphire Multi-Agent Audit Panel",
        "",
        f"- Generated: `{generated}`",
        f"- Source: `{source}`",
        f"- PRs audited: `{histogram.pr_count}`",
        f"- Findings: `{histogram.finding_count}`",
        f"- Clean PRs: `{histogram.clean_count}`",
        f"- Max risk score: `{histogram.max_score:.2f}`",
        f"- Average risk score: `{histogram.average_score:.2f}`",
        "",
        "This report is paste-safe: it lists metadata, paths, and summarized evidence only. It does not include full diffs, PR bodies, or secret values.",
        "",
        "## Histogram",
        "",
        f"- Critical: `{histogram.critical}`",
        f"- High: `{histogram.high}`",
        f"- Medium: `{histogram.medium}`",
        f"- Low: `{histogram.low}`",
        "",
    ]
    if not findings:
        lines.extend(["## Findings", "", "No findings for the audited window."])
    else:
        for severity in SECTION_ORDER:
            section = [finding for finding in findings if finding.severity == severity]
            if not section:
                continue
            lines.extend([f"## {severity.title()}", ""])
            section.sort(key=lambda item: (item.pr_number, item.rule_id))
            for finding in section:
                lines.append(_format_finding(finding, scores.get(finding.pr_number)))
            lines.append("")

    lines.extend(["## Audited PRs", ""])
    for pr in materialized[:200]:
        title = _safe(pr.title, limit=120)
        sha = _safe(pr.merge_commit[:12] or "unknown", limit=20)
        lines.append(
            f"- #{pr.number} `{sha}` {title} "
            f"({len(pr.changed_files)} files, {pr.lines_changed} lines)"
        )

    report = "\n".join(lines).rstrip() + "\n"
    encoded = report.encode("utf-8")
    if len(encoded) <= max_bytes:
        return report
    suffix = "\n\n_Report truncated at MAX_REPORT_BYTES; see the JSON sidecar for full structured findings._\n"
    room = max(0, max_bytes - len(suffix.encode("utf-8")))
    return encoded[:room].decode("utf-8", errors="ignore").rstrip() + suffix
