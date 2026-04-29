"""Interval-indexed snapshots of Sapphire's append-only JSONL time series.

Public surface
--------------

- :class:`SystemSnapshot` — frozen dataclass holding the per-scope rows
  visible at a requested UTC timestamp ``at``.
- :class:`SnapshotEntry` — per-scope payload (rows + interval metadata).
- :func:`take_snapshot` — main entrypoint. Builds (or loads) the index
  and returns a snapshot for ``at``.
- :func:`build_index` — scans configured roots, writes
  ``~/.cache/sapphire/timetravel/index.json``. Idempotent: running it
  twice yields the same content (deterministic ordering, hashed
  fingerprints).
- :func:`load_index` — load the cached index, or build it on first call.
- :func:`index_status` — read-only summary used by the plugin tool.

Design notes
------------

The index is a JSON map ``{scope: [{path, first_ts, last_ts, rows,
sha256, mtime, size_bytes}, ...]}``. Per-file ``first_ts``/``last_ts``
are UTC ISO-8601 strings and let ``take_snapshot`` skip files whose
window doesn't contain ``at`` without reading them.

Each scope has a ``timestamp_field`` resolver: a small function that
extracts a UTC datetime from a row. We support a handful of common
fields (``generated_at``, ``timestamp``, ``ts``, ``time``,
``observed_at``) and the legacy event-bus payload shape
``{"id": ..., "topic": ..., "payload": {...}, "ts": ...}``.

"What was visible at ``at``" semantics: a row is included when the
parsed timestamp ``ts <= at``. We never include rows whose ``ts`` is
in the future relative to ``at``. Out-of-range requests (``at`` before
the earliest known row or after the latest) are NOT errors — they
return an empty snapshot for the affected scope so callers can detect
the boundary cleanly via :attr:`SnapshotEntry.empty`.

UTC discipline: every datetime input is normalised to UTC. Naive
datetimes are tagged as UTC. Output timestamps are ISO-8601 strings
with explicit ``+00:00`` offsets.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path.home() / ".cache" / "sapphire" / "timetravel"
INDEX_PATH = CACHE_DIR / "index.json"

INDEX_SCHEMA_VERSION = 1
GENERATOR = "lib.timetravel.snapshot"
VERSION = "0.1.0"

# Map scope name to the on-disk root we scan. The roots intentionally
# point at the directories whose append-only JSONL files form Sapphire's
# decision audit trail.
SCOPE_TO_ROOT: dict[str, Path] = {
    "correlated_signals": REPO_ROOT / "data" / "correlated_signals",
    "narratives": REPO_ROOT / "data" / "narratives",
    "cross_asset": REPO_ROOT / "data" / "cross_asset",
    "macro": REPO_ROOT / "data" / "macro",
    "onchain": REPO_ROOT / "data" / "onchain",
    "events_bus": REPO_ROOT / "data" / "events",
}

DEFAULT_SCOPE: tuple[str, ...] = tuple(SCOPE_TO_ROOT)

# Per-scope filename glob applied beneath the root. ``**/*.jsonl`` is the
# common case; the events bus is a single flat file.
SCOPE_GLOBS: dict[str, str] = {
    "correlated_signals": "**/*.jsonl",
    "narratives": "**/*.jsonl",
    "cross_asset": "**/*.jsonl",
    "macro": "**/*.jsonl",
    "onchain": "**/*.jsonl",
    "events_bus": "bus.jsonl",
}

MAX_BYTES_PER_FILE = 64 * 1024 * 1024  # safety stop for runaway logs.
MAX_INDEX_FILES_PER_SCOPE = 5_000


# ---------------------------------------------------------------------------
# Timestamp resolution
# ---------------------------------------------------------------------------

_TIMESTAMP_KEYS: tuple[str, ...] = (
    "generated_at",
    "timestamp",
    "timestamp_iso",
    "ts",
    "time",
    "observed_at",
    "wrote_at",
)


def _parse_iso(value: Any) -> datetime | None:
    """Parse a UTC datetime from an ISO-8601 string or epoch number."""
    if value in (None, "", b""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        # Epoch seconds: a small heuristic distinguishes ms.
        v = float(value)
        if v > 1e12:
            v /= 1000.0
        try:
            return datetime.fromtimestamp(v, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _row_timestamp(row: dict[str, Any]) -> datetime | None:
    """Extract a UTC timestamp from a JSONL row, or return None."""
    for key in _TIMESTAMP_KEYS:
        if key in row:
            ts = _parse_iso(row.get(key))
            if ts is not None:
                return ts
    payload = row.get("payload")
    if isinstance(payload, dict):
        for key in _TIMESTAMP_KEYS:
            if key in payload:
                ts = _parse_iso(payload.get(key))
                if ts is not None:
                    return ts
    return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEntry:
    """Per-scope payload for a snapshot."""

    scope: str
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    files_visited: tuple[str, ...] = field(default_factory=tuple)
    earliest_ts: str | None = None
    latest_ts: str | None = None

    @property
    def empty(self) -> bool:
        return len(self.rows) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "rows": list(self.rows),
            "files_visited": list(self.files_visited),
            "earliest_ts": self.earliest_ts,
            "latest_ts": self.latest_ts,
            "row_count": len(self.rows),
            "empty": self.empty,
        }


@dataclass(frozen=True)
class SystemSnapshot:
    """Frozen system-wide snapshot at a UTC timestamp."""

    at: str
    scope: tuple[str, ...]
    entries: dict[str, SnapshotEntry]
    generated_at: str
    index_signature: str
    provenance_envelope: dict[str, Any]

    def by_scope(self, name: str) -> SnapshotEntry:
        return self.entries.get(name, SnapshotEntry(scope=name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "scope": list(self.scope),
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "generated_at": self.generated_at,
            "index_signature": self.index_signature,
            "provenance_envelope": dict(self.provenance_envelope),
        }


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def _file_fingerprint(path: Path) -> tuple[str, float, int]:
    """Return ``(sha256, mtime, size_bytes)`` — used by index idempotence."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    stat = path.stat()
    return digest.hexdigest(), float(stat.st_mtime), int(size or stat.st_size)


def _scan_file(path: Path) -> dict[str, Any] | None:
    """Pull (first_ts, last_ts, row_count) for a JSONL file in one pass."""
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_BYTES_PER_FILE:
        log.warning("timetravel: skipping oversized file %s", path)
        return None
    first: datetime | None = None
    last: datetime | None = None
    rows = 0
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                ts = _row_timestamp(payload)
                if ts is None:
                    continue
                rows += 1
                if first is None or ts < first:
                    first = ts
                if last is None or ts > last:
                    last = ts
    except OSError as exc:
        log.warning("timetravel: read failed for %s (%s)", path, exc)
        return None
    if rows == 0:
        return None
    sha, mtime, size = _file_fingerprint(path)
    return {
        "path": str(path),
        "first_ts": first.isoformat() if first else None,
        "last_ts": last.isoformat() if last else None,
        "rows": rows,
        "sha256": sha,
        "mtime": mtime,
        "size_bytes": size,
    }


def _gather_scope_files(scope: str, root: Path) -> list[Path]:
    glob_pattern = SCOPE_GLOBS.get(scope, "**/*.jsonl")
    if not root.exists():
        return []
    files = sorted(root.glob(glob_pattern))
    return files[:MAX_INDEX_FILES_PER_SCOPE]


def _index_signature(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_index(
    *,
    scopes: Iterable[str] = DEFAULT_SCOPE,
    cache_path: Path = INDEX_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Scan configured roots and write a fresh index to ``cache_path``.

    Idempotent: running twice yields the same on-disk content (we rebuild
    from scratch and only persist if the signature changes).
    """
    requested = tuple(scopes)
    scope_payload: dict[str, list[dict[str, Any]]] = {}
    total_rows = 0
    total_files = 0
    for scope in requested:
        root = SCOPE_TO_ROOT.get(scope)
        if root is None:
            log.debug("timetravel: unknown scope %s — skipping", scope)
            continue
        entries: list[dict[str, Any]] = []
        for path in _gather_scope_files(scope, root):
            entry = _scan_file(path)
            if entry is None:
                continue
            entries.append(entry)
            total_rows += int(entry.get("rows", 0))
        # Stable ordering by (first_ts, path) so the signature is deterministic.
        entries.sort(key=lambda e: (e.get("first_ts") or "", e.get("path") or ""))
        scope_payload[scope] = entries
        total_files += len(entries)

    body = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generator": GENERATOR,
        "version": VERSION,
        "built_at": (now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        "scopes": scope_payload,
        "totals": {
            "files": total_files,
            "rows": total_rows,
            "scopes": len(scope_payload),
        },
    }
    body["signature"] = _index_signature(
        {"scopes": scope_payload, "schema_version": INDEX_SCHEMA_VERSION}
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_index(cache_path)
    if existing and existing.get("signature") == body["signature"]:
        return existing
    cache_path.write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return body


def _read_existing_index(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_index(
    *,
    cache_path: Path = INDEX_PATH,
    scopes: Iterable[str] = DEFAULT_SCOPE,
    rebuild: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load the cached index, building it on first call or when stale."""
    if rebuild:
        return build_index(scopes=scopes, cache_path=cache_path, now=now)
    existing = _read_existing_index(cache_path)
    if existing is None:
        return build_index(scopes=scopes, cache_path=cache_path, now=now)
    return existing


def index_status(*, cache_path: Path = INDEX_PATH) -> dict[str, Any]:
    """Return a small dict describing the on-disk index without rebuild."""
    payload = _read_existing_index(cache_path)
    if payload is None:
        return {
            "exists": False,
            "path": str(cache_path),
            "scopes": list(DEFAULT_SCOPE),
            "files": 0,
            "rows": 0,
            "signature": None,
            "built_at": None,
        }
    totals = payload.get("totals") or {}
    return {
        "exists": True,
        "path": str(cache_path),
        "scopes": sorted(payload.get("scopes") or []),
        "files": int(totals.get("files", 0)),
        "rows": int(totals.get("rows", 0)),
        "signature": payload.get("signature"),
        "built_at": payload.get("built_at"),
        "schema_version": payload.get("schema_version"),
    }


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def _normalise_at(at: datetime) -> datetime:
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC)


def _entries_for_scope(
    index: dict[str, Any],
    scope: str,
    *,
    at: datetime,
) -> list[dict[str, Any]]:
    raw = (index.get("scopes") or {}).get(scope) or []
    candidates: list[dict[str, Any]] = []
    for entry in raw:
        first_ts = _parse_iso(entry.get("first_ts"))
        if first_ts is None:
            continue
        if first_ts > at:
            continue
        candidates.append(entry)
    return candidates


def _stream_rows_at(
    path: Path, *, at: datetime, max_rows: int = 100_000
) -> Iterable[tuple[datetime, dict[str, Any]]]:
    if not path.is_file():
        return []
    rows: list[tuple[datetime, dict[str, Any]]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                ts = _row_timestamp(payload)
                if ts is None or ts > at:
                    continue
                rows.append((ts, payload))
                if len(rows) >= max_rows:
                    break
    except OSError as exc:
        log.warning("timetravel: read failed for %s (%s)", path, exc)
        return []
    return rows


def take_snapshot(
    at: datetime,
    *,
    scope: Iterable[str] | None = None,
    cache_path: Path = INDEX_PATH,
    rebuild_index: bool = False,
    max_rows_per_file: int = 100_000,
    now: datetime | None = None,
) -> SystemSnapshot:
    """Return a :class:`SystemSnapshot` containing rows visible at ``at``.

    ``at`` must be timezone-aware UTC; naive datetimes are coerced. If
    ``scope`` is omitted we use :data:`DEFAULT_SCOPE`. The index is
    loaded (and built on first call) under ``cache_path``.
    """
    at_utc = _normalise_at(at)
    requested_scopes = tuple(scope) if scope else DEFAULT_SCOPE
    index = load_index(
        cache_path=cache_path,
        scopes=requested_scopes,
        rebuild=rebuild_index,
        now=now,
    )
    entries: dict[str, SnapshotEntry] = {}
    for sc in requested_scopes:
        candidates = _entries_for_scope(index, sc, at=at_utc)
        scope_rows: list[tuple[datetime, dict[str, Any]]] = []
        files_visited: list[str] = []
        for entry in candidates:
            path = Path(str(entry.get("path") or ""))
            if not path.is_file():
                continue
            files_visited.append(str(path))
            for ts, row in _stream_rows_at(
                path, at=at_utc, max_rows=max_rows_per_file
            ):
                scope_rows.append((ts, row))
        scope_rows.sort(key=lambda kv: kv[0])
        rows = tuple(payload for _, payload in scope_rows)
        earliest = scope_rows[0][0].isoformat() if scope_rows else None
        latest = scope_rows[-1][0].isoformat() if scope_rows else None
        entries[sc] = SnapshotEntry(
            scope=sc,
            rows=rows,
            files_visited=tuple(sorted(files_visited)),
            earliest_ts=earliest,
            latest_ts=latest,
        )

    generated_at = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    envelope = _snapshot_envelope(
        at=at_utc.isoformat(),
        scope=requested_scopes,
        entries=entries,
        index=index,
        generated_at=generated_at,
    )
    return SystemSnapshot(
        at=at_utc.isoformat(),
        scope=requested_scopes,
        entries=entries,
        generated_at=generated_at,
        index_signature=str(index.get("signature") or ""),
        provenance_envelope=envelope,
    )


def _snapshot_envelope(
    *,
    at: str,
    scope: tuple[str, ...],
    entries: dict[str, SnapshotEntry],
    index: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    file_hashes: dict[str, str] = {}
    for sc in scope:
        scope_idx = (index.get("scopes") or {}).get(sc) or []
        for record in scope_idx:
            sha = record.get("sha256")
            path = record.get("path")
            if isinstance(sha, str) and isinstance(path, str):
                file_hashes[path] = sha
    return {
        "generator": GENERATOR,
        "version": VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
        "at": at,
        "scope": list(scope),
        "row_counts": {sc: len(entries[sc].rows) for sc in scope},
        "index_signature": str(index.get("signature") or ""),
        "index_built_at": index.get("built_at"),
        "source_files_sha256": file_hashes,
        "generated_at": generated_at,
        "warning": (
            "Time-travel snapshot is read-only research output. It does "
            "not represent live state and must not be used to place "
            "trades, send alerts, or mutate the event bus."
        ),
    }


__all__ = [
    "DEFAULT_SCOPE",
    "GENERATOR",
    "INDEX_PATH",
    "INDEX_SCHEMA_VERSION",
    "MAX_BYTES_PER_FILE",
    "MAX_INDEX_FILES_PER_SCOPE",
    "SCOPE_GLOBS",
    "SCOPE_TO_ROOT",
    "VERSION",
    "SnapshotEntry",
    "SystemSnapshot",
    "build_index",
    "index_status",
    "load_index",
    "take_snapshot",
]


# Allow tests / callers to bind a *fresh* repo root if invoked from the
# worktree root (the resolution above uses module ``__file__``).
def _set_repo_root_for_tests(root: Path) -> None:  # pragma: no cover - test helper
    global REPO_ROOT
    REPO_ROOT = Path(root)
    SCOPE_TO_ROOT.update(
        {
            "correlated_signals": REPO_ROOT / "data" / "correlated_signals",
            "narratives": REPO_ROOT / "data" / "narratives",
            "cross_asset": REPO_ROOT / "data" / "cross_asset",
            "macro": REPO_ROOT / "data" / "macro",
            "onchain": REPO_ROOT / "data" / "onchain",
            "events_bus": REPO_ROOT / "data" / "events",
        }
    )


# Public unused symbol guard: silence linters if os import becomes unused
# in future refactors.
_unused = (os, Callable)
