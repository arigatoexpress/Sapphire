"""Credential storage backends for the WebAuthn admin scaffold.

Schema (matches the spec in the project handoff):

    credential_id   bytes   primary key
    public_key      bytes
    sign_count      int
    user_id         str
    created_at      datetime (UTC)
    last_used_at    datetime (UTC) | None
    aaguid          str

Two backends:

    InMemoryCredentialStore   — tests / local dev when GOOGLE_APPLICATION_CREDENTIALS
                                is not set. Persists for the life of the process.
    FirestoreCredentialStore  — production. Collection: ``admin_credentials``,
                                document id: base64url(credential_id).

Both implement the same ``CredentialStore`` Protocol so callers can be
backend-agnostic.
"""

from __future__ import annotations

import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

log = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode bytes without padding (matches WebAuthn convention)."""
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + padding)


@dataclass
class CredentialRecord:
    """One registered passkey."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_id: str
    aaguid: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None

    @property
    def credential_id_b64(self) -> str:
        return _b64url_encode(self.credential_id)


class CredentialStore(Protocol):
    """Pluggable persistence for registered passkeys."""

    def add(self, record: CredentialRecord) -> None: ...
    def get(self, credential_id: bytes) -> CredentialRecord | None: ...
    def list_all(self) -> list[CredentialRecord]: ...
    def list_for_user(self, user_id: str) -> list[CredentialRecord]: ...
    def update_usage(self, credential_id: bytes, *, sign_count: int) -> None: ...
    def count(self) -> int: ...


# ---------------------------------------------------------------------------
# In-memory backend (tests + GOOGLE_APPLICATION_CREDENTIALS-less dev)
# ---------------------------------------------------------------------------


class InMemoryCredentialStore:
    """Process-local credential store. Lost on restart — tests only."""

    def __init__(self, seed: Iterable[CredentialRecord] = ()) -> None:
        self._rows: dict[bytes, CredentialRecord] = {}
        for r in seed:
            self.add(r)

    def add(self, record: CredentialRecord) -> None:
        self._rows[record.credential_id] = record

    def get(self, credential_id: bytes) -> CredentialRecord | None:
        return self._rows.get(credential_id)

    def list_all(self) -> list[CredentialRecord]:
        return list(self._rows.values())

    def list_for_user(self, user_id: str) -> list[CredentialRecord]:
        return [r for r in self._rows.values() if r.user_id == user_id]

    def update_usage(self, credential_id: bytes, *, sign_count: int) -> None:
        rec = self._rows.get(credential_id)
        if rec is None:
            return
        rec.sign_count = sign_count
        rec.last_used_at = datetime.now(UTC)

    def count(self) -> int:
        return len(self._rows)


# ---------------------------------------------------------------------------
# Firestore backend
# ---------------------------------------------------------------------------


class FirestoreCredentialStore:
    """Persists credentials to Firestore in project ``tho-ai-agent``.

    Collection: ``admin_credentials``
    Document id: ``urlsafe-base64(credential_id)`` (no padding)

    Bytes (credential_id, public_key) are stored as Firestore Blob — the
    underlying client preserves byte-identity round-trip.

    Lazy-imports ``google.cloud.firestore`` so the module loads in
    environments where the SDK is missing (tests, lightweight workers).
    """

    COLLECTION = "admin_credentials"

    def __init__(self, project: str | None = None, *, client=None) -> None:
        if client is None:
            from google.cloud import firestore  # local import keeps module light

            client = firestore.Client(project=project) if project else firestore.Client()
        self._client = client
        self._collection = client.collection(self.COLLECTION)

    @staticmethod
    def _doc_id(credential_id: bytes) -> str:
        return _b64url_encode(credential_id)

    @classmethod
    def _to_record(cls, doc_id: str, data: dict) -> CredentialRecord:
        cid = data.get("credential_id")
        if isinstance(cid, str):
            cid_bytes = _b64url_decode(cid)
        elif cid is None:
            cid_bytes = _b64url_decode(doc_id)
        else:
            cid_bytes = bytes(cid)
        pk = data.get("public_key", b"")
        pk_bytes = _b64url_decode(pk) if isinstance(pk, str) else bytes(pk)
        return CredentialRecord(
            credential_id=cid_bytes,
            public_key=pk_bytes,
            sign_count=int(data.get("sign_count", 0)),
            user_id=str(data.get("user_id", "admin")),
            aaguid=str(data.get("aaguid", "")),
            created_at=data.get("created_at") or datetime.now(UTC),
            last_used_at=data.get("last_used_at"),
        )

    def add(self, record: CredentialRecord) -> None:
        self._collection.document(self._doc_id(record.credential_id)).set(
            {
                "credential_id": record.credential_id,
                "public_key": record.public_key,
                "sign_count": record.sign_count,
                "user_id": record.user_id,
                "aaguid": record.aaguid,
                "created_at": record.created_at,
                "last_used_at": record.last_used_at,
            }
        )

    def get(self, credential_id: bytes) -> CredentialRecord | None:
        snap = self._collection.document(self._doc_id(credential_id)).get()
        if not snap.exists:
            return None
        return self._to_record(snap.id, snap.to_dict() or {})

    def list_all(self) -> list[CredentialRecord]:
        return [self._to_record(s.id, s.to_dict() or {}) for s in self._collection.stream()]

    def list_for_user(self, user_id: str) -> list[CredentialRecord]:
        query = self._collection.where("user_id", "==", user_id)
        return [self._to_record(s.id, s.to_dict() or {}) for s in query.stream()]

    def update_usage(self, credential_id: bytes, *, sign_count: int) -> None:
        self._collection.document(self._doc_id(credential_id)).update(
            {"sign_count": sign_count, "last_used_at": datetime.now(UTC)}
        )

    def count(self) -> int:
        # Firestore has no native COUNT; this is fine for an admin-only collection
        # that holds at most a handful of credentials.
        return sum(1 for _ in self._collection.stream())


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def default_store(project: str | None = None) -> CredentialStore:
    """Return a Firestore-backed store, falling back to in-memory if the SDK or
    ADC are unavailable. Used at app startup so dev / CI doesn't hard-require
    GCP credentials.
    """
    try:
        return FirestoreCredentialStore(project=project)
    except Exception as exc:  # noqa: BLE001 — broad on purpose; we degrade gracefully
        log.warning("falling back to in-memory credential store (%s)", exc)
        return InMemoryCredentialStore()
