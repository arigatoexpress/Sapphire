"""Tests for content-engine artifact comparison."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "compare_content_artifacts.py"

SPEC = importlib.util.spec_from_file_location("compare_content_artifacts", SCRIPT)
assert SPEC and SPEC.loader
compare_content_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules["compare_content_artifacts"] = compare_content_artifacts
SPEC.loader.exec_module(compare_content_artifacts)


def _write_manifest(
    root: Path,
    *,
    kind: str = "weekly_crypto_brief",
    platform: str = "linkedin",
    quality_passed: bool = True,
    body: str = "BTC at $65000. ETH at $3200. SOL at $150.",
) -> Path:
    drafts = root / "data" / "content" / "drafts"
    ready = root / "data" / "content" / "ready" / platform
    drafts.mkdir(parents=True, exist_ok=True)
    ready.mkdir(parents=True, exist_ok=True)
    rendering_path = ready / f"20260426_0600_{kind}.md"
    rendering_path.write_text(body)
    manifest = {
        "report": {
            "kind": kind,
            "title": "Sapphire Weekly Crypto Brief - 2026-04-26",
            "generated_at": "2026-04-26T12:00:00+00:00",
            "facts": {"count": 3},
            "body": body,
            "sources": ["data/trading_predictions.jsonl"],
            "tags": ["crypto"],
        },
        "renderings": {
            platform: {
                "path": f"data/content/ready/{platform}/20260426_0600_{kind}.md",
                "quality": {
                    "passed": quality_passed,
                    "reasons": [] if quality_passed else ["too_short"],
                },
            }
        },
        "published_at": "2026-04-26T12:00:00",
    }
    path = drafts / f"20260426_0600_{kind}.json"
    path.write_text(json.dumps(manifest))
    return path


def test_identical_content_artifacts_pass(tmp_path: Path) -> None:
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_manifest(local)
    _write_manifest(remote)

    report = compare_content_artifacts.compare_manifest_sets(
        local=compare_content_artifacts.latest_manifests_by_kind(local),
        remote=compare_content_artifacts.latest_manifests_by_kind(remote),
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["rows_pass"] == 1


def test_remote_quality_failure_when_local_passes_fails(tmp_path: Path) -> None:
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_manifest(local, quality_passed=True)
    _write_manifest(remote, quality_passed=False)

    report = compare_content_artifacts.compare_manifest_sets(
        local=compare_content_artifacts.latest_manifests_by_kind(local),
        remote=compare_content_artifacts.latest_manifests_by_kind(remote),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["rows_fail"] == 1


def test_matching_quality_failure_is_warn_not_fail(tmp_path: Path) -> None:
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_manifest(local, quality_passed=False)
    _write_manifest(remote, quality_passed=False)

    report = compare_content_artifacts.compare_manifest_sets(
        local=compare_content_artifacts.latest_manifests_by_kind(local),
        remote=compare_content_artifacts.latest_manifests_by_kind(remote),
    )

    assert report["verdict"] == "WARN"
    assert report["summary"]["rows_warn"] == 1


def test_missing_remote_kind_fails(tmp_path: Path) -> None:
    local = tmp_path / "local"
    remote = tmp_path / "remote"
    _write_manifest(local, kind="weekly_crypto_brief")
    _write_manifest(local, kind="market_pulse")
    _write_manifest(remote, kind="weekly_crypto_brief")

    report = compare_content_artifacts.compare_manifest_sets(
        local=compare_content_artifacts.latest_manifests_by_kind(local),
        remote=compare_content_artifacts.latest_manifests_by_kind(remote),
    )

    assert report["verdict"] == "FAIL"
    assert report["summary"]["missing_in_remote"] == ["market_pulse"]
