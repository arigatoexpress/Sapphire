"""Durable media artifact manifests.

This module gives podcast/video/image generation work a provenance spine before
any generation API or live publishing path is wired in. It only reads local
files and writes JSON manifests.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_ROOT = REPO_ROOT / "data" / "media" / "manifests"
SCHEMA_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normal_token(value: str, *, default: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or default


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def make_run_id(kind: str, slug: str, *, when: datetime | None = None) -> str:
    """Return a deterministic run id shaped like ``YYYYMMDD_<kind>_<slug>``."""
    when = when or _utcnow()
    return "_".join(
        (
            when.strftime("%Y%m%d"),
            _normal_token(kind, default="media"),
            _normal_token(slug, default="artifact"),
        )
    )


def sha256_file(path: Path) -> str:
    """Return a SHA-256 hex digest for a local artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(
    path: Path | str,
    *,
    root: Path = REPO_ROOT,
    role: str,
    media_kind: str,
    mime_type: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Build a manifest record for one existing local artifact."""
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError(str(artifact_path))
    guessed_mime, _encoding = mimetypes.guess_type(artifact_path.name)
    return {
        "path": _repo_relative(artifact_path, root),
        "role": role,
        "media_kind": media_kind,
        "mime_type": mime_type or guessed_mime,
        "bytes": artifact_path.stat().st_size,
        "sha256": sha256_file(artifact_path),
        "duration_seconds": duration_seconds,
    }


def _coerce_artifacts(
    artifacts: list[Path | str | dict[str, Any]],
    *,
    root: Path,
    role: str,
    media_kind: str,
) -> list[dict[str, Any]]:
    rows = []
    for item in artifacts:
        if isinstance(item, dict):
            rows.append(dict(item))
            continue
        rows.append(artifact_record(item, root=root, role=role, media_kind=media_kind))
    return rows


def write_manifest(
    *,
    kind: str,
    slug: str,
    media_kind: str,
    inputs: list[Path | str | dict[str, Any]],
    outputs: list[Path | str | dict[str, Any]],
    root: Path = REPO_ROOT,
    manifest_root: Path = DEFAULT_MANIFEST_ROOT,
    dry_run: bool = True,
    approval_status: str = "pending",
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Write and return a local media manifest.

    ``inputs`` and ``outputs`` may be paths or pre-built artifact records. Path
    items must already exist so manifests cannot claim outputs that were not
    actually materialized.
    """
    created_at = created_at or _utcnow()
    run_id = make_run_id(kind, slug, when=created_at)
    manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_root / f"{run_id}.json"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "kind": _normal_token(kind, default="media"),
        "slug": _normal_token(slug, default="artifact"),
        "media_kind": media_kind,
        "dry_run": dry_run,
        "approval_status": approval_status,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "inputs": _coerce_artifacts(inputs, root=root, role="input", media_kind=media_kind),
        "outputs": _coerce_artifacts(outputs, root=root, role="output", media_kind=media_kind),
        "metadata": metadata or {},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest["manifest_path"] = _repo_relative(manifest_path, root)
    return manifest


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Load a manifest written by :func:`write_manifest`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data
