"""Tests for the issue #393 threat-intel readiness helper."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_OPS = ROOT / "scripts" / "ops"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_OPS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_OPS))

import dependabot_alerts_fetch as dependabot_fetcher  # noqa: E402
import threat_intel_issue_393_readiness as readiness  # noqa: E402


def test_collect_dependency_names_reads_requirements_and_pyproject(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text(
        "requests==2.32.0\n# comment\n-e git+ssh://example.invalid/repo\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = ["cryptography>=42", "pydantic[email]>=2"]

[project.optional-dependencies]
dev = ["pytest>=8"]
""",
        encoding="utf-8",
    )

    assert readiness.collect_dependency_names(tmp_path) == [
        "cryptography",
        "pydantic",
        "pytest",
        "requests",
    ]


def test_classify_kev_candidates_marks_dependency_matches():
    payload = {
        "vulnerabilities": [
            {
                "cveID": "CVE-1",
                "vendorProject": "Example",
                "product": "Cryptography Toolkit",
                "vulnerabilityName": "Cryptography flaw",
                "dateAdded": "2026-04-27",
                "knownRansomwareCampaignUse": "Unknown",
                "requiredAction": "Patch",
            },
            {
                "cveID": "CVE-2",
                "vendorProject": "JetBrains",
                "product": "TeamCity",
                "vulnerabilityName": "TeamCity flaw",
                "dateAdded": "2026-04-20",
                "knownRansomwareCampaignUse": "Known",
                "requiredAction": "Patch",
            },
            {
                "cveID": "CVE-3",
                "vendorProject": "Old",
                "product": "Product",
                "dateAdded": "2025-01-01",
                "knownRansomwareCampaignUse": "Unknown",
                "requiredAction": "Patch",
            },
        ]
    }

    out = readiness.classify_kev_candidates(
        payload,
        ["cryptography", "requests"],
        as_of=date(2026, 4, 28),
    )

    assert out["catalog_count"] == 3
    assert out["reported_candidates_count"] == 2
    assert out["sapphire_relevant_reported_count"] == 1
    assert out["reported_candidates"][0]["cveID"] == "CVE-1"
    assert out["reported_candidates"][0]["matched_dependencies"] == ["cryptography"]


def test_deployment_footprint_ignores_docs_and_reports_config_matches(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "handoff.md").write_text(
        "PaperCut TeamCity Exchange Server Cisco FMC", encoding="utf-8"
    )
    infra = tmp_path / "infra"
    infra.mkdir()
    (infra / "ci.yaml").write_text("runner: teamcity\n", encoding="utf-8")

    summary = readiness.summarize_deployment_footprint(tmp_path)
    by_product = {item["product"]: item for item in summary}

    assert by_product["JetBrains TeamCity"]["status"] == "present_in_repo_config_evidence"
    assert by_product["JetBrains TeamCity"]["matches"] == [
        {"path": "infra/ci.yaml", "line": 1, "matched_alias": "teamcity"}
    ]
    assert by_product["PaperCut NG/MF"]["status"] == "absent_by_repo_config_evidence"
    assert by_product["Microsoft Exchange Server"]["status"] == "absent_by_repo_config_evidence"
    assert (
        by_product["Cisco Secure Firewall Management Center (FMC)"]["status"]
        == "absent_by_repo_config_evidence"
    )


def test_build_report_recommends_close_when_all_checks_clear(monkeypatch, tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.0\n", encoding="utf-8")
    payload = {
        "vulnerabilities": [
            {
                "cveID": "CVE-TEAMCITY",
                "vendorProject": "JetBrains",
                "product": "TeamCity",
                "dateAdded": "2026-04-20",
                "knownRansomwareCampaignUse": "Known",
                "requiredAction": "Patch",
            }
        ]
    }

    monkeypatch.setattr(
        readiness,
        "fetch_dependabot_status",
        lambda repo: {"status": "available", "critical_high_open": 0},
    )

    report = readiness.build_report(
        root=tmp_path,
        repo="acme/repo",
        kev_payload=payload,
        as_of=date(2026, 4, 28),
    )

    assert report["readiness"]["ready_to_comment"] is True
    assert report["readiness"]["ready_to_close"] is True
    assert report["kev"]["sapphire_relevant_reported_count"] == 0


def test_build_report_keeps_close_false_when_dependabot_unavailable(monkeypatch, tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.0\n", encoding="utf-8")
    payload = {"vulnerabilities": []}

    monkeypatch.setattr(
        readiness,
        "fetch_dependabot_status",
        lambda repo: {
            "status": "unavailable",
            "reason": "gh api failed",
            "critical_high_open": None,
        },
    )

    report = readiness.build_report(
        root=tmp_path,
        repo="acme/repo",
        kev_payload=payload,
        as_of=date(2026, 4, 28),
    )

    assert report["readiness"]["ready_to_comment"] is True
    assert report["readiness"]["ready_to_close"] is False
    assert (
        report["readiness"]["recommendation"] == "comment_with_evidence_ghas_unavailable_or_nonzero"
    )


def test_fetch_dependabot_status_sanitizes_unavailable_errors(monkeypatch):
    def fail(repo):
        raise dependabot_fetcher.DependabotFetchError("bad ghp_secretvalue")

    monkeypatch.setattr(dependabot_fetcher, "fetch_and_render", fail)

    out = readiness.fetch_dependabot_status("acme/repo")

    assert out["status"] == "unavailable"
    assert "<redacted-token>" in out["reason"]
    assert "ghp_secretvalue" not in out["reason"]


def test_main_can_render_markdown_with_fixture(tmp_path: Path, capsys):
    (tmp_path / "requirements.txt").write_text("requests==2.32.0\n", encoding="utf-8")
    kev_path = tmp_path / "kev.json"
    kev_path.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")

    rc = readiness.main(
        [
            "--repo-root",
            str(tmp_path),
            "--kev-json",
            str(kev_path),
            "--as-of",
            "2026-04-28",
            "--skip-ghas",
            "--markdown-only",
        ]
    )

    assert rc == 0
    assert "Issue #393 readiness evidence" in capsys.readouterr().out
