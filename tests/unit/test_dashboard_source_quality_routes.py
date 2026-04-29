"""Dashboard /source-quality routes degrade safely and surface report data."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def _seed_report(tmp_path: Path, report: dict, *, report_date: str = "2026-04-29") -> Path:
    daily = tmp_path / report_date
    daily.mkdir(parents=True)
    report_path = daily / "report.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    return report_path


def _sample_report() -> dict:
    return {
        "schema_version": 1,
        "report_date": "2026-04-29",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "sources_count": 2,
            "samples_total": 12,
            "near_duplicate_pairs": 1,
            "decayed_sources_count": 1,
            "low_sample_sources_count": 0,
        },
        "snr": {
            "alpha": {"source": "alpha", "samples": 6, "precision": 0.9, "recall": 0.85, "f1": 0.875, "true_positives": 5, "false_positives": 1, "true_negatives": 0, "false_negatives": 0, "low_sample": False, "notes": [], "window_start": "", "window_end": ""},
            "beta": {"source": "beta", "samples": 6, "precision": 0.7, "recall": 0.6, "f1": 0.65, "true_positives": 4, "false_positives": 2, "true_negatives": 0, "false_negatives": 0, "low_sample": False, "notes": [], "window_start": "", "window_end": ""},
        },
        "correlation": {
            "sources": ["alpha", "beta"],
            "bucket_minutes": 60,
            "min_overlap": 5,
            "near_duplicate_threshold": 0.87,
            "pairs": [
                {"source_a": "alpha", "source_b": "beta", "overlap": 6, "agreements": 6, "conflicts": 0, "agreement_rate": 1.0, "conflict_rate": 0.0, "near_duplicate": True}
            ],
            "near_duplicates": [
                {"source_a": "alpha", "source_b": "beta", "agreement_rate": 1.0, "near_duplicate": True}
            ],
            "notes": [],
        },
        "near_duplicates": [
            {"source_a": "alpha", "source_b": "beta", "agreement_rate": 1.0, "near_duplicate": True}
        ],
        "decay": {
            "threshold": 0.15,
            "recent_days": 14,
            "window_hours": 24,
            "alerts": [
                {"source": "alpha", "baseline_f1": 0.875, "recent_f1": 0.5, "delta": 0.375, "baseline_samples": 6, "recent_samples": 6, "decay": True, "low_sample": False, "notes": []}
            ],
            "decayed_sources": ["alpha"],
            "notes": [],
        },
        "read_only": True,
    }


def test_source_quality_page_requires_auth(client):
    response = client.get("/source-quality")

    assert response.status_code == 401


def test_source_quality_page_renders_template_with_auth(client):
    response = client.get("/source-quality", headers=_auth_header())

    assert response.status_code == 200
    assert b"Source Quality" in response.data


def test_api_snr_returns_no_data_when_no_report(client, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-snr", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "no_data"
    assert payload["snr"] == {}


def test_api_snr_returns_seeded_report(client, tmp_path, monkeypatch):
    _seed_report(tmp_path, _sample_report())
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-snr", headers=_auth_header())

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "alpha" in payload["snr"]
    assert payload["snr"]["alpha"]["f1"] == pytest.approx(0.875)
    assert "alpha" in payload["sources"]


def test_api_correlation_surfaces_near_duplicates(client, tmp_path, monkeypatch):
    _seed_report(tmp_path, _sample_report())
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-correlation", headers=_auth_header())

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["correlation"]["pairs"][0]["near_duplicate"] is True
    assert len(payload["near_duplicates"]) == 1


def test_api_decay_surfaces_decayed_sources(client, tmp_path, monkeypatch):
    _seed_report(tmp_path, _sample_report())
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-decay", headers=_auth_header())

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["decayed_sources"] == ["alpha"]
    assert payload["decay"]["alerts"][0]["decay"] is True


def test_api_endpoints_all_require_auth(client):
    for path in (
        "/api/source-quality-snr",
        "/api/source-quality-correlation",
        "/api/source-quality-decay",
    ):
        response = client.get(path)

        assert response.status_code == 401, path


def test_api_falls_back_when_report_unreadable(client, tmp_path, monkeypatch):
    bad_dir = tmp_path / "2026-04-29"
    bad_dir.mkdir()
    (bad_dir / "report.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-snr", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    # malformed → treated as "no data"
    assert payload["status"] == "no_data"
    assert payload["snr"] == {}


def test_api_picks_newest_dated_report(client, tmp_path, monkeypatch):
    older = _sample_report()
    older["report_date"] = "2026-04-01"
    older["summary"]["samples_total"] = 1
    newer = _sample_report()
    newer["report_date"] = "2026-04-29"
    newer["summary"]["samples_total"] = 999
    _seed_report(tmp_path, older, report_date="2026-04-01")
    _seed_report(tmp_path, newer, report_date="2026-04-29")
    monkeypatch.setattr(dashboard_app, "_SOURCE_QUALITY_REPORT_ROOT", tmp_path)

    response = client.get("/api/source-quality-snr", headers=_auth_header())

    payload = response.get_json()
    assert payload["report_date"] == "2026-04-29"
    assert payload["summary"]["samples_total"] == 999
