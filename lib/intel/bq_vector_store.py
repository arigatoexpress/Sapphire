"""BigQuery vector retrieval layer with deterministic local mock fallback.

This module is the canonical entry point for Sapphire's "lift our intel into
a queryable substrate" workstream. It exposes a small, contract-first API
over a vector store of intel records (sovereign-thesis assets, convergence
watchlist entries, threat-intel summaries, future intel sources). Acquirers
and partners can see that Sapphire intel is not a pile of local JSONL files
but a versioned, provenance-stamped, queryable corpus.

Two backends share one API:

* **mock** (default): an in-memory cosine-similarity store, persisted to
  ``~/.cache/sapphire/bq_vector_mock.jsonl``. Deterministic, dependency-free,
  CI-safe, and the default path for Sapphire callers.
* **live**: a real BigQuery-backed store that uses ``VECTOR_SEARCH`` over
  a fixed-schema table. Refuses
  to perform any live operation unless **all three** of these gates are
  satisfied at call time:

  1. ``SAPPHIRE_BQ_LIVE=1``
  2. ``GOOGLE_APPLICATION_CREDENTIALS`` resolves to a readable file
  3. ``SAPPHIRE_BQ_PROJECT`` matches the constructor's ``project`` argument

This module is intentionally side-effect-free at import time. No env vars
are read at module load. No filesystem or network I/O occurs until a method
is called. ``BQVectorStore`` reads env vars only inside guarded methods.

Caps (mirrored from the runbook so the registry, the docs, and the tool all
agree):

* ``MAX_QUERY_K = 50``
* ``MAX_INDEX_RECORDS_PER_RUN = 5000``
* ``MAX_LIVE_INDEX_PER_HOUR = 2``
* ``EMBEDDING_DIMS_HARD = 1536``

Every :class:`QueryHit` carries a :mod:`lib.core.provenance` envelope so
downstream consumers can verify the record was produced by Sapphire and has
not drifted since indexing.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import math
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.core.provenance import ProvenanceEnvelope, stamp
from lib.intel.embedders import (
    EMBEDDING_DIMS_HARD,
    EmbedderProtocol,
    HashEmbedder,
    default_registry,
)

# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

MAX_QUERY_K = 50
MAX_INDEX_RECORDS_PER_RUN = 5_000
MAX_LIVE_INDEX_PER_HOUR = 2
DEFAULT_DIMS = 768

DEFAULT_MOCK_PATH = Path.home() / ".cache" / "sapphire" / "bq_vector_mock.jsonl"
DEFAULT_RATE_PATH = Path.home() / ".cache" / "sapphire" / "bq_vector_live_rate.json"
BIGQUERY_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")

LIVE_VECTOR_SEARCH_SQL_TEMPLATE = """
SELECT
  result.base.id AS id,
  result.base.text AS text,
  result.base.source AS source,
  result.base.metadata AS metadata,
  result.base.created_at AS created_at,
  result.distance AS distance
FROM VECTOR_SEARCH(
  TABLE {table_sql_name},
  'embedding',
  (SELECT @query_embedding AS embedding),
  top_k => @top_k,
  distance_type => 'COSINE'
) AS result
WHERE (@source_filter IS NULL OR result.base.source = @source_filter)
ORDER BY result.distance ASC, result.base.id ASC
LIMIT @top_k
""".strip()

KNOWN_SOURCES = (
    "sovereign_thesis",
    "convergence_watchlist",
    "threat_intel",
    "daily_brief",
    "regional_intel",
    "ad_hoc",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VectorRecord:
    """One indexable intel record.

    ``embedding`` is required at upsert time (callers compute it via the
    chosen embedder). ``metadata`` is small, structured, and JSON-safe;
    secrets must never be placed here.
    """

    id: str
    text: str
    embedding: list[float]
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def to_jsonable(self) -> dict[str, Any]:
        created = (self.created_at or datetime.now(UTC)).isoformat()
        return {
            "id": self.id,
            "text": self.text,
            "embedding": list(self.embedding),
            "source": self.source,
            "metadata": dict(self.metadata),
            "created_at": created,
        }

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> VectorRecord:
        created_raw = data.get("created_at")
        created: datetime | None
        if isinstance(created_raw, datetime):
            created = created_raw
        elif isinstance(created_raw, str) and created_raw:
            try:
                created = datetime.fromisoformat(created_raw)
            except ValueError:
                created = None
        else:
            created = None
        return cls(
            id=str(data.get("id") or ""),
            text=str(data.get("text") or ""),
            embedding=[float(v) for v in (data.get("embedding") or [])],
            source=str(data.get("source") or "ad_hoc"),
            metadata=dict(data.get("metadata") or {}),
            created_at=created,
        )


@dataclass
class UpsertResult:
    ok: bool
    inserted: int
    updated: int
    skipped: int
    errors: list[str] = field(default_factory=list)
    mode: str = "mock"
    table: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryHit:
    """One ranked result from :meth:`BQVectorStore.query`.

    ``score`` is cosine similarity in ``[-1.0, 1.0]``; the store sorts
    descending. ``provenance`` is a stamped envelope produced by
    :func:`lib.core.provenance.stamp` over the underlying record.
    """

    id: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoreStats:
    mode: str
    total_records: int
    by_source: dict[str, int]
    table_fqn: str
    dims: int
    last_index_at: str | None
    backend_path: str | None = None
    live_calls_last_hour: int = 0
    max_live_index_per_hour: int = MAX_LIVE_INDEX_PER_HOUR

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in ``[-1.0, 1.0]``; 0.0 for any zero vector."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _stable_id(text: str, source: str, salt: str = "") -> str:
    """Derive a stable record ID from text + source when one is missing."""
    digest = hashlib.sha256(f"{salt}|{source}|{text}".encode()).hexdigest()
    return f"{source}:{digest[:16]}"


def describe_embedder_models(*, dims: int = DEFAULT_DIMS) -> list[dict[str, object]]:
    """Return the embedder model inventory exposed by the intel-search tool."""
    return default_registry(dims=dims).describe()


def _validate_records(
    records: list[VectorRecord],
    *,
    expected_dims: int,
) -> tuple[list[VectorRecord], list[str]]:
    cleaned: list[VectorRecord] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, VectorRecord):
            errors.append(f"records[{index}]: not a VectorRecord instance")
            continue
        if not raw.text or not raw.text.strip():
            errors.append(f"records[{index}] (id={raw.id}): empty text")
            continue
        if len(raw.embedding) != expected_dims:
            errors.append(
                f"records[{index}] (id={raw.id}): embedding dims "
                f"{len(raw.embedding)} != {expected_dims}"
            )
            continue
        if raw.source not in KNOWN_SOURCES:
            # Permitted but logged — keeps the schema soft for new sources.
            errors.append(
                f"records[{index}] (id={raw.id}): unknown source {raw.source!r} "
                f"(allowed: {', '.join(KNOWN_SOURCES)}); record kept"
            )
        record = raw
        if not record.id:
            record = VectorRecord(
                id=_stable_id(record.text, record.source),
                text=record.text,
                embedding=list(record.embedding),
                source=record.source,
                metadata=dict(record.metadata),
                created_at=record.created_at,
            )
        if record.id in seen:
            errors.append(f"records[{index}] (id={record.id}): duplicate ID in batch")
            continue
        seen.add(record.id)
        cleaned.append(record)
    return cleaned, errors


# ---------------------------------------------------------------------------
# Live-mode gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveGateResult:
    allowed: bool
    reason: str
    project: str | None = None


def evaluate_live_gate(*, project: str, env: dict[str, str] | None = None) -> LiveGateResult:
    """Return whether the live BigQuery path is currently permitted.

    The gate is fail-closed and must be re-checked on every call. It does
    not perform any I/O. Pass ``env`` to override ``os.environ`` for tests.
    """
    env_map = env if env is not None else os.environ
    if (env_map.get("SAPPHIRE_BQ_LIVE", "") or "").strip() != "1":
        return LiveGateResult(False, "SAPPHIRE_BQ_LIVE != 1")
    creds = (env_map.get("GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()
    if not creds:
        return LiveGateResult(False, "GOOGLE_APPLICATION_CREDENTIALS not set")
    if not Path(creds).expanduser().is_file():
        return LiveGateResult(False, f"GOOGLE_APPLICATION_CREDENTIALS file missing: {creds}")
    bq_project = (env_map.get("SAPPHIRE_BQ_PROJECT", "") or "").strip()
    if not bq_project:
        return LiveGateResult(False, "SAPPHIRE_BQ_PROJECT not set")
    if bq_project != project:
        return LiveGateResult(
            False,
            f"SAPPHIRE_BQ_PROJECT={bq_project!r} mismatches store project={project!r}",
            project=bq_project,
        )
    return LiveGateResult(True, "ok", project=bq_project)


# ---------------------------------------------------------------------------
# Mock backend (deterministic, JSONL-persisted)
# ---------------------------------------------------------------------------


class _MockBackend:
    """In-memory store with JSONL persistence.

    Persistence is best-effort: a corrupt line is skipped, a write failure
    raises. The file is rewritten in full on each upsert so the schema stays
    in sync (trade-off: slower for huge corpora; fine for the < 5K cap).
    """

    def __init__(self, *, path: Path, dims: int) -> None:
        self.path = path
        self.dims = dims
        self.records: dict[str, VectorRecord] = {}
        self.last_index_at: str | None = None
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            for raw_line in self.path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("__meta__"):
                    self.last_index_at = obj.get("last_index_at")
                    continue
                record = VectorRecord.from_jsonable(obj)
                if len(record.embedding) != self.dims:
                    continue
                self.records[record.id] = record
        except OSError:
            return

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        lines: list[str] = []
        lines.append(
            json.dumps(
                {
                    "__meta__": True,
                    "last_index_at": self.last_index_at,
                    "dims": self.dims,
                },
                sort_keys=True,
            )
        )
        for record in self.records.values():
            lines.append(json.dumps(record.to_jsonable(), sort_keys=True, default=str))
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def upsert(self, records: list[VectorRecord]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        for record in records:
            if record.id in self.records:
                updated += 1
            else:
                inserted += 1
            self.records[record.id] = record
        if records:
            self.last_index_at = _now_iso()
        return inserted, updated

    def all_records(self) -> list[VectorRecord]:
        return list(self.records.values())


# ---------------------------------------------------------------------------
# Live-mode rate limiter
# ---------------------------------------------------------------------------


def _load_live_rate(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"calls": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"calls": []}


def _save_live_rate(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _prune_calls(calls: list[float], *, now: float) -> list[float]:
    cutoff = now - 3600
    return [t for t in calls if t >= cutoff]


# ---------------------------------------------------------------------------
# Live BigQuery helpers
# ---------------------------------------------------------------------------


def _load_bigquery_module() -> Any:
    """Lazy import ``google.cloud.bigquery`` only after the live gate passes."""
    try:
        return importlib.import_module("google.cloud.bigquery")
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-bigquery is required for live BigQuery vector operations"
        ) from exc


def _quote_bigquery_table(project: str, dataset: str, table: str) -> str:
    """Return a backtick-quoted table FQN after validating identifier parts."""
    for label, value in (
        ("project", project),
        ("dataset", dataset),
        ("table", table),
    ):
        if not BIGQUERY_IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"invalid BigQuery {label} identifier: {value!r}")
    return f"`{project}.{dataset}.{table}`"


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return getattr(row, key, default)


def _metadata_from_row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _created_at_to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return _now_iso()


# ---------------------------------------------------------------------------
# Public store
# ---------------------------------------------------------------------------


class BQVectorStore:
    """Adapter for the Sapphire BigQuery vector retrieval layer.

    Parameters
    ----------
    project, dataset, table:
        Identify the (eventual) BigQuery destination. Even in mock mode
        these are recorded in stats and provenance so the corpus is
        portable when the live path is enabled.
    mock:
        ``True`` (default) uses the in-memory + JSONL backend. ``False``
        switches the store into "intends to use live"; *every* live call
        still re-checks :func:`evaluate_live_gate`.
    embedder:
        Used to compute embeddings for the query string when callers pass
        text to :meth:`query` instead of a vector. Defaults to a fresh
        :class:`HashEmbedder` at the configured ``dims``.
    dims:
        Embedding dimensionality. Hard-capped at ``EMBEDDING_DIMS_HARD``.
    mock_path / rate_path:
        Override default cache paths (handy for tests).
    """

    def __init__(
        self,
        project: str,
        dataset: str,
        table: str,
        *,
        mock: bool = True,
        embedder: EmbedderProtocol | None = None,
        dims: int = DEFAULT_DIMS,
        mock_path: Path | None = None,
        rate_path: Path | None = None,
    ) -> None:
        if not project or not dataset or not table:
            raise ValueError("project, dataset, and table are required")
        if dims < 8 or dims > EMBEDDING_DIMS_HARD:
            raise ValueError(f"dims={dims} must be in [8, {EMBEDDING_DIMS_HARD}]")
        self.project = project
        self.dataset = dataset
        self.table = table
        self.mock = bool(mock)
        self.dims = dims
        self.embedder: EmbedderProtocol = embedder or HashEmbedder(dims=dims)
        if getattr(self.embedder, "dims", dims) != dims:
            raise ValueError(
                f"embedder.dims={getattr(self.embedder, 'dims', None)} "
                f"does not match store dims={dims}"
            )
        self._mock_path = mock_path or DEFAULT_MOCK_PATH
        self._rate_path = rate_path or DEFAULT_RATE_PATH
        self._backend = _MockBackend(path=self._mock_path, dims=dims)

    # -- properties -------------------------------------------------------

    @property
    def table_fqn(self) -> str:
        return f"{self.project}.{self.dataset}.{self.table}"

    # -- internal ---------------------------------------------------------

    def _ensure_loaded(self) -> None:
        self._backend.load()

    def _live_allowed(self) -> LiveGateResult:
        return evaluate_live_gate(project=self.project)

    def _check_live_rate(self) -> tuple[bool, str, list[float]]:
        data = _load_live_rate(self._rate_path)
        calls = _prune_calls(list(data.get("calls", [])), now=time.time())
        if len(calls) >= MAX_LIVE_INDEX_PER_HOUR:
            return (
                False,
                (
                    f"live index rate limit hit: {len(calls)}/{MAX_LIVE_INDEX_PER_HOUR}"
                    " in the last hour"
                ),
                calls,
            )
        return True, "ok", calls

    def _record_live_call(self, calls: list[float]) -> None:
        calls.append(time.time())
        _save_live_rate(self._rate_path, {"calls": calls})

    def _embed_query(self, text: str | None, embedding: list[float] | None) -> list[float]:
        if embedding is not None:
            if len(embedding) != self.dims:
                raise ValueError(f"query embedding dims {len(embedding)} != store dims {self.dims}")
            return list(embedding)
        if text is None or not text.strip():
            raise ValueError("either text or embedding is required for query")
        return self.embedder.embed(text)

    def _build_provenance(self, record: VectorRecord) -> dict[str, Any]:
        envelope = ProvenanceEnvelope.build(
            {"id": record.id, "text": record.text, "source": record.source},
            generator="lib.intel.bq_vector_store",
            model=getattr(self.embedder, "name", "mock-hash"),
            metadata={
                "table": self.table_fqn,
                "dims": self.dims,
                "mode": "mock" if self.mock else "live",
                "record_source": record.source,
            },
        )
        return envelope.to_dict()

    def _bigquery_schema(self, bigquery: Any) -> list[Any]:
        return [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("text", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
            bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        ]

    def _ensure_live_table(self, client: Any, bigquery: Any) -> None:
        table = bigquery.Table(self.table_fqn, schema=self._bigquery_schema(bigquery))
        client.create_table(table, exists_ok=True)

    def _record_to_bq_row(self, record: VectorRecord) -> dict[str, Any]:
        created = record.created_at or _now()
        return {
            "id": record.id,
            "text": record.text,
            "embedding": [float(value) for value in record.embedding],
            "source": record.source,
            "metadata": dict(record.metadata),
            "created_at": created.isoformat(),
        }

    def _staging_table_name(self) -> str:
        table_prefix = re.sub(r"[^A-Za-z0-9_]", "_", self.table)
        return f"_{table_prefix}_stage_{uuid.uuid4().hex[:16]}"

    def _merge_sql(self, *, staging_table: str) -> str:
        target_sql = _quote_bigquery_table(self.project, self.dataset, self.table)
        staging_sql = _quote_bigquery_table(self.project, self.dataset, staging_table)
        return f"""
MERGE {target_sql} AS T
USING {staging_sql} AS S
ON T.id = S.id
WHEN MATCHED THEN
  UPDATE SET
    text = S.text,
    embedding = S.embedding,
    source = S.source,
    metadata = S.metadata,
    created_at = S.created_at
WHEN NOT MATCHED THEN
  INSERT (id, text, embedding, source, metadata, created_at)
  VALUES (S.id, S.text, S.embedding, S.source, S.metadata, S.created_at)
""".strip()

    def _live_upsert(self, records: list[VectorRecord]) -> tuple[int, int]:
        bigquery = _load_bigquery_module()
        client = bigquery.Client(project=self.project)
        schema = self._bigquery_schema(bigquery)
        self._ensure_live_table(client, bigquery)
        if not records:
            return 0, 0

        staging_table = self._staging_table_name()
        staging_fqn = f"{self.project}.{self.dataset}.{staging_table}"
        rows = [self._record_to_bq_row(record) for record in records]
        staging = bigquery.Table(staging_fqn, schema=schema)
        client.create_table(staging, exists_ok=True)
        try:
            write_disposition = getattr(
                getattr(bigquery, "WriteDisposition", object()),
                "WRITE_TRUNCATE",
                "WRITE_TRUNCATE",
            )
            load_config = bigquery.LoadJobConfig(
                schema=schema,
                write_disposition=write_disposition,
            )
            load_job = client.load_table_from_json(
                rows,
                staging_fqn,
                job_config=load_config,
            )
            load_job.result()
            merge_job = client.query(self._merge_sql(staging_table=staging_table))
            merge_job.result()
            dml_stats = getattr(merge_job, "dml_stats", None)
            inserted = int(getattr(dml_stats, "inserted_row_count", 0) or 0)
            updated = int(getattr(dml_stats, "updated_row_count", 0) or 0)
            if inserted == 0 and updated == 0:
                inserted = len(records)
            return inserted, updated
        finally:
            with contextlib.suppress(Exception):
                client.delete_table(staging_fqn, not_found_ok=True)

    def _live_query(
        self,
        *,
        query_vec: list[float],
        k: int,
        filters: dict[str, Any] | None,
    ) -> list[QueryHit]:
        bigquery = _load_bigquery_module()
        client = bigquery.Client(project=self.project)

        filter_source = None
        meta_filters: dict[str, Any] = {}
        if filters:
            for key, value in filters.items():
                if key == "source":
                    filter_source = value
                else:
                    meta_filters[key] = value

        query_parameters = [
            bigquery.ArrayQueryParameter("query_embedding", "FLOAT64", query_vec),
            bigquery.ScalarQueryParameter("top_k", "INT64", k),
            bigquery.ScalarQueryParameter(
                "source_filter",
                "STRING",
                str(filter_source) if filter_source is not None else None,
            ),
        ]
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        sql = LIVE_VECTOR_SEARCH_SQL_TEMPLATE.format(
            table_sql_name=_quote_bigquery_table(self.project, self.dataset, self.table)
        )
        rows = client.query(sql, job_config=job_config).result()

        hits: list[QueryHit] = []
        for row in rows:
            metadata = _metadata_from_row(_row_value(row, "metadata"))
            if meta_filters:
                matched = True
                for key, expected in meta_filters.items():
                    if metadata.get(key) != expected:
                        matched = False
                        break
                if not matched:
                    continue
            record = VectorRecord(
                id=str(_row_value(row, "id", "")),
                text=str(_row_value(row, "text", "")),
                embedding=[],
                source=str(_row_value(row, "source", "ad_hoc")),
                metadata=metadata,
            )
            distance = _row_value(row, "distance", 1.0)
            try:
                score = 1.0 - float(distance)
            except (TypeError, ValueError):
                score = 0.0
            hits.append(
                QueryHit(
                    id=record.id,
                    text=record.text,
                    score=score,
                    source=record.source,
                    metadata=metadata,
                    created_at=_created_at_to_iso(_row_value(row, "created_at")),
                    provenance=self._build_provenance(record),
                )
            )
        hits.sort(key=lambda h: (-h.score, h.id))
        return hits[:k]

    # -- public API -------------------------------------------------------

    def upsert(
        self,
        records: list[VectorRecord],
        *,
        live_override: bool | None = None,
    ) -> UpsertResult:
        """Insert or replace ``records``. Returns counts.

        Refuses to write more than ``MAX_INDEX_RECORDS_PER_RUN`` per call.
        Records with mismatched embedding dims, empty text, or duplicate
        IDs in the same batch are rejected and recorded in ``errors``.
        Live writes are only attempted when ``mock=False`` *and* the live
        gate passes *and* the per-hour cap allows another call.
        """
        cleaned, errors = _validate_records(records, expected_dims=self.dims)
        skipped_validation = len(records) - len(cleaned)
        if len(cleaned) > MAX_INDEX_RECORDS_PER_RUN:
            errors.append(
                f"truncating batch from {len(cleaned)} to {MAX_INDEX_RECORDS_PER_RUN}"
                f" (MAX_INDEX_RECORDS_PER_RUN cap)"
            )
            cleaned = cleaned[:MAX_INDEX_RECORDS_PER_RUN]

        use_live = live_override if live_override is not None else (not self.mock)
        mode = "mock"
        if use_live:
            gate = self._live_allowed()
            if not gate.allowed:
                return UpsertResult(
                    ok=False,
                    inserted=0,
                    updated=0,
                    skipped=skipped_validation + len(cleaned),
                    errors=errors + [f"live gate refused: {gate.reason}"],
                    mode="live-refused",
                    table=self.table_fqn,
                )
            allowed, reason, calls = self._check_live_rate()
            if not allowed:
                return UpsertResult(
                    ok=False,
                    inserted=0,
                    updated=0,
                    skipped=skipped_validation + len(cleaned),
                    errors=errors + [reason],
                    mode="live-rate-limited",
                    table=self.table_fqn,
                )
            mode = "live"
            try:
                inserted, updated = self._live_upsert(cleaned)
            except Exception as exc:  # BigQuery auth/import/client failures.
                self._record_live_call(calls)
                return UpsertResult(
                    ok=False,
                    inserted=0,
                    updated=0,
                    skipped=skipped_validation + len(cleaned),
                    errors=errors + [f"live BigQuery upsert failed: {exc}"],
                    mode="live-error",
                    table=self.table_fqn,
                )
            self._record_live_call(calls)
            return UpsertResult(
                ok=True,
                inserted=inserted,
                updated=updated,
                skipped=skipped_validation,
                errors=errors,
                mode=mode,
                table=self.table_fqn,
            )

        # Mock path.
        self._ensure_loaded()
        inserted, updated = self._backend.upsert(cleaned)
        try:
            self._backend.save()
        except OSError as exc:
            errors.append(f"mock persistence failed: {exc}")
            return UpsertResult(
                ok=False,
                inserted=inserted,
                updated=updated,
                skipped=skipped_validation,
                errors=errors,
                mode=mode,
                table=self.table_fqn,
            )
        return UpsertResult(
            ok=True,
            inserted=inserted,
            updated=updated,
            skipped=skipped_validation,
            errors=errors,
            mode=mode,
            table=self.table_fqn,
        )

    def query(
        self,
        text: str | None = None,
        *,
        embedding: list[float] | None = None,
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[QueryHit]:
        """Return up to ``k`` ranked hits.

        Pass either ``text`` (the store will embed it via the configured
        embedder) or a precomputed ``embedding``. ``filters`` is an
        optional dict applied to the ``source`` and to ``metadata`` keys —
        equality only; non-matching records are skipped.
        ``k`` is hard-capped at ``MAX_QUERY_K``.
        """
        if k <= 0:
            return []
        k = min(k, MAX_QUERY_K)
        query_vec = self._embed_query(text, embedding)

        if not self.mock:
            gate = self._live_allowed()
            if not gate.allowed:
                return []
            return self._live_query(query_vec=query_vec, k=k, filters=filters)

        self._ensure_loaded()

        filter_source = None
        meta_filters: dict[str, Any] = {}
        if filters:
            for key, value in filters.items():
                if key == "source":
                    filter_source = value
                else:
                    meta_filters[key] = value

        hits: list[QueryHit] = []
        for record in self._backend.all_records():
            if filter_source is not None and record.source != filter_source:
                continue
            if meta_filters:
                ok = True
                for k_meta, v_meta in meta_filters.items():
                    if record.metadata.get(k_meta) != v_meta:
                        ok = False
                        break
                if not ok:
                    continue
            score = cosine_similarity(query_vec, record.embedding)
            created_iso = record.created_at.isoformat() if record.created_at else _now_iso()
            hits.append(
                QueryHit(
                    id=record.id,
                    text=record.text,
                    score=score,
                    source=record.source,
                    metadata=dict(record.metadata),
                    created_at=created_iso,
                    provenance=self._build_provenance(record),
                )
            )
        hits.sort(key=lambda h: (-h.score, h.id))
        return hits[:k]

    def stats(self) -> StoreStats:
        self._ensure_loaded()
        records = self._backend.all_records()
        by_source: dict[str, int] = {}
        for record in records:
            by_source[record.source] = by_source.get(record.source, 0) + 1
        rate_data = _load_live_rate(self._rate_path)
        calls = _prune_calls(list(rate_data.get("calls", [])), now=time.time())
        return StoreStats(
            mode="mock" if self.mock else "live-intent",
            total_records=len(records),
            by_source=dict(sorted(by_source.items())),
            table_fqn=self.table_fqn,
            dims=self.dims,
            last_index_at=self._backend.last_index_at,
            backend_path=str(self._mock_path) if self.mock else None,
            live_calls_last_hour=len(calls),
            max_live_index_per_hour=MAX_LIVE_INDEX_PER_HOUR,
        )

    def stamp_corpus_snapshot(self) -> dict[str, Any]:
        """Return a stamped, provenance-bearing snapshot of the corpus.

        Useful for diligence packets: shows the corpus shape and a hash
        without leaking record text.
        """
        self._ensure_loaded()
        records = self._backend.all_records()
        digest = hashlib.sha256()
        for record in sorted(records, key=lambda r: r.id):
            digest.update(record.id.encode("utf-8"))
            digest.update(b"|")
            for value in record.embedding:
                digest.update(f"{value:.8f}".encode())
            digest.update(b"\n")
        payload = {
            "table": self.table_fqn,
            "dims": self.dims,
            "total_records": len(records),
            "by_source": {
                src: sum(1 for r in records if r.source == src)
                for src in sorted({r.source for r in records})
            },
            "corpus_hash": digest.hexdigest(),
        }
        return stamp(
            payload,
            generator="lib.intel.bq_vector_store.snapshot",
            model=getattr(self.embedder, "name", "mock-hash"),
            metadata={"mode": "mock" if self.mock else "live-intent"},
        )


__all__ = [
    "BQVectorStore",
    "DEFAULT_DIMS",
    "DEFAULT_MOCK_PATH",
    "DEFAULT_RATE_PATH",
    "EMBEDDING_DIMS_HARD",
    "KNOWN_SOURCES",
    "LiveGateResult",
    "LIVE_VECTOR_SEARCH_SQL_TEMPLATE",
    "MAX_INDEX_RECORDS_PER_RUN",
    "MAX_LIVE_INDEX_PER_HOUR",
    "MAX_QUERY_K",
    "QueryHit",
    "StoreStats",
    "UpsertResult",
    "VectorRecord",
    "cosine_similarity",
    "describe_embedder_models",
    "evaluate_live_gate",
]
