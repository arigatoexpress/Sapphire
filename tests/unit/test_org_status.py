"""Tests for the Sapphire autonomous-org control tower."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "org_status.py"
MANIFEST = ROOT / "infra" / "org-repos.yaml"
CLASSIFICATION_REPORT = ROOT / "infra" / "org-classification-report.yaml"
HERMES_SKILLS = ROOT / "infra" / "hermes-sapphire-skills.yaml"

SPEC = importlib.util.spec_from_file_location("org_status", SCRIPT)
assert SPEC and SPEC.loader
org_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(org_status)


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _classification_report() -> dict:
    return yaml.safe_load(CLASSIFICATION_REPORT.read_text(encoding="utf-8"))


def _hermes_skills() -> dict:
    return yaml.safe_load(HERMES_SKILLS.read_text(encoding="utf-8"))


def test_manifest_tracks_required_core_and_satellite_fields() -> None:
    manifest = _manifest()
    allowed_classes = {
        "core",
        "satellite",
        "integration",
        "candidate_absorb",
        "candidate_archive",
    }
    required = {
        "id",
        "name",
        "classification",
        "role",
        "local_path",
        "default_branch",
        "ci_strategy",
        "production_adjacent",
        "required_guardrails",
        "migration_state",
    }
    allowed_ci_strategies = {
        "sapphire_self_hosted_gate",
        "local_evidence_skip_ci_bootstrap",
        "draft_auto_deploy",
        "upstream_fork_local_only",
    }

    repos = manifest["repos"]
    assert {repo["id"] for repo in repos} >= {
        "sapphire",
        "project-go-forward",
        "org-platform",
        "cyber-threat-bot",
        "tradingview-mcp-v2",
        "hermes-agent",
    }
    for repo in repos:
        assert repo["classification"] in allowed_classes
        assert repo["ci_strategy"] in allowed_ci_strategies
        if repo["classification"] in {"core", "satellite"}:
            assert required <= set(repo)
            assert repo["github"], f"{repo['id']} needs a GitHub repo"
            assert repo["required_guardrails"]


def test_production_adjacent_repos_have_no_spend_ci_posture() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}

    for repo in repos.values():
        if repo["production_adjacent"]:
            assert repo["ci_strategy"], f"{repo['id']} needs ci_strategy"

    assert repos["sapphire"]["ci_strategy"] == "sapphire_self_hosted_gate"
    assert repos["project-go-forward"]["ci_strategy"] == "draft_auto_deploy"
    assert repos["org-platform"]["ci_strategy"] == "local_evidence_skip_ci_bootstrap"
    assert repos["hermes-agent"]["ci_strategy"] == "upstream_fork_local_only"
    assert repos["regional-intel-workbench"]["ci_strategy"] == ("local_evidence_skip_ci_bootstrap")


def test_org_platform_tracks_local_showcase_runtime() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["org-platform"]

    assert repo["classification"] == "satellite"
    assert repo["github"] == "arigatoexpress/org-platform"
    assert repo["migration_state"] == "active_local_showcase"
    assert repo["local_runtime_tracking"] == {
        "launchagent_label": "com.codex.org-platform-dashboard",
        "dashboard_url": "http://127.0.0.1:3000",
        "validated_commands": ["make test", "make dashboard-build"],
        "next_step": (
            "Add no-spend CI gate or keep local evidence as the merge proof for dashboard "
            "and OSINT demo changes."
        ),
    }


def test_manifest_tracks_upstream_integration_fleet() -> None:
    manifest = _manifest()
    upstream_repos = manifest["upstream_repos"]
    by_id = {repo["id"]: repo for repo in upstream_repos}

    assert {repo["id"] for repo in upstream_repos} >= {
        "openbb",
        "kronos",
        "lumo-api-v2",
        "hermes-agent-upstream",
        "foundry-platform-python",
        "nemoclaw",
    }
    for repo in upstream_repos:
        assert repo["id"]
        assert repo["name"]
        assert repo["upstream"]
        assert repo["local_path"].startswith("/Users/aribs/Code/")
        assert repo["integration_surface"]
        assert repo["sync_state"]

    assert by_id["openbb"]["ari_fork"] == "arigatoexpress/OpenBB"
    assert by_id["openclaw"]["sync_state"] == "fork_diverged_do_not_force"
    assert by_id["aip-community-registry"]["ari_fork"] == "arigatoexpress/aip-community-registry"
    assert (
        by_id["aip-community-registry"]["sync_state"]
        == "forked_lfs_filter_bypassed_clean_reference"
    )


def test_tradingview_mcp_v2_tracks_upstream_hardening_pr() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["tradingview-mcp-v2"]

    assert repo["migration_state"] == "upstream_pr_open"
    assert (
        repo["hardening_tracking"]["upstream_pr"]
        == "https://github.com/tradesdontlie/tradingview-mcp/pull/102"
    )
    assert repo["hardening_tracking"]["validated_commands"] == [
        "npm run check:syntax",
        "npm run test:offline",
    ]


def test_crypto_tax_tracker_tracks_completed_guardrail_pr() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["crypto-tax-tracker"]

    assert repo["migration_state"] == "guardrails_complete"
    assert "AGENTS.md" in repo["required_guardrails"]
    assert (
        repo["hardening_tracking"]["repo_pr"]
        == "https://github.com/arigatoexpress/crypto-tax-tracker/pull/2"
    )
    assert repo["hardening_tracking"]["validated_commands"] == [
        ".venv/bin/ruff check src tests",
        ".venv/bin/python -m pytest -q",
        'PATH="$PWD/.venv/bin:$PATH" .venv/bin/pre-commit run --all-files',
    ]


def test_agentic_arigato_tracks_protected_cloud_run_service() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["agentic-arigato"]

    assert repo["classification"] == "integration"
    assert repo["migration_state"] == "guardrails_complete_protected_cloud_run"
    assert repo["github"] == "arigatoexpress/AgenticArigato"
    assert "CI on PR" in repo["required_guardrails"]
    assert "pre-commit or equivalent lint/test parity" in repo["required_guardrails"]
    tracking = repo["cloud_run_tracking"]
    assert tracking["project_id"] == "tho-ai-agent"
    assert tracking["service"] == "agentic-pm-hub"
    assert tracking["public_invoker"] is False
    assert tracking["authenticated_health_paths"] == ["/health", "/healthz/"]
    assert tracking["warning_kind"] == "cloud_run_auth_required"
    assert tracking["repo_pr"] == "https://github.com/arigatoexpress/AgenticArigato/pull/1"
    assert (
        tracking["authenticated_health_runbook"]
        == "https://github.com/arigatoexpress/AgenticArigato/pull/2"
    )
    assert tracking["authenticated_health_script"] == "scripts/ops/check_agentic_pm_hub_health.sh"
    assert tracking["validated_commands"] == [
        "cd bd-analytics-agent && uv run pytest tests/unit -q",
        "cd bd-analytics-agent && uv run ruff check app/server.py app/agent.py app/retrievers.py app/templates.py app/utils tests/unit",
        "cd bd-analytics-agent && uv run ruff format app/server.py app/agent.py app/retrievers.py app/templates.py app/utils tests/unit --check",
        "uvx pre-commit run --all-files",
        "scripts/ops/check_agentic_pm_hub_health.sh",
    ]


def test_threat_refresh_tracks_soak_evidence() -> None:
    routines = {routine["id"]: routine for routine in _manifest()["routines"]}
    routine = routines["threat-refresh"]

    assert routine["stage"] == "soaking"
    assert routine["remote_workflow"] == ".github/workflows/threat-refresh.yml"
    assert routine["comparator"] == "scripts/ops/compare_threat_artifacts.py"
    assert (
        routine["soak_tracking"]["evidence_doc"]
        == "docs/org/threat-refresh-shadow-soak-2026-04-26.md"
    )
    assert routine["soak_tracking"]["latest_manual_remote_run_id"] == "24962186595"
    assert routine["soak_tracking"]["required_scheduled_successes"] == 24
    assert routine["soak_tracking"]["latest_comparison"] == {
        "compared_at": "2026-04-26T17:04:37Z",
        "verdict": "WARN",
        "rows_compared": 15,
        "rows_pass": 10,
        "rows_warn": 5,
        "rows_fail": 0,
        "missing_in_local": 0,
        "missing_in_remote": 0,
    }


def test_backtest_weekly_tracks_soak_evidence() -> None:
    routines = {routine["id"]: routine for routine in _manifest()["routines"]}
    routine = routines["backtest-weekly"]

    assert routine["stage"] == "soaking"
    assert routine["remote_workflow"] == ".github/workflows/weekly-backtest.yml"
    assert routine["comparator"] == "scripts/ops/compare_backtest_artifacts.py"
    assert (
        routine["soak_tracking"]["evidence_doc"]
        == "docs/org/backtest-weekly-shadow-soak-2026-04-26.md"
    )
    assert routine["soak_tracking"]["required_scheduled_successes"] == 4
    assert routine["soak_tracking"]["latest_comparison"] == {
        "compared_at": "2026-04-26T16:15:51Z",
        "verdict": "PASS",
        "rows_compared": 756,
        "rows_pass": 756,
        "rows_warn": 0,
        "rows_fail": 0,
        "missing_in_local": 0,
        "missing_in_remote": 0,
        "leaderboard_top3_order_equal": True,
    }


def test_content_engine_tracks_soak_evidence() -> None:
    routines = {routine["id"]: routine for routine in _manifest()["routines"]}
    routine = routines["content-engine"]

    assert routine["stage"] == "soaking"
    assert routine["remote_workflow"] == ".github/workflows/content-engine.yml"
    assert routine["comparator"] == "scripts/ops/compare_content_artifacts.py"
    assert (
        routine["soak_tracking"]["evidence_doc"]
        == "docs/org/content-engine-shadow-soak-2026-04-26.md"
    )
    assert routine["soak_tracking"]["required_scheduled_successes"] == 7
    assert routine["soak_tracking"]["latest_manual_remote_run_id"] == "24966520333"
    assert routine["soak_tracking"]["latest_comparison"] == {
        "compared_at": "2026-04-26T20:41:18Z",
        "verdict": "WARN",
        "rows_compared": 4,
        "rows_pass": 0,
        "rows_warn": 4,
        "rows_fail": 0,
        "missing_in_local": 0,
        "missing_in_remote": 0,
    }


def test_hermes_agent_tracks_runtime_checkout_and_local_patches() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["hermes-agent"]

    assert repo["migration_state"] == "local_runtime_mapped"
    assert repo["pr_github"] == "arigatoexpress/hermes-agent"
    tracking = repo["runtime_tracking"]
    assert tracking["consolidation_doc"] == "docs/org/hermes-agent-consolidation-map.md"
    assert tracking["launchagent_label"] == "ai.hermes.gateway"
    assert tracking["runtime_path"] == "/Users/aribs/.hermes/hermes-agent"
    assert tracking["dev_clone_path"] == "/Users/aribs/Code/hermes-agent"
    assert [item["sha"] for item in tracking["local_runtime_commits"]] == [
        "5f2af81c",
        "3ba7bd5f",
    ]


def test_actionable_pr_tracking_uses_ari_forks_for_upstream_integrations() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}

    assert repos["claw-code"]["github"] == "instructkr/claw-code"
    assert repos["claw-code"]["pr_github"] == "arigatoexpress/claw-code"
    assert repos["tradingview-mcp-v2"]["github"] == "tradesdontlie/tradingview-mcp"
    assert repos["tradingview-mcp-v2"]["pr_github"] == "arigatoexpress/tradingview-mcp-upstream"
    assert repos["hermes-agent"]["github"] == "NousResearch/hermes-agent"
    assert repos["hermes-agent"]["pr_github"] == "arigatoexpress/hermes-agent"


def test_open_pr_count_excludes_probe_errors() -> None:
    report = org_status.collect_status(_manifest(), external=False)
    report["repos"][0]["open_prs"] = [
        {"number": 1, "title": "real"},
        {"error": "repo unavailable"},
    ]

    assert org_status.count_actionable_items(report["repos"][0]["open_prs"]) == 1


def test_status_report_includes_runtime_tracking_without_required_runtime_path(
    tmp_path: Path,
) -> None:
    manifest = deepcopy(_manifest())
    hermes = next(repo for repo in manifest["repos"] if repo["id"] == "hermes-agent")
    hermes["runtime_tracking"]["runtime_path"] = str(tmp_path / "missing-runtime")

    report = org_status.collect_status(manifest, external=False)
    hermes_status = next(repo for repo in report["repos"] if repo["id"] == "hermes-agent")

    assert hermes_status["runtime"] == {
        "launchagent_label": "ai.hermes.gateway",
        "runtime_path": str(tmp_path / "missing-runtime"),
        "expected_branch": "local/sapphire-relay-ignore",
        "exists": False,
        "branch": None,
        "head": None,
        "dirty_count": None,
        "dirty_summary": None,
        "clean": None,
        "errors": [],
    }


def test_kimi_tools_tracks_absorb_guardrails() -> None:
    repos = {repo["id"]: repo for repo in _manifest()["repos"]}
    repo = repos["kimi-tools"]

    assert repo["migration_state"] == "absorb_guardrails_tested"
    tracking = repo["absorb_tracking"]
    assert tracking["consolidation_doc"] == "docs/org/kimi-tools-absorb-map.md"
    assert tracking["live_callers_found"] is False
    assert tracking["target_repo"] == "sapphire"
    assert tracking["guardrail_tests"] == ["tests/unit/test_kimi_cloud_fallback.py"]


def test_hermes_sapphire_skill_surface_inventory_is_complete_and_sanitized() -> None:
    inventory = _hermes_skills()
    allowed_classes = {
        "read_only",
        "local_mutating",
        "external_mutating",
        "production_adjacent",
    }
    skills = inventory["skills"]

    assert inventory["schema_version"] == 1
    assert len(skills) == 16
    assert {skill["classification"] for skill in skills} <= allowed_classes
    assert {skill["id"] for skill in skills} >= {
        "tradingview",
        "system-ops",
        "tho-operations",
        "paper-trading",
        "trading-brain",
        "gemini-ooda",
    }
    assert all(
        skill["path"].startswith("/Users/aribs/.hermes/skills/sapphire/") for skill in skills
    )
    assert all(skill["next_action"] for skill in skills)

    by_id = {skill["id"]: skill for skill in skills}
    assert by_id["tho-operations"]["secret_posture"]["credential_literal_present"] is True
    assert by_id["tradingview"]["classification"] == "external_mutating"
    assert by_id["system-ops"]["classification"] == "local_mutating"

    serialized = json.dumps(inventory)
    assert "4832" not in serialized
    assert "X-Admin-Token" not in serialized


def test_classification_report_tracks_absorb_and_archive_candidates() -> None:
    report = _classification_report()
    manifest_ids = {repo["id"] for repo in _manifest()["repos"]}

    assert report["schema_version"] == 1
    assert report["source_manifest"] == "infra/org-repos.yaml"
    assert {item["id"] for item in report["candidate_absorb"]} <= manifest_ids
    assert {item["id"] for item in report["candidate_absorb"]} >= {
        "kimi-tools",
        "tradingview-mcp-v2",
    }
    assert report["candidate_archive"]["approved"] == []
    assert "Do not delete" in " ".join(report["candidate_archive"]["policy"])
    assert report["upstream_integration_fleet"]["source_manifest_section"] == "upstream_repos"
    assert set(report["upstream_integration_fleet"]["tracked"]) >= {
        "openbb",
        "kronos",
        "lumo-api-v2",
        "foundry-platform-python",
    }
    assert "agentic-arigato" in report["active_repos"]["integration"]
    assert "org-platform" in report["active_repos"]["satellite"]
    assert "agentic-arigato" not in {item["id"] for item in report["blocked_or_watch"]}
    assert "crypto-tax-tracker" not in {item["id"] for item in report["blocked_or_watch"]}
    assert "crypto-tax-tracker" not in {item["id"] for item in report["next_reviews"]}
    assert "hermes-agent" not in {item["id"] for item in report["next_reviews"]}
    assert report["next_reviews"] == []


def test_collect_status_no_external_handles_local_ci_without_live_tools(tmp_path: Path) -> None:
    manifest = deepcopy(_manifest())
    for repo in manifest["repos"]:
        repo["local_path"] = str(tmp_path / repo["id"])
    for repo in manifest["upstream_repos"]:
        repo["local_path"] = str(tmp_path / "upstream" / repo["id"])

    report = org_status.collect_status(manifest, external=False)

    assert report["schema_version"] == 1
    assert report["summary"]["repo_count"] == len(manifest["repos"])
    assert report["summary"]["upstream_repo_count"] == len(manifest["upstream_repos"])
    assert "repo_classifications" in report["summary"]
    assert report["summary"]["ci_strategies"]["sapphire_self_hosted_gate"] == 1
    assert report["summary"]["ci_strategies"]["draft_auto_deploy"] == 1
    assert report["summary"]["open_prs_checked"] is False
    assert "worktree_count" in report["summary"]
    assert "dirty_worktrees" in report["summary"]
    assert isinstance(report["worktrees"], list)
    assert report["summary"]["hermes_skill_classes"]["read_only"] == 10
    assert report["summary"]["hermes_production_adjacent_skills"] == 10
    assert sorted(report["summary"]["missing_local_repos"]) == sorted(
        repo["id"] for repo in manifest["repos"]
    )
    assert sorted(report["summary"]["upstream_missing_local_repos"]) == sorted(
        repo["id"] for repo in manifest["upstream_repos"]
    )
    assert report["summary"]["dirty_repos"] == []
    assert report["summary"]["upstream_dirty_repos"] == []
    assert report["hermes_skills"]["skill_count"] == 16
    assert len(report["gcp_projects"]) == len(manifest["gcp_projects"])
    assert report["local_runtime"]["docker"]["checked"] is False
    assert all(row["status"] == "not_checked" for row in report["local_runtime"]["launchagents"])


def test_render_markdown_includes_control_board_sections() -> None:
    report = org_status.collect_status(_manifest(), external=False)

    markdown = org_status.render_markdown(report)

    assert "# Sapphire Autonomous Org Status" in markdown
    assert "## Summary" in markdown
    assert "## Repos" in markdown
    assert "## Active Worktrees" in markdown
    assert "## Upstream Integration Fleet" in markdown
    assert "## Hermes Skills" in markdown
    assert "## Waves" in markdown
    assert "- Open PRs: not checked (--no-external)" in markdown
    assert "- CI strategies:" in markdown
    assert "| sapphire | core |" in markdown
    # Branch name is intentionally not pinned: this test runs from any local
    # checkout, including feature branches. Confirm the row shape (class, CI
    # strategy, command-repo state) without hard-coding the branch label.
    sapphire_row = next(
        line for line in markdown.splitlines() if line.startswith("| sapphire | core |")
    )
    assert "sapphire_self_hosted_gate" in sapphire_row
    assert "command_repo" in sapphire_row
    assert "| openbb | OpenBB-finance/OpenBB | arigatoexpress/OpenBB |" in markdown
    assert "| tradingview | external_mutating | yes |" in markdown


def test_dirty_summary_counts_porcelain_without_paths() -> None:
    summary = org_status.summarize_dirty_lines(
        [
            " M README.md",
            "A  docs/new.md",
            " D old.txt",
            "R  old.py -> new.py",
            "?? scratch.env",
            "UU conflict.py",
        ]
    )

    assert summary == {
        "entries": 6,
        "tracked": 5,
        "modified": 1,
        "added": 1,
        "deleted": 1,
        "renamed": 1,
        "copied": 0,
        "untracked": 1,
        "ignored": 0,
        "unmerged": 1,
        "other": 0,
    }


def test_render_markdown_dirty_summary_is_sanitized() -> None:
    report = org_status.collect_status(_manifest(), external=False)
    repo = next(row for row in report["repos"] if row["id"] == "sapphire")
    repo["dirty_count"] = 2
    repo["clean"] = False
    repo["dirty_summary"] = org_status.summarize_dirty_lines(
        [" M docs/control.md", "?? scratch.env"]
    )
    report["summary"]["dirty_repos"] = ["sapphire"]

    markdown = org_status.render_markdown(report)

    assert "## Dirty Repo Summary" in markdown
    assert "| sapphire | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 0 |" in markdown
    assert "scratch.env" not in markdown
    assert "docs/control.md" not in markdown


def test_parse_worktree_porcelain_maps_active_lanes() -> None:
    output = "\n".join(
        [
            "worktree /Users/aribs/Code/Sapphire",
            "HEAD 23c572cb8fd7e492430bbd61df7eb5af527d8eb0",
            "branch refs/heads/main",
            "",
            "worktree /Users/aribs/Code/_worktrees/sapphire-lane",
            "HEAD b3e045565d86030aaa6438dd5ab6485959a346a7",
            "branch refs/heads/feat/sapphire-lane",
            "locked by operator",
            "",
        ]
    )

    assert org_status.parse_worktree_porcelain(output) == [
        {
            "path": "/Users/aribs/Code/Sapphire",
            "head": "23c572cb8fd7",
            "branch": "main",
        },
        {
            "path": "/Users/aribs/Code/_worktrees/sapphire-lane",
            "head": "b3e045565d86",
            "branch": "feat/sapphire-lane",
            "locked": "by operator",
        },
    ]


def test_render_markdown_worktree_summary_is_sanitized() -> None:
    report = org_status.collect_status(_manifest(), external=False)
    report["worktrees"] = [
        {
            "path": "/Users/aribs/Code/_worktrees/sapphire-secret-lane",
            "branch": "feat/secret-lane",
            "upstream": "origin/main",
            "clean": False,
            "dirty_count": 1,
            "dirty_summary": org_status.summarize_dirty_lines(["?? scratch.env"]),
            "head": "abc123",
        }
    ]
    report["summary"]["worktree_count"] = 1
    report["summary"]["dirty_worktrees"] = ["feat/secret-lane"]

    markdown = org_status.render_markdown(report)

    assert "## Active Worktrees" in markdown
    assert "| /Users/aribs/Code/_worktrees/sapphire-secret-lane | feat/secret-lane |" in markdown
    assert "- Dirty worktrees: feat/secret-lane" in markdown
    assert "scratch.env" not in markdown


def test_parse_launchctl_maps_pid_and_last_status() -> None:
    output = "\n".join(
        [
            "PID\tStatus\tLabel",
            "-\t0\tcom.sapphire.threat-refresh",
            "123\t0\tcom.sapphire.dashboard",
            "48423\t-15\tai.hermes.gateway",
        ]
    )

    parsed = org_status.parse_launchctl(output)

    assert parsed["com.sapphire.threat-refresh"] == {
        "loaded": True,
        "pid": None,
        "last_status": 0,
    }
    assert parsed["com.sapphire.dashboard"]["pid"] == 123
    assert parsed["ai.hermes.gateway"]["last_status"] == -15


def test_status_json_shape_omits_secret_payloads() -> None:
    report = org_status.collect_status(_manifest(), external=False)

    serialized = json.dumps(report)

    assert "Secret Manager" not in serialized
    assert "PRIVATE KEY" not in serialized
    assert "BEGIN RSA" not in serialized
    assert "token=" not in serialized.lower()
