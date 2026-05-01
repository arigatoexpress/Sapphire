"""Tests for scripts/ops/compare_threat_artifacts.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "compare_threat_artifacts.py"
SPEC = importlib.util.spec_from_file_location("compare_threat_artifacts", SCRIPT)
assert SPEC and SPEC.loader
comparator = importlib.util.module_from_spec(SPEC)
sys.modules["compare_threat_artifacts"] = comparator
SPEC.loader.exec_module(comparator)


def test_matching_threats_pass_and_write_reports(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.json", _artifact([_threat("CVE-2026-0001", score=9.1)]))
    remote = _write(tmp_path / "remote.json", _artifact([_threat("CVE-2026-0001", score=9.5)]))
    report_dir = tmp_path / "reports"

    exit_code = comparator.main(
        ["--local", str(local), "--remote", str(remote), "--report-out", str(report_dir), "--quiet"]
    )

    assert exit_code == 0
    reports = sorted(
        path
        for path in report_dir.glob("threat-shadow-comparison-*")
        if not path.name.endswith(".envelope.json")
    )
    assert {path.suffix for path in reports} == {".json", ".md"}
    payload = json.loads(next(path for path in reports if path.suffix == ".json").read_text())
    assert payload["verdict"] == "PASS"
    assert payload["summary"]["rows_compared"] == 1
    assert sorted(path.name for path in report_dir.glob("*.envelope.json")) == sorted(
        f"{path.name}.envelope.json" for path in reports
    )


def test_small_asymmetric_id_set_warns_and_strict_fails(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.json", _artifact([_threat("CVE-2026-0001")]))
    remote = _write(
        tmp_path / "remote.json",
        _artifact([_threat("CVE-2026-0001"), _threat("CVE-2026-0002")]),
    )
    args = [
        "--local",
        str(local),
        "--remote",
        str(remote),
        "--report-out",
        str(tmp_path / "reports"),
        "--quiet",
    ]

    assert comparator.main(args) == 10
    assert comparator.main([*args, "--strict"]) == 20


def test_large_asymmetric_id_set_fails(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.json", _artifact([_threat("CVE-2026-0001")]))
    remote = _write(
        tmp_path / "remote.json",
        _artifact(
            [
                _threat("CVE-2026-0001"),
                _threat("CVE-2026-0002"),
                _threat("CVE-2026-0003"),
                _threat("CVE-2026-0004"),
            ]
        ),
    )

    assert comparator.main(["--local", str(local), "--remote", str(remote), "--quiet"]) == 20


def test_stable_field_drift_fails(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.json", _artifact([_threat("CVE-2026-0001")]))
    changed = _threat("CVE-2026-0001")
    changed["title"] = "Different title"
    remote = _write(tmp_path / "remote.json", _artifact([changed]))

    assert comparator.main(["--local", str(local), "--remote", str(remote), "--quiet"]) == 20


def test_malformed_threats_schema_is_config_error(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.json", {"refreshed_at": "2026-04-25T00:00:00Z"})
    remote = _write(tmp_path / "remote.json", _artifact([_threat("CVE-2026-0001")]))

    assert comparator.main(["--local", str(local), "--remote", str(remote), "--quiet"]) == 78


def test_nearest_run_snapshot_selection_writes_selection_metadata(tmp_path: Path) -> None:
    local_root = tmp_path / "local-intel"
    remote_root = tmp_path / "remote-artifact"
    _write_run(
        local_root,
        "20260426T010000Z",
        _artifact([_threat("CVE-2026-OLD")]),
    )
    _write_run(
        local_root,
        "20260426T170350Z",
        _artifact([_threat("CVE-2026-0001")]),
    )
    _write_run(
        remote_root / "data" / "intelligence",
        "20260426T170422Z",
        _artifact([_threat("CVE-2026-0001")]),
    )
    report_dir = tmp_path / "reports"

    exit_code = comparator.main(
        [
            "--local-root",
            str(local_root),
            "--remote-root",
            str(remote_root),
            "--report-out",
            str(report_dir),
            "--quiet",
        ]
    )

    assert exit_code == 0
    payload = json.loads(
        next(
            path for path in report_dir.glob("*.json") if not path.name.endswith(".envelope.json")
        ).read_text()
    )
    assert payload["selection"]["mode"] == "nearest_run_snapshot"
    assert payload["selection"]["local"]["run_timestamp"] == "2026-04-26T17:03:50Z"
    assert payload["selection"]["remote"]["run_timestamp"] == "2026-04-26T17:04:22Z"
    assert payload["selection"]["time_skew_seconds"] == 32.0
    assert payload["summary"]["missing_in_local"] == []
    assert payload["summary"]["missing_in_remote"] == []


def test_nearest_run_snapshot_rejects_stale_pairing(tmp_path: Path) -> None:
    local_root = tmp_path / "local-intel"
    remote_root = tmp_path / "remote-artifact"
    _write_run(local_root, "20260426T010000Z", _artifact([_threat("CVE-2026-0001")]))
    _write_run(remote_root, "20260426T030000Z", _artifact([_threat("CVE-2026-0001")]))

    exit_code = comparator.main(
        [
            "--local-root",
            str(local_root),
            "--remote-root",
            str(remote_root),
            "--max-skew-minutes",
            "15",
            "--quiet",
        ]
    )

    assert exit_code == 64


def _artifact(threats: list[dict]) -> dict:
    return {
        "refreshed_at": "2026-04-25T00:00:00+00:00",
        "source_count": len(threats),
        "threats": threats,
    }


def _threat(canonical_id: str, *, score: float = 9.1) -> dict:
    return {
        "canonical_id": canonical_id,
        "source": "nvd",
        "source_type": "cve",
        "title": f"{canonical_id} synthetic advisory",
        "url": f"https://example.invalid/{canonical_id}",
        "published_at": "2026-04-25T00:00:00Z",
        "summary": "Synthetic vulnerability summary for shadow comparison.",
        "score": score,
        "exploited": False,
        "tags": ["synthetic", "test"],
        "evidence": [{"label": "NVD", "url": f"https://example.invalid/{canonical_id}"}],
        "metadata": {},
    }


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_run(root: Path, stamp: str, payload: dict) -> Path:
    return _write(root / "runs" / stamp / "threats.json", payload)
