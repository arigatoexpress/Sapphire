from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BLANGA_SRC = ROOT / "clients" / "blanga" / "src"


def _load_module(monkeypatch: pytest.MonkeyPatch, module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_blanga_gcs(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("bis")
    package.__path__ = [str(BLANGA_SRC / "bis")]
    monkeypatch.setitem(sys.modules, "bis", package)
    settings_module = _load_module(
        monkeypatch,
        "bis.settings",
        BLANGA_SRC / "bis" / "settings.py",
    )
    gcs_module = _load_module(
        monkeypatch,
        "bis.gcs_persistence",
        BLANGA_SRC / "bis" / "gcs_persistence.py",
    )
    return settings_module.BISSettings, gcs_module


def _settings(
    settings_cls,
    bucket: str = "test-bucket",
    blob: str = "snapshots/latest.json",
):
    return settings_cls(
        environment="test",
        require_auth=False,
        app_password="",
        app_username="blanga",
        project_id="local",
        backup_dir="/tmp/blanga-test",
        autosave_snapshots=True,
        gcs_snapshot_bucket=bucket,
        gcs_snapshot_blob=blob,
        default_spreadsheet_id="",
        sheets_new_properties_tab="new",
        sheets_property_updates_tab="updates",
        sheets_notes_tab="notes",
        sheets_input_tab="input",
        sheets_computed_tab="computed",
        sheets_master_view_tab="master",
        sheets_reviews_tab="reviews",
        sheets_change_log_tab="changes",
        sheets_today_tasks_tab="today",
    )


class FakeBlob:
    def __init__(
        self,
        *,
        exists: bool = True,
        downloaded: dict[str, Any] | None = None,
        updated: datetime | None = None,
    ) -> None:
        self._exists = exists
        self._downloaded = downloaded or {"ok": True}
        self.updated = updated
        self.size = 123
        self.exists_client = None
        self.reload_client = None
        self.download_client = None
        self.upload_payload = None
        self.upload_content_type = None
        self.upload_from_filename_args = None

    def exists(self, *, client: Any | None = None) -> bool:
        self.exists_client = client
        return self._exists

    def reload(self, *, client: Any | None = None) -> None:
        self.reload_client = client

    def upload_from_string(self, payload: str, *, content_type: str) -> None:
        self.upload_payload = payload
        self.upload_content_type = content_type

    def download_as_bytes(self, *, client: Any | None = None) -> bytes:
        self.download_client = client
        return json.dumps(self._downloaded).encode("utf-8")

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


def _install_fake_storage(
    monkeypatch: pytest.MonkeyPatch,
    gcs_persistence,
    blob: FakeBlob,
) -> FakeClient:
    bucket = FakeBucket(blob)
    client = FakeClient(bucket)
    monkeypatch.setattr(gcs_persistence, "storage", SimpleNamespace(Client=lambda: client))
    return client


def test_gcs_status_reports_unconfigured_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    monkeypatch.setattr(gcs_persistence, "storage", None)

    status = gcs_persistence.gcs_status(_settings(settings_cls, bucket=""))

    assert status == {
        "configured": False,
        "bucket": None,
        "blob": "snapshots/latest.json",
        "client_library_available": False,
        "exists": False,
    }


def test_gcs_status_reads_blob_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    updated = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    blob = FakeBlob(exists=True, updated=updated)
    client = _install_fake_storage(monkeypatch, gcs_persistence, blob)

    status = gcs_persistence.gcs_status(_settings(settings_cls))

    assert status["configured"] is True
    assert status["bucket"] == "test-bucket"
    assert status["blob"] == "snapshots/latest.json"
    assert status["client_library_available"] is True
    assert status["exists"] is True
    assert status["size_bytes"] == 123
    assert status["updated_at"] == "2026-04-27T12:00:00+00:00"
    assert client.requested_bucket == "test-bucket"
    assert client._bucket.requested_blob == "snapshots/latest.json"
    assert blob.exists_client is client
    assert blob.reload_client is client


def test_save_snapshot_to_gcs_uploads_json(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    blob = FakeBlob()
    _install_fake_storage(monkeypatch, gcs_persistence, blob)

    result = gcs_persistence.save_snapshot_to_gcs({"b": 2, "a": 1}, _settings(settings_cls))

    assert result["saved"] is True
    assert result["bucket"] == "test-bucket"
    assert result["blob"] == "snapshots/latest.json"
    assert result["bytes"] == len(blob.upload_payload.encode("utf-8"))
    assert result["saved_at"].endswith("+00:00")
    assert blob.upload_content_type == "application/json"
    assert json.loads(blob.upload_payload) == {"a": 1, "b": 2}


def test_save_snapshot_to_gcs_requires_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    blob = FakeBlob()
    _install_fake_storage(monkeypatch, gcs_persistence, blob)

    with pytest.raises(RuntimeError, match="BIS_GCS_SNAPSHOT_BUCKET"):
        gcs_persistence.save_snapshot_to_gcs({"ok": True}, _settings(settings_cls, bucket=""))


def test_load_snapshot_from_gcs_returns_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    blob = FakeBlob(exists=False)
    client = _install_fake_storage(monkeypatch, gcs_persistence, blob)

    assert gcs_persistence.load_snapshot_from_gcs(_settings(settings_cls)) is None
    assert blob.exists_client is client


def test_load_snapshot_from_gcs_downloads_existing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_cls, gcs_persistence = _load_blanga_gcs(monkeypatch)
    blob = FakeBlob(exists=True, downloaded={"status": "warm"})
    client = _install_fake_storage(monkeypatch, gcs_persistence, blob)

    assert gcs_persistence.load_snapshot_from_gcs(_settings(settings_cls)) == {"status": "warm"}
    assert blob.exists_client is client
    assert blob.download_client is client
