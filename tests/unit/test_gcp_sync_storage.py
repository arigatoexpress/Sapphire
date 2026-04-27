from __future__ import annotations

import importlib.util
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

    module_name = "gcp_sync_storage_test"
    module_path = ROOT / "services" / "pipeline" / "gcp_sync.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeBlob:
    def __init__(self) -> None:
        self.upload_from_filename_args = None

    def upload_from_filename(self, filename: str, *, content_type: str) -> None:
        self.upload_from_filename_args = (filename, content_type)


class FakeBucket:
    def __init__(self, blob: FakeBlob) -> None:
        self._blob = blob
        self.requested_blob = None

    def blob(self, name: str) -> FakeBlob:
        self.requested_blob = name
        return self._blob


class FakeClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self._bucket = bucket
        self.requested_bucket = None

    def bucket(self, name: str) -> FakeBucket:
        self.requested_bucket = name
        return self._bucket


def test_upload_to_gcs_uses_ndjson_content_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gcp_sync = _load_gcp_sync(monkeypatch)
    local = tmp_path / "signals.ndjson"
    local.write_text('{"ok": true}\n')
    blob = FakeBlob()
    bucket = FakeBucket(blob)
    client = FakeClient(bucket)

    uri = gcp_sync._upload_to_gcs(client, local, "raw/signals/signals.ndjson")

    assert uri == "gs://sapphire-data-lake/raw/signals/signals.ndjson"
    assert client.requested_bucket == "sapphire-data-lake"
    assert bucket.requested_blob == "raw/signals/signals.ndjson"
    assert blob.upload_from_filename_args == (str(local), "application/x-ndjson")
