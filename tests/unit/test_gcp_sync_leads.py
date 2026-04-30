from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_gcp_sync(monkeypatch: pytest.MonkeyPatch):
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_storage = types.ModuleType("google.cloud.storage")
    fake_cloud.bigquery = fake_bigquery
    fake_cloud.storage = fake_storage

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", fake_storage)

    module_name = "gcp_sync_leads_test"
    module_path = ROOT / "services" / "pipeline" / "gcp_sync.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_transform_leads_supports_houston_jsonl(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    store = tmp_path / "houston_leads.jsonl"
    store.write_text(
        json.dumps(
            {
                "id": "311:100",
                "source": "311",
                "address": "100 Main St, Houston, TX 77002",
                "zip": "77002",
                "type": "Foundation Concern",
                "score": 94,
                "urgency": "high",
                "created_at": "2026-04-30T12:00:00+00:00",
                "raw_data": {"city": "Houston", "owner": "Owner Name"},
            }
        )
        + "\nnot-json\n",
        encoding="utf-8",
    )

    rows = list(gcp_sync.transform_leads([store]))

    assert len(rows) == 1
    row = rows[0]
    assert row["lead_id"] == "311:100"
    assert row["city"] == "Houston"
    assert row["state"] == "TX"
    assert row["grade"] == "A"
    assert row["status"] == "LEAD"
    assert row["permit_type"] == "Foundation Concern"
    assert row["owner_name"] == "Owner Name"
    assert row["timestamp"] == "2026-04-30T12:00:00+00:00"


def test_transform_leads_keeps_legacy_pipeline_json(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    legacy = tmp_path / "pipeline_20260430.json"
    legacy.write_text(
        json.dumps(
            {
                "generated_at": "20260430_0900",
                "leads": [
                    {
                        "id": "legacy:1",
                        "address": "1 Legacy Way",
                        "score": 0.7,
                        "grade": "B",
                        "status": "LEAD",
                        "source": "legacy",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = list(gcp_sync.transform_leads([legacy]))

    assert len(rows) == 1
    assert rows[0]["lead_id"] == "legacy:1"
    assert rows[0]["grade"] == "B"
    assert rows[0]["timestamp"] == "2026-04-30T09:00:00+00:00"


def test_discover_files_accepts_multiple_patterns(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    data_dir = tmp_path / "data"
    leads_dir = data_dir / "leads"
    leads_dir.mkdir(parents=True)
    pipeline = leads_dir / "pipeline_20260430.json"
    houston = leads_dir / "houston_leads.jsonl"
    geocache = leads_dir / "geocache.json"
    pipeline.write_text("{}", encoding="utf-8")
    houston.write_text("{}", encoding="utf-8")
    geocache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gcp_sync, "DATA_DIR", data_dir)

    discovered = gcp_sync._discover_files(gcp_sync.SOURCES["leads"].glob, since_mtime=0)

    assert discovered == [houston, pipeline]
