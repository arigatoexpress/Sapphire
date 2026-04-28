"""Tests for ``lib.intel.bq_vector_store``.

The mock backend is the only path exercised here. The live backend is
verified through env-flag gating only (no live BigQuery calls).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.core.provenance import verify
from lib.intel.bq_vector_store import (
    DEFAULT_DIMS,
    EMBEDDING_DIMS_HARD,
    KNOWN_SOURCES,
    MAX_INDEX_RECORDS_PER_RUN,
    MAX_LIVE_INDEX_PER_HOUR,
    MAX_QUERY_K,
    BQVectorStore,
    QueryHit,
    UpsertResult,
    VectorRecord,
    cosine_similarity,
    evaluate_live_gate,
)
from lib.intel.embedders import HashEmbedder

DIMS = 64


def _make_store(tmp_path: Path, *, mock: bool = True, dims: int = DIMS) -> BQVectorStore:
    embedder = HashEmbedder(dims=dims)
    return BQVectorStore(
        project="sapphire-test",
        dataset="intel",
        table="vectors",
        mock=mock,
        embedder=embedder,
        dims=dims,
        mock_path=tmp_path / "mock.jsonl",
        rate_path=tmp_path / "rate.json",
    )


def _record(store: BQVectorStore, text: str, source: str, **metadata) -> VectorRecord:
    embedding = store.embedder.embed(text)
    return VectorRecord(
        id="",
        text=text,
        embedding=embedding,
        source=source,
        metadata=dict(metadata),
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------


def test_store_requires_project_dataset_table(tmp_path):
    with pytest.raises(ValueError):
        BQVectorStore("", "d", "t", mock_path=tmp_path / "x.jsonl", rate_path=tmp_path / "y.json")


def test_store_dims_bounded(tmp_path):
    with pytest.raises(ValueError):
        BQVectorStore(
            "p",
            "d",
            "t",
            mock=True,
            embedder=HashEmbedder(dims=64),
            dims=EMBEDDING_DIMS_HARD + 1,
            mock_path=tmp_path / "x.jsonl",
            rate_path=tmp_path / "y.json",
        )


def test_store_embedder_dims_must_match(tmp_path):
    with pytest.raises(ValueError):
        BQVectorStore(
            "p",
            "d",
            "t",
            mock=True,
            embedder=HashEmbedder(dims=128),
            dims=64,
            mock_path=tmp_path / "x.jsonl",
            rate_path=tmp_path / "y.json",
        )


def test_table_fqn_format(tmp_path):
    store = _make_store(tmp_path)
    assert store.table_fqn == "sapphire-test.intel.vectors"


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def test_upsert_inserts_then_updates(tmp_path):
    store = _make_store(tmp_path)
    rec1 = _record(store, "Bitcoin is hard money", "sovereign_thesis")
    result = store.upsert([rec1])
    assert isinstance(result, UpsertResult)
    assert result.ok is True
    assert result.inserted == 1
    assert result.updated == 0
    # Re-upsert with same derived ID should update.
    rec2 = _record(store, "Bitcoin is hard money", "sovereign_thesis")
    result2 = store.upsert([rec2])
    assert result2.inserted == 0
    assert result2.updated == 1


def test_upsert_rejects_dim_mismatch(tmp_path):
    store = _make_store(tmp_path)
    bad = VectorRecord(
        id="x",
        text="bad",
        embedding=[0.1, 0.2, 0.3],  # wrong dims
        source="ad_hoc",
    )
    result = store.upsert([bad])
    assert result.inserted == 0
    assert any("embedding dims" in e for e in result.errors)


def test_upsert_rejects_empty_text(tmp_path):
    store = _make_store(tmp_path)
    embedding = store.embedder.embed("placeholder")
    bad = VectorRecord(id="x", text="   ", embedding=embedding, source="ad_hoc")
    result = store.upsert([bad])
    assert result.inserted == 0
    assert any("empty text" in e for e in result.errors)


def test_upsert_dedupes_within_batch(tmp_path):
    store = _make_store(tmp_path)
    embedding = store.embedder.embed("dup")
    rec_a = VectorRecord(id="dup-1", text="dup text", embedding=embedding, source="ad_hoc")
    rec_b = VectorRecord(id="dup-1", text="dup text", embedding=embedding, source="ad_hoc")
    result = store.upsert([rec_a, rec_b])
    assert result.inserted == 1
    assert any("duplicate ID" in e for e in result.errors)


def test_upsert_truncates_at_max_records(tmp_path):
    store = _make_store(tmp_path)
    embedding = store.embedder.embed("filler")
    over = MAX_INDEX_RECORDS_PER_RUN + 5
    records = [
        VectorRecord(
            id=f"id-{i}",
            text=f"row {i}",
            embedding=embedding,
            source="ad_hoc",
        )
        for i in range(over)
    ]
    result = store.upsert(records)
    assert result.inserted == MAX_INDEX_RECORDS_PER_RUN
    assert any(f"truncating batch from {over}" in e for e in result.errors)


def test_upsert_keeps_unknown_source_with_warning(tmp_path):
    store = _make_store(tmp_path)
    embedding = store.embedder.embed("custom")
    rec = VectorRecord(
        id="x", text="custom intel", embedding=embedding, source="custom_source"
    )
    result = store.upsert([rec])
    assert result.inserted == 1
    assert any("unknown source" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def test_query_ranks_by_cosine_similarity(tmp_path):
    store = _make_store(tmp_path)
    closer = _record(
        store, "bitcoin is the hardest asset", "sovereign_thesis", asset="BTC"
    )
    farther = _record(store, "fluffy clouds drift gently", "ad_hoc", asset="CLOUD")
    store.upsert([closer, farther])
    hits = store.query("bitcoin hardest asset", k=2)
    assert len(hits) == 2
    assert hits[0].id == closer.id or hits[0].text == closer.text
    assert hits[0].score >= hits[1].score


def test_query_truncates_at_k_cap(tmp_path):
    store = _make_store(tmp_path)
    embedding = store.embedder.embed("filler")
    records = [
        VectorRecord(
            id=f"id-{i}",
            text=f"signal {i}",
            embedding=embedding,
            source="ad_hoc",
        )
        for i in range(MAX_QUERY_K + 10)
    ]
    store.upsert(records)
    hits = store.query("signal", k=MAX_QUERY_K + 100)
    assert len(hits) <= MAX_QUERY_K


def test_query_filters_on_source(tmp_path):
    store = _make_store(tmp_path)
    a = _record(store, "alpha", "sovereign_thesis", topic="alpha")
    b = _record(store, "alpha", "convergence_watchlist", topic="alpha")
    store.upsert([a, b])
    hits = store.query("alpha", k=10, filters={"source": "convergence_watchlist"})
    assert len(hits) == 1
    assert hits[0].source == "convergence_watchlist"


def test_query_filters_on_metadata(tmp_path):
    store = _make_store(tmp_path)
    a = _record(store, "alpha thesis", "sovereign_thesis", asset="BTC")
    b = _record(store, "alpha thesis", "sovereign_thesis", asset="ETH")
    store.upsert([a, b])
    hits = store.query("alpha", k=10, filters={"asset": "BTC"})
    assert len(hits) == 1
    assert hits[0].metadata.get("asset") == "BTC"


def test_query_requires_text_or_embedding(tmp_path):
    store = _make_store(tmp_path)
    with pytest.raises(ValueError):
        store.query()


def test_query_with_explicit_embedding(tmp_path):
    store = _make_store(tmp_path)
    rec = _record(store, "Sapphire intel", "sovereign_thesis")
    store.upsert([rec])
    embedding = store.embedder.embed("Sapphire intel")
    hits = store.query(embedding=embedding, k=1)
    assert len(hits) == 1
    # ID is derived for records that omit it; just assert text matches.
    assert hits[0].text == "Sapphire intel"


def test_query_zero_k_returns_empty(tmp_path):
    store = _make_store(tmp_path)
    rec = _record(store, "anything", "ad_hoc")
    store.upsert([rec])
    assert store.query("anything", k=0) == []


def test_query_hits_carry_provenance_envelope(tmp_path):
    store = _make_store(tmp_path)
    rec = _record(store, "Sovereign thesis on hard money", "sovereign_thesis")
    store.upsert([rec])
    hits = store.query("hard money", k=1)
    assert len(hits) == 1
    hit = hits[0]
    assert isinstance(hit, QueryHit)
    provenance = hit.provenance
    assert provenance.get("schema_version") == 1
    assert provenance.get("generator") == "lib.intel.bq_vector_store"
    # Envelope itself must verify.
    assert verify(provenance) is True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_mock_persistence_roundtrip(tmp_path):
    store = _make_store(tmp_path)
    rec = _record(store, "persist me", "convergence_watchlist", asset="SOL")
    store.upsert([rec])
    # Recreate the store; data should reload from disk.
    reborn = _make_store(tmp_path)
    hits = reborn.query("persist me", k=1)
    assert len(hits) == 1
    assert hits[0].text == "persist me"
    # File contains a __meta__ row plus the record row.
    raw = (tmp_path / "mock.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"__meta__": true' in line for line in raw)
    assert any('"persist me"' in line for line in raw)


def test_mock_skips_corrupt_lines(tmp_path):
    store = _make_store(tmp_path)
    rec = _record(store, "good record", "sovereign_thesis")
    store.upsert([rec])
    # Corrupt the file by appending garbage.
    path = tmp_path / "mock.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n{not-json}\n")
    reborn = _make_store(tmp_path)
    hits = reborn.query("good record", k=1)
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Live gating
# ---------------------------------------------------------------------------


def test_live_gate_default_blocks(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_BQ_LIVE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("SAPPHIRE_BQ_PROJECT", raising=False)
    gate = evaluate_live_gate(project="sapphire-test")
    assert gate.allowed is False
    assert "SAPPHIRE_BQ_LIVE" in gate.reason


def test_live_gate_requires_credentials_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    gate = evaluate_live_gate(project="sapphire-test")
    assert gate.allowed is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" in gate.reason


def test_live_gate_requires_project_match(tmp_path, monkeypatch):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "other-project")
    gate = evaluate_live_gate(project="sapphire-test")
    assert gate.allowed is False
    assert "mismatches" in gate.reason


def test_live_gate_passes_with_all_three(tmp_path, monkeypatch):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    gate = evaluate_live_gate(project="sapphire-test")
    assert gate.allowed is True


def test_upsert_refuses_live_when_gate_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_BQ_LIVE", raising=False)
    store = _make_store(tmp_path, mock=False)
    rec = _record(store, "would-be-live", "sovereign_thesis")
    result = store.upsert([rec])
    assert result.ok is False
    assert result.mode == "live-refused"
    # No state was persisted in either backend.
    assert not (tmp_path / "mock.jsonl").exists()


def test_upsert_records_failed_live_attempt_for_rate_accounting(tmp_path, monkeypatch):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    monkeypatch.setattr(
        "lib.intel.bq_vector_store._load_bigquery_module",
        lambda: (_ for _ in ()).throw(RuntimeError("mock auth failure")),
    )
    store = _make_store(tmp_path, mock=False)
    rec = _record(store, "would-be-live", "sovereign_thesis")
    result = store.upsert([rec])
    # Failed live attempts still count toward the local rate guard, which
    # prevents a broken caller from hammering BigQuery/auth repeatedly.
    assert result.ok is False
    assert result.mode == "live-error"
    rate = json.loads((tmp_path / "rate.json").read_text(encoding="utf-8"))
    assert len(rate["calls"]) == 1


def test_live_rate_limit_trips(tmp_path, monkeypatch):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SAPPHIRE_BQ_LIVE", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("SAPPHIRE_BQ_PROJECT", "sapphire-test")
    rate_path = tmp_path / "rate.json"
    import time

    rate_path.write_text(
        json.dumps({"calls": [time.time()] * MAX_LIVE_INDEX_PER_HOUR}), encoding="utf-8"
    )
    store = _make_store(tmp_path, mock=False)
    rec = _record(store, "would-be-live", "sovereign_thesis")
    result = store.upsert([rec])
    assert result.ok is False
    assert result.mode == "live-rate-limited"


# ---------------------------------------------------------------------------
# Stats / snapshot
# ---------------------------------------------------------------------------


def test_stats_groups_by_source(tmp_path):
    store = _make_store(tmp_path)
    store.upsert(
        [
            _record(store, "a", "sovereign_thesis"),
            _record(store, "b", "convergence_watchlist"),
            _record(store, "c", "convergence_watchlist"),
        ]
    )
    stats = store.stats()
    assert stats.total_records == 3
    assert stats.by_source["convergence_watchlist"] == 2
    assert stats.by_source["sovereign_thesis"] == 1
    assert stats.dims == DIMS
    assert stats.table_fqn == "sapphire-test.intel.vectors"


def test_stamp_corpus_snapshot_is_provenance_verified(tmp_path):
    store = _make_store(tmp_path)
    store.upsert([_record(store, "snapshot me", "sovereign_thesis")])
    snapshot = store.stamp_corpus_snapshot()
    assert snapshot["provenance"]["schema_version"] == 1
    assert verify(snapshot) is True
    assert snapshot["total_records"] == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_cosine_similarity_handles_zero_vectors():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_known_sources_has_canonical_intel_buckets():
    assert "sovereign_thesis" in KNOWN_SOURCES
    assert "convergence_watchlist" in KNOWN_SOURCES
    assert "threat_intel" in KNOWN_SOURCES


def test_default_dims_is_768():
    assert DEFAULT_DIMS == 768
