"""Tests for the routine soak status reporter."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "routine_soak_status.py"

SPEC = importlib.util.spec_from_file_location("routine_soak_status", SCRIPT)
assert SPEC and SPEC.loader
routine_soak_status = importlib.util.module_from_spec(SPEC)
sys.modules["routine_soak_status"] = routine_soak_status
SPEC.loader.exec_module(routine_soak_status)


def _run(
    *,
    database_id: int,
    created_at: str,
    event: str = "schedule",
    conclusion: str = "success",
) -> dict:
    return {
        "database_id": database_id,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created_at,
        "event": event,
        "head_branch": "main",
        "display_title": "routine",
    }


def _manifest() -> dict:
    return {
        "routines": [
            {
                "id": "threat-refresh",
                "local_label": "com.sapphire.threat-refresh",
                "stage": "soaking",
                "remote_workflow": ".github/workflows/threat-refresh.yml",
                "comparator": "scripts/ops/compare_threat_artifacts.py",
                "soak_tracking": {
                    "started_at": "2026-04-26",
                    "required_scheduled_successes": 2,
                    "latest_comparison": {
                        "verdict": "WARN",
                        "rows_fail": 0,
                    },
                },
            },
            {
                "id": "correlation-refresh",
                "stage": "local",
            },
        ]
    }


def test_summarize_runs_counts_only_runs_since_start() -> None:
    runs = [
        _run(database_id=1, created_at="2026-04-25T23:10:00Z"),
        _run(database_id=2, created_at="2026-04-26T01:10:00Z"),
        _run(database_id=3, created_at="2026-04-26T05:10:00Z", conclusion="failure"),
        _run(
            database_id=4,
            created_at="2026-04-26T06:10:00Z",
            event="workflow_dispatch",
        ),
    ]

    summary = routine_soak_status.summarize_runs(
        runs,
        started_at=datetime(2026, 4, 26, tzinfo=UTC),
    )

    assert summary["total_since_start"] == 3
    assert summary["scheduled_total_since_start"] == 2
    assert summary["scheduled_success_since_start"] == 1
    assert summary["manual_success_since_start"] == 1
    assert summary["by_event"] == {"schedule": 2, "workflow_dispatch": 1}
    assert summary["latest_run"]["database_id"] == 4


def test_build_report_marks_ready_after_required_scheduled_successes(monkeypatch) -> None:
    def fake_runs(*, repo: str, workflow: str, limit: int) -> dict:
        assert repo == "arigatoexpress/Sapphire"
        assert workflow == ".github/workflows/threat-refresh.yml"
        assert limit == 25
        return {
            "available": True,
            "error": "",
            "runs": [
                {
                    "databaseId": 10,
                    "status": "completed",
                    "conclusion": "success",
                    "createdAt": "2026-04-26T05:10:00Z",
                    "event": "schedule",
                    "headBranch": "main",
                    "displayTitle": "threat-refresh",
                },
                {
                    "databaseId": 11,
                    "status": "completed",
                    "conclusion": "success",
                    "createdAt": "2026-04-26T09:10:00Z",
                    "event": "schedule",
                    "headBranch": "main",
                    "displayTitle": "threat-refresh",
                },
            ],
        }

    monkeypatch.setattr(routine_soak_status, "github_workflow_runs", fake_runs)

    report = routine_soak_status.build_report(
        _manifest(),
        repo="arigatoexpress/Sapphire",
        external=True,
        run_limit=25,
    )

    assert report["routine_count"] == 1
    routine = report["routines"][0]
    assert routine["id"] == "threat-refresh"
    assert routine["github_runs"]["scheduled_success_since_start"] == 2
    assert routine["gate_state"] == "ready_for_artifact_review"
    assert report["summary"]["ready_for_artifact_review"] == 1


def test_build_report_no_external_is_explicitly_marked() -> None:
    report = routine_soak_status.build_report(_manifest(), external=False)

    routine = report["routines"][0]
    assert routine["github_runs"]["available"] is False
    assert routine["github_runs"]["error"] == "external probes disabled"
    assert routine["gate_state"] == "external_disabled"
    assert report["summary"]["external_disabled"] == 1


def test_render_markdown_omits_raw_run_payload_shape() -> None:
    report = {
        "generated_at": "2026-04-26T00:00:00Z",
        "repo": "arigatoexpress/Sapphire",
        "external": True,
        "summary": {
            "ready_for_artifact_review": 0,
            "collecting": 1,
            "blocked": 0,
            "external_disabled": 0,
        },
        "routines": [
            {
                "id": "threat-refresh",
                "workflow_name": "threat-refresh.yml",
                "required_scheduled_successes": 24,
                "latest_comparison": {"verdict": "WARN", "rows_fail": 0},
                "github_runs": {
                    "scheduled_success_since_start": 6,
                    "manual_success_since_start": 2,
                    "latest_run": _run(
                        database_id=42,
                        created_at="2026-04-26T17:57:29Z",
                    ),
                    "error": "",
                },
                "gate_state": "collecting",
            }
        ],
    }

    rendered = routine_soak_status.render_markdown(report)

    assert "# Sapphire Routine Soak Status" in rendered
    assert "threat-refresh.yml" in rendered
    assert "42 schedule/success 2026-04-26T17:57:29Z" in rendered
    assert "WARN (0 fail)" in rendered
