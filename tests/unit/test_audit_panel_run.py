"""Tests for the audit-panel service runner with mocked gh I/O."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from services.audit_panel import run as audit_run


class FakeGh(audit_run.GhClient):
    def __init__(self, responses):
        super().__init__(repo="arigatoexpress/Sapphire", runner=None)
        self.responses = list(responses)
        self.commands = []

    def run(self, args, *, timeout=20):
        self.calls += 1
        self.commands.append(args)
        if not self.responses:
            return ""
        value = self.responses.pop(0)
        return json.dumps(value) if isinstance(value, (dict, list)) else str(value)


def test_weekly_window_uses_seven_day_lookback():
    start, text = audit_run.weekly_window(datetime(2026, 4, 28, tzinfo=UTC))

    assert text == "2026-04-21"
    assert start.tzinfo == UTC


def test_pr_from_gh_payload_maps_nested_fields():
    payload = {
        "number": 1,
        "title": "feat: audit [skip ci]",
        "author": {"login": "codex"},
        "mergeCommit": {"oid": "abc"},
        "files": [{"path": "lib/a.py", "additions": 2, "deletions": 3}],
        "commits": [{"messageHeadline": "feat: audit [skip ci]"}],
        "reviews": [{"author": {"login": "arigatoexpress"}, "state": "APPROVED"}],
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    }

    pr = audit_run.pr_from_gh_payload(payload)

    assert pr.number == 1
    assert pr.merge_commit == "abc"
    assert pr.changed_files == ("lib/a.py",)
    assert pr.lines_changed == 5
    assert pr.status_conclusion == "SUCCESS"


def test_collect_merged_prs_calls_list_then_detail():
    fake = FakeGh(
        [
            [{"number": 7, "title": "feat: audit [skip ci]"}],
            {
                "number": 7,
                "title": "feat: audit [skip ci]",
                "files": [],
                "commits": [{"messageHeadline": "feat: audit [skip ci]"}],
            },
        ]
    )

    prs = audit_run.collect_merged_prs(since="2026-04-21", gh=fake)

    assert len(prs) == 1
    assert fake.commands[0][:2] == ["pr", "list"]
    assert fake.commands[1][:2] == ["pr", "view"]


def test_collect_merged_prs_respects_call_cap():
    fake = FakeGh([[{"number": i, "title": "feat: audit [skip ci]"} for i in range(40)]])
    fake.max_calls = 1

    prs = audit_run.collect_merged_prs(since="2026-04-21", gh=fake)

    assert prs == ()


def test_run_panel_writes_report_json_and_envelope(tmp_path):
    fake = FakeGh(
        [
            [{"number": 7, "title": "feat: audit"}],
            {
                "number": 7,
                "title": "feat: audit",
                "files": [],
                "commits": [{"messageHeadline": "feat: audit"}],
            },
        ]
    )

    result = audit_run.run_panel(
        cache_dir=tmp_path, gh=fake, open_issue=False, now=datetime(2026, 4, 28, tzinfo=UTC)
    )

    assert result.pr_count == 1
    assert result.finding_count >= 1
    assert (tmp_path / "audit-panel-2026-04-21.md").exists()
    assert (tmp_path / "audit-panel-2026-04-21.json").exists()
    assert (tmp_path / "audit-panel-2026-04-21.json.envelope.json").exists()


def test_run_panel_issue_disabled_is_skipped(tmp_path):
    fake = FakeGh(
        [
            [],
        ]
    )

    result = audit_run.run_panel(
        cache_dir=tmp_path, gh=fake, open_issue=False, now=datetime(2026, 4, 28, tzinfo=UTC)
    )

    assert result.issue_action == "skipped"


def test_maybe_publish_issue_creates_findings_issue_for_high():
    finding = audit_run.Finding("x", "high", 1.0, "summary", 1, "title")
    fake = FakeGh(["https://github.com/arigatoexpress/Sapphire/issues/1"])

    action, url = audit_run.maybe_publish_issue(
        report="body", findings=(finding,), repo="arigatoexpress/Sapphire", gh=fake
    )

    assert action == "created_findings_issue"
    assert url.endswith("/1")


def test_maybe_publish_issue_comments_on_existing_rolling_summary():
    fake = FakeGh(
        [
            [
                {
                    "number": 2,
                    "url": "https://github.com/x/2",
                    "title": audit_run.ROLLING_SUMMARY_TITLE,
                }
            ],
            "",
        ]
    )

    action, url = audit_run.maybe_publish_issue(
        report="body", findings=(), repo="arigatoexpress/Sapphire", gh=fake
    )

    assert action == "commented_rolling_summary"
    assert url == "https://github.com/x/2"


def test_latest_report_returns_error_when_missing(tmp_path):
    result = audit_run.latest_report(tmp_path)

    assert result["error"] == "no audit-panel report found"


def test_latest_report_reads_newest_json(tmp_path):
    old = tmp_path / "audit-panel-2026-04-01.json"
    new = tmp_path / "audit-panel-2026-04-02.json"
    old.write_text('{"old": true}', encoding="utf-8")
    new.write_text('{"new": true}', encoding="utf-8")

    result = audit_run.latest_report(tmp_path)

    assert result["report"] == {"new": True}
