"""Mock-only tests for the live BigQuery vector store path.

The real ``google.cloud.bigquery.Client`` is never constructed here. Tests
swap in a small fake module after the live gate passes, which keeps CI
offline while still pinning the BigQuery schema, SQL, and parameter shape.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import lib.intel.bq_vector_store as bq_vector_store
from lib.core.provenance import verify
from lib.intel.bq_vector_store import (
    MAX_LIVE_INDEX_PER_HOUR,
    BQVectorStore,
    VectorRecord,
)
from lib.intel.embedders import HashEmbedder

DIMS = 16


@dataclass
class FakeSchemaField:
    name: str
    field_type: str
    mode: str = "NULLABLE"


class FakeTable:
    def __init__(self, table_id: str, *, schema: list[FakeSchemaField] | None = None):
        self.table_id = table_id
        self.schema = schema or []


class FakeLoadJobConfig:
    def __init__(self, **kwargs: Any):
        self.kwargs = dict(kwargs)


class FakeQueryJobConfig:
    def __init__(self, *, query_parameters: list[Any] | None = None):
        self.query_parameters = list(query_parameters or [])


class FakeQueryParameter:
    def __init__(self, name: str, kind: str, value: Any):
        self.name = name
        self.kind = kind
        self.value = value


class FakeJob:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        inserted: int = 0,
        updated: int = 0,
    ):
        self._rows = list(rows or [])
        self.dml_stats = type(
            "FakeDmlStats",
            (),
            {
                "inserted_row_count": inserted,
                "updated_row_count": updated,
            },
        )()

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class FakeBigQueryModule:
    SchemaField = FakeSchemaField
    Table = FakeTable
    LoadJobConfig = FakeLoadJobConfig
    QueryJobConfig = FakeQueryJobConfig
    ArrayQueryParameter = FakeQueryParameter
    ScalarQueryParameter = FakeQueryParameter
    WriteDisposition = type(
        "FakeWriteDisposition",
        (),
        {"WRITE_TRUNCATE": "WRITE_TRUNCATE"},
    )

    def __init__(self) -> None:
        self.clients: list[Any] = []
        self.query_rows: list[dict[str, Any]] = []
        self.inserted_row_count = 1
        self.updated_row_count = 0
        self.client_error: Exception | None = None

        module = self

        class Client:
            def __init__(self, *, project: str):
                if module.client_error is not None:
                    raise module.client_error
                self.project = project
                self.create_table_calls: list[tuple[FakeTable, bool]] = []
                self.load_calls: list[dict[str, Any]] = []
                self.query_calls: list[dict[str, Any]] = []
                self.delete_table_calls: list[tuple[str, bool]] = []
                module.clients.append(self)

            def create_table(self, table: FakeTable, *, exists_ok: bool = False):
                self.create_table_calls.append((table, exists_ok))
                return table

            def load_table_from_json(
                self,
                rows: list[dict[str, Any]],
                destination: str,
                *,
                job_config: FakeLoadJobConfig,
            ) -> FakeJob:
                self.load_calls.append(
                    {
                        "rows": rows,
                        "destination": destination,
                        "job_config": job_config,
                    }
                )
                return FakeJob()

            def query(
                self,
                sql: str,
                *,
                job_config: FakeQueryJobConfig | None = None,
            ) -> FakeJob:
                self.query_calls.append({"sql": sql, "job_config": job_config})
                if sql.lstrip().upper().startswith("MERGE"):
                    return FakeJob(
                        inserted=module.inserted_row_count,
                        updated=module.updated_row_count,
                    )
                return FakeJob(rows=module.query_rows)

            def delete_table(self, table_id: str, *, not_found_ok: bool = False) -> None:
                self.delete_table_calls.append((table_id, not_found_ok))

        self.Client = Client


def _allow_live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    return creds


def _deny_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAPPHIRE_BQ_LIVE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("SAPPHIRE_BQ_PROJECT", raising=False)


def _store(tmp_path: Path, *, mock: bool = False) -> BQVectorStore:
    return BQVectorStore(
        project="sapphire-test",
        dataset="intel",
        table="vectors",
        mock=mock,
        embedder=HashEmbedder(dims=DIMS),
        dims=DIMS,
        mock_path=tmp_path / "mock.jsonl",
        rate_path=tmp_path / "rate.json",
    )


def _record(store: BQVectorStore, *, rec_id: str = "rec-1") -> VectorRecord:
    text = f"live vector intel {rec_id}"
    return VectorRecord(
        id=rec_id,
        text=text,
        embedding=store.embedder.embed(text),
        source="sovereign_thesis",
        metadata={"asset": "BTC", "rank": 1},
        created_at=datetime(2026, 4, 28, tzinfo=UTC),
    )


def _install_fake_bigquery(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeBigQueryModule | None = None,
) -> FakeBigQueryModule:
    module = fake or FakeBigQueryModule()
    monkeypatch.setattr(bq_vector_store, "_load_bigquery_module", lambda: module)
    return module


def _param(job_config: FakeQueryJobConfig, name: str) -> FakeQueryParameter:
    for parameter in job_config.query_parameters:
        if parameter.name == name:
            return parameter
    raise AssertionError(f"missing query parameter {name!r}")


def test_live_upsert_does_not_import_bigquery_when_env_unset(tmp_path, monkeypatch):
    _deny_live(monkeypatch)
    store = _store(tmp_path)
    monkeypatch.setattr(
        bq_vector_store,
        "_load_bigquery_module",
        lambda: pytest.fail("BigQuery import should not happen"),
    )

    result = store.upsert([_record(store)])

    assert result.ok is False
    assert result.mode == "live-refused"
    assert not (tmp_path / "mock.jsonl").exists()


def test_live_query_does_not_import_bigquery_when_env_unset(tmp_path, monkeypatch):
    _deny_live(monkeypatch)
    store = _store(tmp_path)
    monkeypatch.setattr(
        bq_vector_store,
        "_load_bigquery_module",
        lambda: pytest.fail("BigQuery import should not happen"),
    )

    assert store.query("bitcoin", k=3) == []


def test_live_upsert_refuses_when_project_env_missing(tmp_path, monkeypatch):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.delenv("SAPPHIRE_BQ_PROJECT", raising=False)
    store = _store(tmp_path)
    monkeypatch.setattr(
        bq_vector_store,
        "_load_bigquery_module",
        lambda: pytest.fail("BigQuery import should not happen"),
    )

    result = store.upsert([_record(store)])

    assert result.ok is False
    assert result.mode == "live-refused"
    assert any("SAPPHIRE_BQ_PROJECT" in error for error in result.errors)


def test_live_upsert_refuses_when_credentials_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    store = _store(tmp_path)
    monkeypatch.setattr(
        bq_vector_store,
        "_load_bigquery_module",
        lambda: pytest.fail("BigQuery import should not happen"),
    )

    result = store.upsert([_record(store)])

    assert result.ok is False
    assert result.mode == "live-refused"


def test_live_upsert_imports_bigquery_lazily_when_gate_passes(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    result = store.upsert([_record(store)])

    assert result.ok is True
    assert result.mode == "live"
    assert len(fake.clients) == 1


def test_live_upsert_creates_target_table_idempotently(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.upsert([_record(store)])

    client = fake.clients[0]
    target_table, exists_ok = client.create_table_calls[0]
    assert target_table.table_id == "sapphire-test.intel.vectors"
    assert exists_ok is True


def test_live_upsert_schema_has_expected_columns(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.upsert([_record(store)])

    target_table = fake.clients[0].create_table_calls[0][0]
    schema = {field.name: field for field in target_table.schema}
    assert set(schema) == {"id", "text", "embedding", "source", "metadata", "created_at"}
    assert schema["id"].field_type == "STRING"
    assert schema["text"].field_type == "STRING"
    assert schema["embedding"].field_type == "FLOAT64"
    assert schema["embedding"].mode == "REPEATED"
    assert schema["source"].field_type == "STRING"
    assert schema["metadata"].field_type == "JSON"
    assert schema["created_at"].field_type == "TIMESTAMP"


def test_live_upsert_loads_json_rows_into_staging_table(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)
    record = _record(store, rec_id="row-load")

    store.upsert([record])

    load_call = fake.clients[0].load_calls[0]
    assert load_call["destination"].startswith("sapphire-test.intel._vectors_stage_")
    row = load_call["rows"][0]
    assert row["id"] == "row-load"
    assert row["text"] == record.text
    assert row["embedding"] == pytest.approx(record.embedding)
    assert row["metadata"] == {"asset": "BTC", "rank": 1}
    assert row["created_at"] == "2026-04-28T00:00:00+00:00"


def test_live_upsert_uses_merge_sql_for_upsert(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.upsert([_record(store)])

    sql = fake.clients[0].query_calls[0]["sql"]
    assert sql.startswith("MERGE `sapphire-test.intel.vectors` AS T")
    assert "USING `sapphire-test.intel._vectors_stage_" in sql
    assert "WHEN MATCHED THEN" in sql
    assert "WHEN NOT MATCHED THEN" in sql


def test_live_upsert_returns_bigquery_dml_counts(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = FakeBigQueryModule()
    fake.inserted_row_count = 3
    fake.updated_row_count = 2
    _install_fake_bigquery(monkeypatch, fake)
    store = _store(tmp_path)

    result = store.upsert([_record(store, rec_id="counts")])

    assert result.inserted == 3
    assert result.updated == 2


def test_live_upsert_deletes_staging_table_after_merge(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.upsert([_record(store)])

    assert len(fake.clients[0].delete_table_calls) == 1
    table_id, not_found_ok = fake.clients[0].delete_table_calls[0]
    assert table_id.startswith("sapphire-test.intel._vectors_stage_")
    assert not_found_ok is True


def test_live_upsert_auth_failure_returns_error_without_unmocked_call(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = FakeBigQueryModule()
    fake.client_error = RuntimeError("auth boom")
    _install_fake_bigquery(monkeypatch, fake)
    store = _store(tmp_path)

    result = store.upsert([_record(store)])

    assert result.ok is False
    assert result.mode == "live-error"
    assert any("auth boom" in error for error in result.errors)
    assert fake.clients == []


def test_live_upsert_rate_limit_prevents_client_call(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    rate_path = tmp_path / "rate.json"
    rate_path.write_text(
        '{"calls": [' + ",".join(str(time.time()) for _ in range(MAX_LIVE_INDEX_PER_HOUR)) + "]}",
        encoding="utf-8",
    )
    store = _store(tmp_path)
    monkeypatch.setattr(
        bq_vector_store,
        "_load_bigquery_module",
        lambda: pytest.fail("BigQuery import should not happen"),
    )

    result = store.upsert([_record(store)])

    assert result.ok is False
    assert result.mode == "live-rate-limited"


def test_live_query_uses_vector_search_sql(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.query("bitcoin", k=4)

    sql = fake.clients[0].query_calls[0]["sql"]
    assert "VECTOR_SEARCH(" in sql
    assert "TABLE `sapphire-test.intel.vectors`" in sql
    assert "'embedding'" in sql
    assert "distance_type => 'COSINE'" in sql


def test_live_query_does_not_create_table(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.query("bitcoin", k=4)

    assert fake.clients[0].create_table_calls == []


def test_live_query_uses_parameterized_vector_search(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)
    embedding = [0.1] * DIMS

    store.query(embedding=embedding, k=4, filters={"source": "threat_intel"})

    call = fake.clients[0].query_calls[0]
    assert "@query_embedding" in call["sql"]
    assert "@top_k" in call["sql"]
    assert "@source_filter" in call["sql"]
    job_config = call["job_config"]
    assert _param(job_config, "query_embedding").value == embedding
    assert _param(job_config, "top_k").value == 4
    assert _param(job_config, "source_filter").value == "threat_intel"


def test_live_query_does_not_inline_source_filter_value(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = _install_fake_bigquery(monkeypatch)
    store = _store(tmp_path)

    store.query("breach intel", k=2, filters={"source": "threat_intel"})

    sql = fake.clients[0].query_calls[0]["sql"]
    assert "threat_intel" not in sql
    assert _param(fake.clients[0].query_calls[0]["job_config"], "source_filter").value == (
        "threat_intel"
    )


def test_live_query_maps_rows_to_hits_with_score_and_provenance(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = FakeBigQueryModule()
    fake.query_rows = [
        {
            "id": "hit-1",
            "text": "Bitcoin sovereign reserve thesis",
            "source": "sovereign_thesis",
            "metadata": {"asset": "BTC"},
            "created_at": datetime(2026, 4, 28, tzinfo=UTC),
            "distance": 0.25,
        }
    ]
    _install_fake_bigquery(monkeypatch, fake)
    store = _store(tmp_path)

    hits = store.query("bitcoin", k=1)

    assert len(hits) == 1
    assert hits[0].id == "hit-1"
    assert hits[0].score == pytest.approx(0.75)
    assert hits[0].metadata == {"asset": "BTC"}
    assert hits[0].created_at == "2026-04-28T00:00:00+00:00"
    assert verify(hits[0].provenance) is True
    assert hits[0].provenance["metadata"]["mode"] == "live"


def test_live_query_applies_metadata_filters_after_vector_search(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = FakeBigQueryModule()
    fake.query_rows = [
        {
            "id": "btc",
            "text": "btc",
            "source": "sovereign_thesis",
            "metadata": {"asset": "BTC"},
            "created_at": "2026-04-28T00:00:00+00:00",
            "distance": 0.1,
        },
        {
            "id": "eth",
            "text": "eth",
            "source": "sovereign_thesis",
            "metadata": {"asset": "ETH"},
            "created_at": "2026-04-28T00:00:00+00:00",
            "distance": 0.2,
        },
    ]
    _install_fake_bigquery(monkeypatch, fake)
    store = _store(tmp_path)

    hits = store.query("reserve asset", k=2, filters={"asset": "BTC"})

    assert [hit.id for hit in hits] == ["btc"]


def test_live_query_surfaces_client_auth_failure(tmp_path, monkeypatch):
    _allow_live(monkeypatch, tmp_path)
    fake = FakeBigQueryModule()
    fake.client_error = RuntimeError("auth boom")
    _install_fake_bigquery(monkeypatch, fake)
    store = _store(tmp_path)

    with pytest.raises(RuntimeError, match="auth boom"):
        store.query("bitcoin", k=1)
