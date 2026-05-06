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

    module_name = "gcp_sync_fred_test"
    module_path = ROOT / "services" / "pipeline" / "gcp_sync.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_transform_fred_observations_skips_bad_rows(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    store = tmp_path / "fred_observations.jsonl"
    store.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "obs-1",
                        "series_id": "dff",
                        "observation_date": "2026-01-02",
                        "value": 4.33,
                        "realtime_start": "2026-01-01",
                        "realtime_end": "2026-01-31",
                        "units": "lin",
                        "frequency": "Daily",
                        "source_url": "https://api.stlouisfed.org/fred/series/observations",
                        "payload_hash": "h" * 64,
                        "ingested_at": "2026-01-05T00:00:00+00:00",
                    }
                ),
                "not-json",
                json.dumps({"series_id": "DGS10"}),
            ]
        ),
        encoding="utf-8",
    )

    rows = list(gcp_sync.transform_fred_observations([store]))

    assert rows == [
        {
            "observation_id": "obs-1",
            "series_id": "DFF",
            "observation_date": "2026-01-02",
            "value": 4.33,
            "realtime_start": "2026-01-01",
            "realtime_end": "2026-01-31",
            "units": "lin",
            "frequency": "Daily",
            "source_url": "https://api.stlouisfed.org/fred/series/observations",
            "payload_hash": "h" * 64,
            "ingested_at": "2026-01-05T00:00:00+00:00",
        }
    ]


def test_fred_source_discovers_macro_artifacts(monkeypatch, tmp_path):
    gcp_sync = _load_gcp_sync(monkeypatch)
    data_dir = tmp_path / "data"
    macro_dir = data_dir / "macro" / "2026-01-05"
    macro_dir.mkdir(parents=True)
    fred = macro_dir / "fred_observations.jsonl"
    events = macro_dir / "events.jsonl"
    fred.write_text("{}", encoding="utf-8")
    events.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gcp_sync, "DATA_DIR", data_dir)

    discovered = gcp_sync._discover_files(gcp_sync.SOURCES["fred"].glob, since_mtime=0)

    assert discovered == [fred]
