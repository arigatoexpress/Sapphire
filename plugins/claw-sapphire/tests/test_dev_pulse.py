"""Tests for the dev_pulse tool.

All external commands (`gh`, `gcloud`, `launchctl`, `git`) are monkeypatched.
Nothing here hits the network or the local filesystem outside `tmp_path`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import dev_pulse  # type: ignore

# ── helpers ────────────────────────────────────────────────────────────────


class FakeRun:
    """Stand-in for dev_pulse._run — dispatches on argv prefix."""

    def __init__(self):
        self.handlers: list = []

    def register(self, prefix: list[str], rc: int, stdout: str = "", stderr: str = ""):
        self.handlers.append((prefix, rc, stdout, stderr))

    def __call__(self, cmd, timeout=10):
        for prefix, rc, stdout, stderr in self.handlers:
            if cmd[: len(prefix)] == prefix:
                return rc, stdout, stderr
        return 127, "", f"no fake handler for {cmd}"


@pytest.fixture
def fake_run(monkeypatch):
    fr = FakeRun()
    monkeypatch.setattr(dev_pulse, "_run", fr)
    # Pretend both CLIs exist so shutil.which short-circuits are fine
    monkeypatch.setattr(dev_pulse.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    return fr


# ── repo status ────────────────────────────────────────────────────────────


def test_collect_repo_status_happy_path(fake_run, tmp_path):
    repo_path = tmp_path / "fake-repo"
    (repo_path / ".git").mkdir(parents=True)

    fake_run.register(
        ["git", "-C", str(repo_path), "branch", "--show-current"],
        0, "main\n",
    )
    fake_run.register(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        0, " M file_a.py\n?? file_b.py\n",
    )
    fake_run.register(
        ["gh", "pr", "list", "--repo", "arigato/test"],
        0,
        json.dumps([
            {
                "number": 42,
                "title": "feat: thing",
                "isDraft": False,
                "author": {"login": "bot"},
                "updatedAt": "2026-04-23T00:00:00Z",
            },
        ]),
    )
    fake_run.register(
        ["gh", "run", "list", "--repo", "arigato/test"],
        0,
        json.dumps([
            {
                "status": "completed",
                "conclusion": "success",
                "displayTitle": "feat: thing",
                "createdAt": "2026-04-23T01:00:00Z",
                "url": "https://github.com/arigato/test/actions/runs/1",
            },
        ]),
    )

    status = dev_pulse.collect_repo_status("arigato/test", repo_path, "test")
    assert status.nickname == "test"
    assert status.local_branch == "main"
    assert status.local_dirty_count == 2
    assert len(status.open_prs) == 1
    assert status.open_prs[0]["number"] == 42
    assert status.latest_ci["conclusion"] == "success"
    assert status.error is None


def test_collect_repo_status_missing_local_path(fake_run, tmp_path):
    fake_run.register(["gh", "pr", "list"], 0, "[]")
    fake_run.register(["gh", "run", "list"], 0, "[]")

    status = dev_pulse.collect_repo_status(
        "arigato/test", tmp_path / "does-not-exist", "test"
    )
    assert status.local_path_exists is False
    assert status.local_branch is None
    assert status.local_dirty_count == 0


def test_collect_repo_status_gh_failure_surfaces_error(fake_run, tmp_path):
    repo_path = tmp_path / "fake-repo"
    (repo_path / ".git").mkdir(parents=True)
    fake_run.register(["git", "-C", str(repo_path)], 0, "main\n")
    fake_run.register(["gh", "pr", "list"], 1, "", "auth required\n")
    fake_run.register(["gh", "run", "list"], 0, "[]")

    status = dev_pulse.collect_repo_status("arigato/test", repo_path, "test")
    assert status.error is not None
    assert "auth required" in status.error


# ── cloud run status ───────────────────────────────────────────────────────


def test_collect_cloud_run_status_happy_path(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps({
            "status": {
                "latestReadyRevisionName": "svc-00055-xyz",
                "url": "https://svc.run.app",
                "conditions": [{"type": "Ready", "status": "True"}],
            }
        }),
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "svc")
    assert s.latest_revision == "svc-00055-xyz"
    assert s.ready is True
    assert s.url == "https://svc.run.app"


def test_collect_cloud_run_status_not_ready(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps({
            "status": {
                "latestReadyRevisionName": "svc-00010",
                "conditions": [{"type": "Ready", "status": "False"}],
            }
        }),
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "svc")
    assert s.ready is False


def test_collect_cloud_run_status_gcloud_error(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        1, "", "service not found\n",
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "missing")
    assert s.error is not None
    assert "service not found" in s.error


# ── service statuses ───────────────────────────────────────────────────────


def test_collect_service_statuses_parses_launchctl(fake_run):
    fake_run.register(
        ["launchctl", "list"],
        0,
        "PID\tStatus\tLabel\n"
        "1234\t0\tcom.sapphire.inference-proxy\n"
        "-\t0\tcom.sapphire.dashboard\n"
        "5678\t127\tai.hermes.gateway\n",
    )
    labels = [
        "com.sapphire.inference-proxy",
        "com.sapphire.dashboard",
        "ai.hermes.gateway",
        "com.sapphire.pm-bot",  # not loaded
    ]
    out = dev_pulse.collect_service_statuses(labels)
    by_label = {s.label: s for s in out}
    assert by_label["com.sapphire.inference-proxy"].loaded is True
    assert by_label["com.sapphire.inference-proxy"].pid == 1234
    assert by_label["com.sapphire.inference-proxy"].exit_code == 0
    assert by_label["com.sapphire.dashboard"].pid is None
    assert by_label["ai.hermes.gateway"].exit_code == 127
    assert by_label["com.sapphire.pm-bot"].loaded is False


def test_collect_service_statuses_launchctl_fails(fake_run):
    fake_run.register(["launchctl", "list"], 1, "", "fail")
    out = dev_pulse.collect_service_statuses(["com.sapphire.inference-proxy"])
    assert out[0].loaded is False


# ── pulse() orchestration ──────────────────────────────────────────────────


def test_pulse_runs_all_collectors(fake_run, tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)
    fake_run.register(["git", "-C"], 0, "main\n")
    fake_run.register(["gh", "pr", "list"], 0, "[]")
    fake_run.register(["gh", "run", "list"], 0, "[]")
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps({"status": {"latestReadyRevisionName": "r1", "conditions": [{"type": "Ready", "status": "True"}]}}),
    )
    fake_run.register(["launchctl", "list"], 0, "PID\tStatus\tLabel\n")

    p = dev_pulse.pulse(
        repos=[("arigato/r", repo_path, "r")],
        cloud_run=[("proj", "us-central1", "svc")],
        services=["com.sapphire.fake"],
    )
    assert len(p.repos) == 1
    assert len(p.cloud_run) == 1
    assert len(p.services) == 1


# ── MarkdownV2 formatter ───────────────────────────────────────────────────


def test_format_markdown_v2_escapes_special_chars():
    pulse_result = dev_pulse.DevPulse(
        repos=[
            dev_pulse.RepoStatus(
                nickname="tho",
                full_name="arigato/tho",
                local_path_exists=True,
                local_branch="main",
                local_dirty_count=3,
                open_prs=[
                    {
                        "number": 12,
                        "title": "feat: add _something_ great!",
                        "draft": False,
                        "author": "user",
                        "updated_at": "",
                    }
                ],
                latest_ci={
                    "status": "completed",
                    "conclusion": "success",
                    "title": "green",
                    "created_at": "",
                    "url": "",
                },
            ),
        ],
    )
    out = dev_pulse.format_markdown_v2(pulse_result)
    assert "✅" in out  # success CI emoji
    assert "3 uncommitted" in out.replace("\\", "")  # escaped but present
    assert "\\_" in out  # underscore escaped
    assert "\\!" in out  # exclamation escaped


def test_format_markdown_v2_shows_unloaded_services():
    pulse_result = dev_pulse.DevPulse(
        services=[
            dev_pulse.ServiceStatus(label="com.sapphire.ok", loaded=True, pid=1, exit_code=0),
            dev_pulse.ServiceStatus(label="com.sapphire.dead", loaded=False),
        ],
    )
    out = dev_pulse.format_markdown_v2(pulse_result)
    assert "1/2" in out
    assert "com\\.sapphire\\.dead" in out


def test_format_markdown_v2_handles_empty_pulse():
    out = dev_pulse.format_markdown_v2(dev_pulse.DevPulse())
    # Even with nothing to report, should not crash and starts with title
    assert out.startswith("*dev pulse*")
