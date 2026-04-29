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
        files: list[dict] | None = None,
        runs: list[dict] | None = None,
        pr_view_returncode: int = 0,
        local_ci_returncode: int = 0,
    ):
        self.title = title
        self.head_ref_name = head_ref_name
        self.head_ref_oid = head_ref_oid
        self.files = files if files is not None else [{"path": "docs/ops/safe-merge-runbook.md"}]
        self.runs = runs or []
        self.pr_view_returncode = pr_view_returncode
        self.local_ci_returncode = local_ci_returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> safe_merge.CommandResult:
        self.calls.append(cmd)
        if cmd[:2] == [sys.executable, "scripts/ops/local_ci_verify.py"]:
            if self.local_ci_returncode:
                return safe_merge.CommandResult(self.local_ci_returncode, stderr="local ci failed")
            return safe_merge.CommandResult(0, "")
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
                        "files": self.files,
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


def _local_ci_calls(fake: FakeGh) -> list[list[str]]:
    return [
        cmd for cmd in fake.calls if cmd[:2] == [sys.executable, "scripts/ops/local_ci_verify.py"]
    ]


def test_build_subject_appends_skip_ci():
    assert safe_merge.build_subject("feat(ops): guardrail") == "feat(ops): guardrail [skip ci]"


def test_build_subject_does_not_double_append_skip_ci():
    assert (
        safe_merge.build_subject("feat(ops): guardrail [skip ci]")
        == "feat(ops): guardrail [skip ci]"
    )


def test_build_subject_accepts_case_variant_skip_ci():
    assert (
        safe_merge.build_subject("feat(ops): guardrail [SKIP CI]")
        == "feat(ops): guardrail [SKIP CI]"
    )


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
    assert info.changed_files == ("docs/ops/safe-merge-runbook.md",)
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
    assert result.docs_only is True
    assert result.local_ci_ran is False
    assert not _local_ci_calls(fake)


def test_safe_merge_dry_run_does_not_merge_or_cancel():
    fake = FakeGh(
        files=[{"path": "scripts/ops/local_ci_verify.py"}],
        runs=[{"databaseId": 1, "status": "queued", "headBranch": "feat/pause-status"}],
    )

    result = safe_merge.safe_merge(44, runner=fake, dry_run=True)

    assert result.dry_run is True
    assert result.docs_only is False
    assert result.local_ci_ran is False
    assert not _calls(fake, "pr", "merge")
    assert not _calls(fake, "run", "cancel")
    assert not _local_ci_calls(fake)


def test_safe_merge_runs_local_ci_for_non_docs_pr_before_merge():
    fake = FakeGh(files=[{"path": "scripts/ops/sapphire_safe_merge.py"}])

    result = safe_merge.safe_merge(44, runner=fake)

    local_ci_call = _local_ci_calls(fake)[0]
    merge_call = _calls(fake, "pr", "merge")[0]
    assert local_ci_call == [
        sys.executable,
        "scripts/ops/local_ci_verify.py",
        "--pr",
        "44",
        "--quiet",
    ]
    assert fake.calls.index(local_ci_call) < fake.calls.index(merge_call)
    assert result.docs_only is False
    assert result.local_ci_ran is True


def test_safe_merge_blocks_non_docs_pr_when_local_ci_fails():
    fake = FakeGh(
        files=[{"path": "lib/core/kill_switch.py"}],
        local_ci_returncode=20,
    )

    with pytest.raises(safe_merge.SafeMergeError, match="local CI verification failed"):
        safe_merge.safe_merge(44, runner=fake)

    assert _local_ci_calls(fake)
    assert not _calls(fake, "pr", "merge")


def test_is_docs_only_pr_accepts_docs_and_markdown_files():
    pr = safe_merge.PullRequestInfo(
        number=1,
        title="docs: update",
        head_ref_name="docs/update",
        head_ref_oid="abc123",
        changed_files=("README.md", "docs/ops/runbook.md", ".github/PULL_REQUEST_TEMPLATE.md"),
    )

    assert safe_merge.is_docs_only_pr(pr) is True


def test_is_docs_only_pr_rejects_empty_or_code_files():
    empty = safe_merge.PullRequestInfo(1, "empty", "branch", "abc123", ())
    code = safe_merge.PullRequestInfo(
        1,
        "fix: code",
        "branch",
        "abc123",
        ("docs/ops/runbook.md", "tests/unit/test_sapphire_safe_merge.py"),
    )
    deps = safe_merge.PullRequestInfo(
        1,
        "fix: deps",
        "branch",
        "abc123",
        ("requirements-test.txt",),
    )

    assert safe_merge.is_docs_only_pr(empty) is False
    assert safe_merge.is_docs_only_pr(code) is False
    assert safe_merge.is_docs_only_pr(deps) is False


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
