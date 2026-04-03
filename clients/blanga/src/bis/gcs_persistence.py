from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from bis.settings import BISSettings

try:
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover
    storage = None  # type: ignore


def gcs_snapshot_configured(settings: BISSettings) -> bool:
    return bool(settings.gcs_snapshot_bucket.strip())


def _client() -> storage.Client:
    if storage is None:
        raise RuntimeError("google-cloud-storage is not installed")
    return storage.Client()


def gcs_status(settings: BISSettings) -> dict[str, Any]:
    configured = gcs_snapshot_configured(settings)
    status: dict[str, Any] = {
        "configured": configured,
        "bucket": settings.gcs_snapshot_bucket or None,
        "blob": settings.gcs_snapshot_blob,
        "client_library_available": storage is not None,
    }
    if not configured or storage is None:
        status["exists"] = False
        return status

    try:
        client = _client()
        blob = client.bucket(settings.gcs_snapshot_bucket).blob(settings.gcs_snapshot_blob)
        exists = blob.exists(client=client)
        status["exists"] = exists
        if exists:
            blob.reload(client=client)
            status["size_bytes"] = blob.size
            status["updated_at"] = (
                blob.updated.astimezone(UTC).isoformat() if getattr(blob, "updated", None) else None
            )
    except Exception as exc:
        status["error"] = str(exc)
    return status


def save_snapshot_to_gcs(snapshot: dict[str, Any], settings: BISSettings) -> dict[str, Any]:
    if not gcs_snapshot_configured(settings):
        raise RuntimeError("BIS_GCS_SNAPSHOT_BUCKET is not configured")
    client = _client()
    bucket = client.bucket(settings.gcs_snapshot_bucket)
    blob = bucket.blob(settings.gcs_snapshot_blob)
    payload = json.dumps(snapshot, indent=2, sort_keys=True)
    blob.upload_from_string(payload, content_type="application/json")
    return {
        "saved": True,
        "bucket": settings.gcs_snapshot_bucket,
        "blob": settings.gcs_snapshot_blob,
        "bytes": len(payload.encode("utf-8")),
        "saved_at": datetime.now(tz=UTC).isoformat(),
    }


def load_snapshot_from_gcs(settings: BISSettings) -> dict[str, Any] | None:
    if not gcs_snapshot_configured(settings):
        return None
    client = _client()
    bucket = client.bucket(settings.gcs_snapshot_bucket)
    blob = bucket.blob(settings.gcs_snapshot_blob)
    if not blob.exists(client=client):
        return None
    data = blob.download_as_bytes(client=client)
    return json.loads(data.decode("utf-8"))

