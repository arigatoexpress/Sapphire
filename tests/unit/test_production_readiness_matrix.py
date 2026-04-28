"""Tests for the full-system production readiness matrix."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "production_readiness_matrix.py"

SPEC = importlib.util.spec_from_file_location("production_readiness_matrix", SCRIPT)
assert SPEC and SPEC.loader
matrix = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = matrix
SPEC.loader.exec_module(matrix)


def _runner(args: list[str]) -> matrix.CommandResult:
    command = " ".join(args)
    if command.startswith("git status"):
        return matrix.CommandResult(True, "## main...origin/main\n")
    if command.startswith("git rev-parse"):
        return matrix.CommandResult(True, "abc123def456\n")
    raise AssertionError(f"unexpected command: {command}")


def test_parse_launchctl_list_extracts_pid_status_and_label() -> None:
    rows = matrix.parse_launchctl_list(
        "123\t0\tcom.sapphire.control-plane\n-\t0\tcom.sapphire.backtest-weekly\n"
    )

    assert rows["com.sapphire.control-plane"] == {"pid": "123", "status": "0"}
    assert rows["com.sapphire.backtest-weekly"] == {"pid": "-", "status": "0"}


def test_latest_local_ci_report_uses_newest_valid_json(tmp_path: Path) -> None:
    older = tmp_path / "local-ci-verify-20260101T000000Z.json"
    newer = tmp_path / "local-ci-verify-20260102T000000Z.json"
    older.write_text(json.dumps({"verdict": "FAIL", "head": "old"}))
    newer.write_text(json.dumps({"verdict": "PASS", "head": "new"}))

    report = matrix.latest_local_ci_report(tmp_path)

    assert report == {"verdict": "PASS", "head": "new"}


def test_git_and_ci_surfaces_are_pass_when_clean_and_latest_ci_passes(tmp_path: Path) -> None:
    (tmp_path / "local-ci-verify-20260102T000000Z.json").write_text(
        json.dumps(
            {
                "verdict": "PASS",
                "head": "abc123def456",
                "completed_at": "2026-01-02T00:00:00Z",
                "checks": [{"name": "ruff", "status": "PASS"}],
            }
        )
    )

    git_surface = matrix.git_surfaces(_runner)[0]
    ci_surface = matrix.local_ci_surfaces(tmp_path)[0]

    assert git_surface["status"] == "pass"
    assert "dirty entries=0" in git_surface["evidence"]
    assert ci_surface["status"] == "pass"
    assert "PASS" in ci_surface["evidence"]


def test_summarize_surfaces_ignores_launchagent_manual_gate_as_hard_blocker() -> None:
    surfaces = [
        matrix.surface(
            "google_launchagent_retargeting", "google-gcp", "blocked", "token", "rotate"
        ),
        matrix.surface("media_factory_status", "media", "warn", "none", "dry run"),
        matrix.surface("local_ci_latest", "repo", "pass", "green", "keep"),
    ]

    summary = matrix.summarize_surfaces(surfaces)

    assert summary["production_testing_posture"] == "go"
    assert summary["hard_blocker_count"] == 0
    assert summary["by_status"]["warn"] == 1


def test_render_markdown_includes_guardrails_surfaces_and_next_actions() -> None:
    report = {
        "generated_at": "2026-04-27T00:00:00Z",
        "mode": "no-external",
        "guardrails": ["No live sends."],
        "summary": {
            "production_testing_posture": "go",
            "surface_count": 2,
            "hard_blocker_count": 0,
            "hard_blockers": [],
            "by_status": {"pass": 1, "warn": 1},
        },
        "surfaces": [
            matrix.surface("repo_git_status", "repo", "pass", "clean", "keep clean"),
            matrix.surface("media_factory_status", "media", "warn", "0 runs", "dry run"),
        ],
        "next_actions": [
            {
                "id": "media_factory_status",
                "area": "media",
                "status": "warn",
                "next_action": "dry run",
            }
        ],
        "subreports": {},
    }

    markdown = matrix.render_markdown(report)

    assert "# Sapphire Production Readiness Matrix" in markdown
    assert "No live sends." in markdown
    assert "`media_factory_status`" in markdown
    assert "`warn` `media/media_factory_status`" in markdown
