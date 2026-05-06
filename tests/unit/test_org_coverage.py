"""Tests for the dashboard-ready org coverage contract."""

from __future__ import annotations

from lib.autonomy.org_coverage import build_org_coverage


def _status_report() -> dict:
    return {
        "generated_at": "2026-05-05T12:00:00Z",
        "manifest": {"schema_version": 1, "updated_at": "2026-05-05"},
        "summary": {
            "ci_strategies": {
                "sapphire_self_hosted_gate": 1,
                "local_evidence_skip_ci_bootstrap": 1,
            },
            "routine_stages": {"soaking": 2, "blocked": 1},
            "hermes_skill_classes": {"read_only": 10, "local_mutating": 3},
            "open_prs_checked": False,
            "open_pr_count": 0,
        },
        "repos": [
            {
                "id": "sapphire",
                "name": "Sapphire",
                "classification": "core",
                "role": "Operator dashboard and autonomy control plane.",
                "local_path": "/Users/aribs/Code/Sapphire",
                "github": "arigatoexpress/Sapphire",
                "default_branch": "main",
                "ci_strategy": "sapphire_self_hosted_gate",
                "production_adjacent": True,
                "migration_state": "canonical",
                "exists": True,
                "branch": "main",
                "head": "abc123",
                "dirty_count": 0,
                "dirty_summary": {},
                "clean": True,
                "open_prs": [],
                "open_issues": [],
                "errors": [],
            },
            {
                "id": "project-go-forward",
                "name": "Project Go Forward",
                "classification": "satellite",
                "role": "THO production app.",
                "local_path": "/Users/aribs/Code/Project-Go-Forward",
                "github": "arigatoexpress/Project-Go-Forward",
                "default_branch": "main",
                "ci_strategy": "draft_auto_deploy",
                "production_adjacent": True,
                "migration_state": "guardrails_complete",
                "exists": True,
                "branch": "main",
                "head": "def456",
                "dirty_count": 2,
                "dirty_summary": {"modified": 1, "untracked": 1},
                "clean": False,
                "open_prs": [],
                "open_issues": [],
                "errors": [],
            },
            {
                "id": "agentic-arigato",
                "name": "Agentic Arigato",
                "classification": "integration",
                "role": "Protected Cloud Run integration.",
                "local_path": "/Users/aribs/Code/AgenticArigato",
                "github": "arigatoexpress/AgenticArigato",
                "default_branch": "main",
                "ci_strategy": "local_evidence_skip_ci_bootstrap",
                "production_adjacent": True,
                "migration_state": "guardrails_complete_protected_cloud_run",
                "exists": False,
                "dirty_count": None,
                "dirty_summary": None,
                "clean": None,
                "open_prs": [],
                "open_issues": [],
                "errors": ["local path missing"],
            },
        ],
        "upstream_repos": [
            {
                "id": "openclaw",
                "name": "OpenClaw",
                "upstream": "someorg/openclaw",
                "ari_fork": "arigatoexpress/openclaw",
                "local_path": "/Users/aribs/Code/openclaw",
                "integration_surface": "coding agent research",
                "sync_state": "fork_diverged_do_not_force",
                "exists": True,
                "branch": "main",
                "head": "fedcba",
                "dirty_count": 1,
                "dirty_summary": {"modified": 1},
                "clean": False,
                "errors": [],
            }
        ],
        "worktrees": [
            {
                "path": "/Users/aribs/Code/_worktrees/sapphire-org-coverage-frontend",
                "branch": "feat/org-coverage-frontend",
                "head": "123456",
                "clean": False,
                "dirty_count": 1,
                "dirty_summary": {"modified": 1},
                "errors": [],
            }
        ],
        "routines": [{"id": "daily", "stage": "soaking"}],
    }


def test_org_coverage_groups_manifest_repos_and_upstreams() -> None:
    payload = build_org_coverage(status_report=_status_report(), external=False)

    assert payload["mode"] == "org_coverage"
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert payload["writes_by_default"] is False

    summary = payload["summary"]
    assert summary["repos_tracked"] == 3
    assert summary["satellite_repos"] == 1
    assert summary["dirty_repos"] == 1
    assert summary["missing_repos"] == 1
    assert summary["dirty_upstreams"] == 1
    assert summary["dirty_worktree_count"] == 1
    assert summary["attention_items"] == 4

    modules = {module["id"]: module for module in payload["modules"]}
    assert modules["core"]["coverage_pct"] == 100
    assert modules["satellite"]["attention_count"] == 1
    assert modules["integration"]["missing_count"] == 1
    assert modules["upstream"]["repo_count"] == 1


def test_org_coverage_rows_are_frontend_ready_and_path_safe() -> None:
    payload = build_org_coverage(status_report=_status_report(), external=False)
    repos = {repo["id"]: repo for repo in payload["repos"]}

    sapphire = repos["sapphire"]
    assert sapphire["github_url"] == "https://github.com/arigatoexpress/Sapphire"
    assert sapphire["local_path_label"] == "Code/Sapphire"
    assert "/Users/" not in sapphire["local_path_label"]
    assert sapphire["guardrail_count"] >= 1
    assert sapphire["badge_class"] == "online"

    pgf = repos["project-go-forward"]
    assert pgf["state"] == "dirty"
    assert pgf["badge_class"] == "warning"
    assert "Inspect local WIP" in pgf["next_step"]

    assert payload["programs"]
    assert payload["programs"][0]["progress"] == 100
    assert payload["ci_strategies"][0]["label"]
    assert payload["routine_stages"][0]["label"]
