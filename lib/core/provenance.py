"""Schema-versioned provenance envelopes for Sapphire-generated artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]


def canonical_json(value: Any) -> str:
    """Return deterministic JSON used for all provenance hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _repo_relative(path: Path, *, root: Path = REPO_ROOT) -> str:
    """Repo-relative path, always with forward slashes.

    These strings land in committed JSON artifacts, so they must not vary by the
    host that generated them. `str()` on a Path yields backslashes on Windows,
    which would make an artifact generated there differ from the same artifact
    generated on macOS — and, for provenance, change the dict keys.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _source_hashes(source_paths: tuple[str | Path, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for raw in source_paths:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.is_file():
            hashes[_repo_relative(path)] = sha256_file(path)
    return hashes


@dataclass(frozen=True)
class ProvenanceEnvelope:
    """Frozen schema-v1 provenance metadata for one generated payload."""

    generator: str
    payload_hash: str
    generated_at: str
    source_hashes: dict[str, str] = field(default_factory=dict)
    model: str | None = None
    prompt_hash: str | None = None
    ttl_seconds: int | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    envelope_hash: str = ""

    @classmethod
    def build(
        cls,
        payload: Any,
        *,
        generator: str,
        model: str | None = None,
        source_paths: tuple[str | Path, ...] = (),
        prompt: str | None = None,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        generated_at: str | None = None,
    ) -> ProvenanceEnvelope:
        generated = generated_at or _now_iso()
        expires_at = None
        if ttl_seconds is not None:
            expires_at = (
                (
                    datetime.fromisoformat(generated).astimezone(UTC)
                    + timedelta(seconds=max(0, int(ttl_seconds)))
                )
                .replace(microsecond=0)
                .isoformat()
            )
        envelope = cls(
            schema_version=SCHEMA_VERSION,
            generator=str(generator),
            model=model,
            prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None,
            source_hashes=_source_hashes(tuple(source_paths or ())),
            generated_at=generated,
            ttl_seconds=int(ttl_seconds) if ttl_seconds is not None else None,
            expires_at=expires_at,
            payload_hash=sha256_canonical(payload),
            metadata=dict(metadata or {}),
        )
        return envelope.with_hash()

    def unsigned_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("envelope_hash", None)
        return data

    def with_hash(self) -> ProvenanceEnvelope:
        digest = sha256_canonical(self.unsigned_dict())
        return ProvenanceEnvelope(**{**self.unsigned_dict(), "envelope_hash": digest})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stamp(
    payload: Any,
    *,
    generator: str,
    model: str | None = None,
    source_paths: tuple[str | Path, ...] = (),
    prompt: str | None = None,
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``payload`` plus a schema-v1 ``provenance`` block."""
    materialized = copy.deepcopy(payload) if isinstance(payload, dict) else {"payload": payload}
    envelope = ProvenanceEnvelope.build(
        materialized,
        generator=generator,
        model=model,
        source_paths=source_paths,
        prompt=prompt,
        ttl_seconds=ttl_seconds,
        metadata=metadata,
    )
    materialized["provenance"] = envelope.to_dict()
    return materialized


def verify(envelope: dict[str, Any]) -> bool:
    """Verify a provenance envelope or stamped payload without side effects."""
    if "provenance" in envelope:
        provenance = envelope.get("provenance")
        if not isinstance(provenance, dict):
            return False
        payload = {k: copy.deepcopy(v) for k, v in envelope.items() if k != "provenance"}
        if provenance.get("payload_hash") != sha256_canonical(payload):
            return False
        return _verify_provenance_dict(provenance)
    return _verify_provenance_dict(envelope)


def sidecar_path(path: Path | str) -> Path:
    artifact = Path(path)
    return artifact.with_name(f"{artifact.name}.envelope.json")


def stamp_file(
    path: Path | str,
    *,
    generator: str,
    model: str | None = None,
    source_paths: tuple[str | Path, ...] = (),
    prompt: str | None = None,
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = Path(path)
    stat = artifact.stat()
    payload = {
        "artifact_path": _repo_relative(artifact),
        "artifact_sha256": sha256_file(artifact),
        "artifact_bytes": stat.st_size,
        "artifact_mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        .replace(microsecond=0)
        .isoformat(),
    }
    return stamp(
        payload,
        generator=generator,
        model=model,
        source_paths=source_paths,
        prompt=prompt,
        ttl_seconds=ttl_seconds,
        metadata=metadata,
    )


def write_envelope_sidecar(
    path: Path | str,
    *,
    generator: str,
    model: str | None = None,
    source_paths: tuple[str | Path, ...] = (),
    prompt: str | None = None,
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    sidecar = sidecar_path(path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = stamp_file(
        path,
        generator=generator,
        model=model,
        source_paths=source_paths,
        prompt=prompt,
        ttl_seconds=ttl_seconds,
        metadata=metadata,
    )
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar


def _verify_provenance_dict(provenance: dict[str, Any]) -> bool:
    if int(provenance.get("schema_version") or 0) != SCHEMA_VERSION:
        return False
    expected = provenance.get("envelope_hash")
    if not isinstance(expected, str) or not expected:
        return False
    unsigned = dict(provenance)
    unsigned.pop("envelope_hash", None)
    return sha256_canonical(unsigned) == expected


__all__ = [
    "ProvenanceEnvelope",
    "canonical_json",
    "sha256_canonical",
    "sha256_file",
    "sidecar_path",
    "stamp",
    "stamp_file",
    "verify",
    "write_envelope_sidecar",
]
