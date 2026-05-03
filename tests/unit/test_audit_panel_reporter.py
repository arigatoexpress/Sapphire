"""Tests for paste-safe audit-panel reporting."""

from __future__ import annotations

from lib.audit_panel.heuristics import MergedPR
from lib.audit_panel.reporter import render_markdown_report


def test_report_includes_header_and_histogram():
    report = render_markdown_report(
        [MergedPR(1, "feat: clean [skip ci]", commits=("feat: clean [skip ci]",))],
        generated_at="2026-04-28T00:00:00+00:00",
    )

    assert "# Sapphire Multi-Agent Audit Panel" in report
    assert "## Histogram" in report
    assert "PRs audited: `1`" in report


def test_report_says_no_findings_when_clean():
    report = render_markdown_report(
        [MergedPR(1, "feat: clean [skip ci]", commits=("feat: clean [skip ci]",))]
    )

    assert "No findings" in report


def test_report_groups_critical_findings():
    report = render_markdown_report(
        [
            MergedPR(
                2,
                "fix: safety [skip ci]",
                changed_files=("lib/core/kill_switch.py",),
                commits=("fix: safety [skip ci]",),
            )
        ]
    )

    assert "## Critical" in report
    assert "kill_switch_touched_without_review" in report


def test_report_groups_medium_findings():
    report = render_markdown_report([MergedPR(2, "feat: no token", commits=("feat: no token",))])

    assert "## Medium" in report
    assert "ci_skip_dropped" in report


def test_report_redacts_secret_evidence():
    report = render_markdown_report(
        [
            MergedPR(
                3,
                "fix: config [skip ci]",
                commits=("fix: config [skip ci]",),
                diff_snippets=("api_key=sk-abcdefghijklmnopqrstuvwxyz",),
            )
        ]
    )

    assert "sk-abcdefghijklmnopqrstuvwxyz" not in report
    assert "secret_signature" in report


def test_report_does_not_include_full_pr_body_field():
    long_text = "body " * 1000
    report = render_markdown_report(
        [MergedPR(4, long_text + " [skip ci]", commits=("feat: body [skip ci]",))]
    )

    assert len(report) < len(long_text)


def test_report_lists_audited_pr_metadata():
    report = render_markdown_report(
        [
            MergedPR(
                5,
                "feat: audit [skip ci]",
                merge_commit="abcdef1234567890",
                additions=2,
                deletions=3,
                changed_files=("lib/audit_panel/a.py",),
                commits=("feat: audit [skip ci]",),
            )
        ]
    )

    assert "#5 `abcdef123456`" in report
    assert "1 files, 5 lines" in report


def test_report_truncates_at_byte_limit():
    prs = [MergedPR(i, "feat: missing skip", commits=("feat: missing skip",)) for i in range(100)]

    report = render_markdown_report(prs, max_bytes=1200)

    assert len(report.encode("utf-8")) <= 1300
    assert "Report truncated" in report


def test_report_uses_supplied_source():
    report = render_markdown_report([], source="test-source")

    assert "Source: `test-source`" in report


def test_report_handles_empty_pr_list():
    report = render_markdown_report([])

    assert "PRs audited: `0`" in report
    assert "Findings: `0`" in report


def test_report_limits_evidence_count():
    pr = MergedPR(
        6,
        "feat: artifacts [skip ci]",
        commits=("feat: artifacts [skip ci]",),
        changed_files=tuple(f"data/x/{i}.json" for i in range(20)),
    )

    report = render_markdown_report([pr])

    assert report.count("Evidence:") <= 3


def test_report_is_paste_safe_statement_present():
    report = render_markdown_report([])

    assert "paste-safe" in report
    assert "full diffs" in report
