from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_gcs_to_bq(monkeypatch: pytest.MonkeyPatch):
    fake_functions = types.ModuleType("functions_framework")
    fake_functions.cloud_event = lambda func: func
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_cloud.bigquery = fake_bigquery

    monkeypatch.setitem(sys.modules, "functions_framework", fake_functions)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)

    module_name = "gcs_to_bq_mapping_test"
    module_path = ROOT / "infra" / "gcp" / "cloud_functions" / "gcs_to_bq" / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fred_raw_path_maps_to_fred_table(monkeypatch):
    module = _load_gcs_to_bq(monkeypatch)

    assert (
        module._resolve_table("raw/fred/2026-01-05/fred_123.ndjson") == "fred_series_observations"
    )
    assert module._resolve_table("raw/missing/2026-01-05/file.ndjson") is None
