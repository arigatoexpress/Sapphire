"""Tests for the Sapphire safe-merge guardrail wrapper."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops import sapphire_safe_merge as safe_merge


class FakeGh:
    def __init__(
        self,
        *,
        title: str = "feat(ops): land guardrail",
        head_ref_name: str = "feat/pause-status",
        head_ref_oid: str = "abc123",
        runs: list[dict] | None = None,
        pr_view_returncode: int = 0,
    ):
        self.title = title
        self.head_ref_name = head_ref_name
        self.head_ref_oid = head_ref_oid
        self.runs = runs or []
        self.pr_view_returncode = pr_view_returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> safe_merge.CommandResult:
        self.calls.append(cmd)
        if cmd[3:5] == ["pr", "view"]:
            if self.pr_view_returncode:
                return safe_merge.CommandResult(self.pr_view_returncode, stderr="not found")
            return safe_merge.CommandResult(
                0,
                json.dumps(
                    {
                        "title": self.title,
                        "headRefName": self.head_ref_name,
                        "headRefOid": self.head_ref_oid,
                    }
                ),
            )
        if cmd[3:5] == ["pr", "merge"]:
            return safe_merge.CommandResult(0, "")
        if cmd[3:5] == ["run", "list"]:
            return safe_merge.CommandResult(0, json.dumps(self.runs))
        if cmd[3:5] == ["run", "cancel"]:
            return safe_merge.CommandResult(0, "")
        return safe_merge.CommandResult(1, stderr=f"unexpected command: {cmd}")


def _calls(fake: FakeGh, *parts: str) -> list[list[str]]:
    return [cmd for cmd in fake.calls if cmd[3 : 3 + len(parts)] == list(parts)]


def test_build_subject_appends_skip_ci():
    assert safe_merge.build_subject("feat(ops): guardrail") == "feat(ops): guardrail [skip ci]"


def test_build_subject_does_not_double_append_skip_ci():
    assert safe_merge.build_subject("feat(ops): guardrail [skip ci]") == "feat(ops): guardrail [skip ci]"


def test_build_subject_accepts_case_variant_skip_ci():
    assert safe_merge.build_subject("feat(ops): guardrail [SKIP CI]") == "feat(ops): guardrail [SKIP CI]"


def test_build_subject_rejects_empty_title():
    with pytest.raises(safe_merge.SafeMergeError):
        safe_merge.build_subject("   ")


def test_parse_pr_number_rejects_non_numeric():
    with pytest.raises(safe_merge.SafeMergeError):
        safe_merge.parse_pr_number("388abc")


def test_parse_pr_number_rejects_zero():
    with pytest.raises(safe_merge.SafeMergeError):
        safe_merge.parse_pr_number("0")


def test_fetch_pr_info_reads_title_and_head_metadata():
    fake = FakeGh(title="docs: sample")

    info = safe_merge.fetch_pr_info(44, runner=fake)

    assert info.title == "docs: sample"
    assert info.head_ref_name == "feat/pause-status"
    assert info.head_ref_oid == "abc123"
    assert _calls(fake, "pr", "view")


def test_fetch_pr_info_raises_on_gh_error():
    fake = FakeGh(pr_view_returncode=1)

    with pytest.raises(safe_merge.SafeMergeError):
        safe_merge.fetch_pr_info(44, runner=fake)


def test_safe_merge_uses_explicit_skip_ci_subject():
    fake = FakeGh(title="feat(ops): guardrail")

    result = safe_merge.safe_merge(44, runner=fake)

    merge_call = _calls(fake, "pr", "merge")[0]
    assert result.subject == "feat(ops): guardrail [skip ci]"
    assert merge_call[-2:] == ["-t", "feat(ops): guardrail [skip ci]"]


def test_safe_merge_dry_run_does_not_merge_or_cancel():
    fake = FakeGh(runs=[{"databaseId": 1, "status": "queued", "headBranch": "feat/pause-status"}])

    result = safe_merge.safe_merge(44, runner=fake, dry_run=True)

    assert result.dry_run is True
    assert not _calls(fake, "pr", "merge")
    assert not _calls(fake, "run", "cancel")


def test_active_runs_cancel_by_pr_head_branch():
    fake = FakeGh(runs=[{"databaseId": 11, "status": "queued", "headBranch": "feat/pause-status"}])

    result = safe_merge.safe_merge(44, runner=fake)

    assert result.cancelled_runs == (11,)
    assert _calls(fake, "run", "cancel")[0][-1] == "11"


def test_active_runs_cancel_by_pr_head_sha():
    fake = FakeGh(runs=[{"databaseId": 12, "status": "in_progress", "headSha": "abc123"}])

    result = safe_merge.safe_merge(44, runner=fake)

    assert result.cancelled_runs == (12,)


def test_active_runs_cancel_by_exact_main_squash_subject():
    fake = FakeGh(
        title="feat(ops): guardrail",
        runs=[
            {
                "databaseId": 13,
                "status": "queued",
                "headBranch": "main",
                "displayTitle": "feat(ops): guardrail [skip ci]",
            }
        ],
    )

    result = safe_merge.safe_merge(44, runner=fake)

    assert result.cancelled_runs == (13,)


def test_active_runs_ignore_completed_and_unrelated_runs():
    fake = FakeGh(
        runs=[
            {"databaseId": 14, "status": "completed", "headBranch": "feat/pause-status"},
            {"databaseId": 15, "status": "queued", "headBranch": "other-branch"},
        ]
    )

    result = safe_merge.safe_merge(44, runner=fake)

    assert result.cancelled_runs == ()
    assert not _calls(fake, "run", "cancel")


def test_active_runs_skip_missing_database_id():
    fake = FakeGh(runs=[{"status": "queued", "headBranch": "feat/pause-status"}])

    result = safe_merge.safe_merge(44, runner=fake)

    assert result.cancelled_runs == ()
