from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bis.settings import BISSettings

try:
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover
    storage = None  # type: ignore


def gcs_snapshot_configured(settings: BISSettings) -> bool:
    return bool(settings.gcs_snapshot_bucket.strip())


def _client() -> "storage.Client":
    if storage is None:
        raise RuntimeError("google-cloud-storage is not installed")
    return storage.Client()


def gcs_status(settings: BISSettings) -> Dict[str, Any]:
    configured = gcs_snapshot_configured(settings)
    status: Dict[str, Any] = {
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
                blob.updated.astimezone(timezone.utc).isoformat() if getattr(blob, "updated", None) else None
            )
    except Exception as exc:
        status["error"] = str(exc)
    return status


def save_snapshot_to_gcs(snapshot: Dict[str, Any], settings: BISSettings) -> Dict[str, Any]:
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
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def load_snapshot_from_gcs(settings: BISSettings) -> Optional[Dict[str, Any]]:
    if not gcs_snapshot_configured(settings):
        return None
    client = _client()
    bucket = client.bucket(settings.gcs_snapshot_bucket)
    blob = bucket.blob(settings.gcs_snapshot_blob)
    if not blob.exists(client=client):
        return None
    data = blob.download_as_bytes(client=client)
    return json.loads(data.decode("utf-8"))

