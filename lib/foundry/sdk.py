"""Versioned Foundry SDK surface for Sapphire.

This module sits above :mod:`lib.foundry.client` and gives callers a small,
contract-first write API:

* every write is wrapped in a versioned envelope,
* every envelope has a deterministic request hash,
* every upsert has an idempotency key,
* every envelope can be replayed without rebuilding local source data.

The SDK does not broaden Foundry permissions. It delegates the actual network
write to ``FoundryClient`` and is therefore safe to unit-test with a fake client.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.foundry.client import FoundryClient

SDK_VERSION = "0.1.0"
DEFAULT_SCHEMA_VERSION = "sapphire.foundry.write.v0.1.0"
SUPPORTED_SCHEMA_VERSIONS = {DEFAULT_SCHEMA_VERSION}
DEFAULT_OPERATION = "upsert_objects"


class FoundrySDKError(Exception):
    """Base Foundry SDK error."""


class FoundrySDKSchemaError(FoundrySDKError):
    """Raised when an SDK envelope is malformed or unsupported."""


class FoundrySDKIdempotencyError(FoundrySDKError):
    """Raised when one idempotency key is reused for a different payload."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _validate_schema_version(schema_version: str) -> None:
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise FoundrySDKSchemaError(
            f"Unsupported Foundry SDK schema_version {schema_version!r}; "
            f"supported versions: {supported}."
        )


def _canonical_request_payload(
    *,
    schema_version: str,
    operation: str,
    object_type: str,
    primary_key: str,
    objects: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "operation": operation,
        "object_type": object_type,
        "primary_key": primary_key,
        "objects": objects,
    }


def compute_request_hash(
    *,
    schema_version: str,
    operation: str,
    object_type: str,
    primary_key: str,
    objects: list[dict[str, Any]],
) -> str:
    """Return the deterministic SHA-256 hash for a Foundry SDK request."""
    _validate_schema_version(schema_version)
    payload = _canonical_request_payload(
        schema_version=schema_version,
        operation=operation,
        object_type=object_type,
        primary_key=primary_key,
        objects=objects,
    )
    return _sha256_hex(_stable_json(payload))


def derive_idempotency_key(
    *,
    schema_version: str,
    operation: str,
    object_type: str,
    primary_key: str,
    objects: list[dict[str, Any]],
) -> str:
    """Derive a stable idempotency key from the canonical request hash."""
    request_hash = compute_request_hash(
        schema_version=schema_version,
        operation=operation,
        object_type=object_type,
        primary_key=primary_key,
        objects=objects,
    )
    return f"foundry:{object_type}:{request_hash[:32]}"


def _copy_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(_stable_json(objects))


def _validate_objects(objects: list[dict[str, Any]], *, primary_key: str) -> None:
    if not isinstance(objects, list) or not objects:
        raise FoundrySDKSchemaError("objects must be a non-empty list of dictionaries.")
    seen: set[str] = set()
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            raise FoundrySDKSchemaError(f"objects[{index}] must be a dictionary.")
        raw_pk = obj.get(primary_key)
        if raw_pk is None or str(raw_pk) == "":
            raise FoundrySDKSchemaError(f"objects[{index}] is missing primary key {primary_key!r}.")
        pk = str(raw_pk)
        if pk in seen:
            raise FoundrySDKSchemaError(
                f"duplicate primary key {primary_key!r} value {pk!r} in SDK request."
            )
        seen.add(pk)


@dataclass(frozen=True)
class FoundryWriteEnvelope:
    """Replayable Sapphire Foundry write envelope."""

    schema_version: str
    sdk_version: str
    operation: str
    object_type: str
    primary_key: str
    objects: list[dict[str, Any]]
    idempotency_key: str
    request_hash: str
    source: str
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def object_count(self) -> int:
        return len(self.objects)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sdk_version": self.sdk_version,
            "operation": self.operation,
            "object_type": self.object_type,
            "primary_key": self.primary_key,
            "objects": _copy_objects(self.objects),
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "source": self.source,
            "generated_at": self.generated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FoundryWriteEnvelope:
        schema_version = str(data.get("schema_version") or "")
        _validate_schema_version(schema_version)
        operation = str(data.get("operation") or "")
        if operation != DEFAULT_OPERATION:
            raise FoundrySDKSchemaError(f"Unsupported Foundry SDK operation {operation!r}.")
        object_type = str(data.get("object_type") or "")
        primary_key = str(data.get("primary_key") or "id")
        objects = _copy_objects(data.get("objects") or [])
        _validate_objects(objects, primary_key=primary_key)
        expected_hash = compute_request_hash(
            schema_version=schema_version,
            operation=operation,
            object_type=object_type,
            primary_key=primary_key,
            objects=objects,
        )
        request_hash = str(data.get("request_hash") or "")
        if request_hash != expected_hash:
            raise FoundrySDKSchemaError("Foundry SDK envelope request_hash does not match payload.")
        idempotency_key = str(data.get("idempotency_key") or "")
        if not idempotency_key:
            raise FoundrySDKSchemaError("Foundry SDK envelope is missing idempotency_key.")
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise FoundrySDKSchemaError("Foundry SDK envelope metadata must be an object.")
        return cls(
            schema_version=schema_version,
            sdk_version=str(data.get("sdk_version") or ""),
            operation=operation,
            object_type=object_type,
            primary_key=primary_key,
            objects=objects,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            source=str(data.get("source") or ""),
            generated_at=str(data.get("generated_at") or ""),
            metadata=dict(metadata),
        )


@dataclass(frozen=True)
class FoundrySDKResult:
    """Result returned by SapphireFoundrySDK writes and replays."""

    ok: bool
    object_type: str
    object_count: int
    schema_version: str
    idempotency_key: str
    request_hash: str
    dry_run: bool = False
    skipped: bool = False
    replay: bool = False
    foundry_result: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "object_type": self.object_type,
            "object_count": self.object_count,
            "schema_version": self.schema_version,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "dry_run": self.dry_run,
            "skipped": self.skipped,
            "replay": self.replay,
            "foundry_result": dict(self.foundry_result),
            "envelope": dict(self.envelope),
        }


class IdempotencyLedger:
    """Small JSON-backed idempotency ledger.

    A path is optional. Without one, the ledger is in-memory and useful for
    tests or a single process. With a path, entries are persisted atomically.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else None
        self._entries: dict[str, dict[str, Any]] = {}
        if self.path and self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError):
                loaded = {}
            if isinstance(loaded, dict):
                self._entries = {
                    str(key): value for key, value in loaded.items() if isinstance(value, dict)
                }

    def get(self, idempotency_key: str) -> dict[str, Any] | None:
        entry = self._entries.get(idempotency_key)
        return dict(entry) if entry else None

    def record(self, idempotency_key: str, entry: dict[str, Any]) -> None:
        self._entries[idempotency_key] = dict(entry)
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._entries, indent=2, sort_keys=True, default=str))
        tmp.replace(self.path)


class SapphireFoundrySDK:
    """Versioned SDK facade for Sapphire Foundry writes."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        ledger: IdempotencyLedger | None = None,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
        source: str = "sapphire-foundry-sdk",
    ):
        _validate_schema_version(schema_version)
        self.client = client if client is not None else FoundryClient.from_env()
        self.ledger = ledger if ledger is not None else IdempotencyLedger()
        self.schema_version = schema_version
        self.source = source

    @classmethod
    def from_env(cls, **kwargs: Any) -> SapphireFoundrySDK:
        return cls(client=FoundryClient.from_env(), **kwargs)

    def build_envelope(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        primary_key: str = "id",
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FoundryWriteEnvelope:
        if not object_type:
            raise FoundrySDKSchemaError("object_type is required.")
        objects_copy = _copy_objects(objects)
        _validate_objects(objects_copy, primary_key=primary_key)
        request_hash = compute_request_hash(
            schema_version=self.schema_version,
            operation=DEFAULT_OPERATION,
            object_type=object_type,
            primary_key=primary_key,
            objects=objects_copy,
        )
        key = idempotency_key or derive_idempotency_key(
            schema_version=self.schema_version,
            operation=DEFAULT_OPERATION,
            object_type=object_type,
            primary_key=primary_key,
            objects=objects_copy,
        )
        return FoundryWriteEnvelope(
            schema_version=self.schema_version,
            sdk_version=SDK_VERSION,
            operation=DEFAULT_OPERATION,
            object_type=object_type,
            primary_key=primary_key,
            objects=objects_copy,
            idempotency_key=key,
            request_hash=request_hash,
            source=self.source,
            generated_at=_now_iso(),
            metadata=dict(metadata or {}),
        )

    def write_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        primary_key: str = "id",
        idempotency_key: str | None = None,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> FoundrySDKResult:
        envelope = self.build_envelope(
            object_type,
            objects,
            primary_key=primary_key,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )
        return self._write_envelope(envelope, dry_run=dry_run, replay=False)

    def replay_envelope(
        self,
        envelope: FoundryWriteEnvelope | dict[str, Any],
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> FoundrySDKResult:
        parsed = (
            envelope
            if isinstance(envelope, FoundryWriteEnvelope)
            else FoundryWriteEnvelope.from_dict(envelope)
        )
        return self._write_envelope(parsed, dry_run=dry_run, replay=True, force=force)

    def _write_envelope(
        self,
        envelope: FoundryWriteEnvelope,
        *,
        dry_run: bool,
        replay: bool,
        force: bool = False,
    ) -> FoundrySDKResult:
        previous = self.ledger.get(envelope.idempotency_key)
        if previous and previous.get("request_hash") != envelope.request_hash:
            raise FoundrySDKIdempotencyError(
                "Foundry SDK idempotency key was reused for a different request hash."
            )
        if previous and not force:
            return FoundrySDKResult(
                ok=True,
                object_type=envelope.object_type,
                object_count=envelope.object_count,
                schema_version=envelope.schema_version,
                idempotency_key=envelope.idempotency_key,
                request_hash=envelope.request_hash,
                dry_run=bool(previous.get("dry_run", False)),
                skipped=True,
                replay=replay,
                foundry_result=dict(previous.get("foundry_result") or {}),
                envelope=envelope.to_dict(),
            )

        if dry_run:
            foundry_result = {
                "dry_run": True,
                "object_type": envelope.object_type,
                "object_count": envelope.object_count,
            }
        elif getattr(self.client, "write_mode", "action") == "dataset":
            foundry_result = self.client.upload_dataset_objects(
                envelope.object_type,
                envelope.objects,
            )
        else:
            foundry_result = self.client.upsert_objects(
                envelope.object_type,
                envelope.objects,
                primary_key=envelope.primary_key,
            )

        self.ledger.record(
            envelope.idempotency_key,
            {
                "request_hash": envelope.request_hash,
                "schema_version": envelope.schema_version,
                "object_type": envelope.object_type,
                "object_count": envelope.object_count,
                "dry_run": dry_run,
                "foundry_result": foundry_result,
                "envelope": envelope.to_dict(),
                "recorded_at": _now_iso(),
                "forced_replay": force,
            },
        )
        return FoundrySDKResult(
            ok=True,
            object_type=envelope.object_type,
            object_count=envelope.object_count,
            schema_version=envelope.schema_version,
            idempotency_key=envelope.idempotency_key,
            request_hash=envelope.request_hash,
            dry_run=dry_run,
            skipped=False,
            replay=replay,
            foundry_result=dict(foundry_result),
            envelope=envelope.to_dict(),
        )


__all__ = [
    "DEFAULT_SCHEMA_VERSION",
    "SDK_VERSION",
    "FoundrySDKError",
    "FoundrySDKIdempotencyError",
    "FoundrySDKResult",
    "FoundrySDKSchemaError",
    "FoundryWriteEnvelope",
    "IdempotencyLedger",
    "SapphireFoundrySDK",
    "compute_request_hash",
    "derive_idempotency_key",
]
