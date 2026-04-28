"""Tests for ``lib.intel.embedders``.

The mock embedder is a placeholder and must stay deterministic across
platforms, locales, and process restarts. These tests pin those
properties so the BQ vector store can rely on them.
"""

from __future__ import annotations

import math

import pytest

from lib.intel.embedders import (
    EMBEDDING_DIMS_HARD,
    HashEmbedder,
    VertexGeckoEmbedder,
    default_registry,
    normalize_text,
    tokenize,
)


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def test_hash_embedder_is_deterministic_across_calls():
    embedder = HashEmbedder(dims=128)
    a = embedder.embed("Sapphire intel corpus")
    b = embedder.embed("Sapphire intel corpus")
    assert a == b
    assert len(a) == 128


def test_hash_embedder_is_deterministic_across_instances():
    a = HashEmbedder(dims=64).embed("convergence watchlist solar drone")
    b = HashEmbedder(dims=64).embed("convergence watchlist solar drone")
    assert a == b


def test_hash_embedder_emits_unit_norm_vectors():
    embedder = HashEmbedder(dims=256)
    vector = embedder.embed("hard money self custody bitcoin")
    assert pytest.approx(_norm(vector), rel=1e-6) == 1.0


def test_hash_embedder_empty_string_yields_zero_vector():
    embedder = HashEmbedder(dims=32)
    vector = embedder.embed("   ")
    assert vector == [0.0] * 32


def test_hash_embedder_locale_stable_via_unicode_normalization():
    embedder = HashEmbedder(dims=64)
    # Composed vs decomposed forms of "café" should embed identically.
    composed = "café"
    decomposed = "café"  # e + combining acute accent
    assert composed != decomposed
    assert embedder.embed(composed) == embedder.embed(decomposed)


def test_hash_embedder_dims_must_be_within_bounds():
    with pytest.raises(ValueError):
        HashEmbedder(dims=4)
    with pytest.raises(ValueError):
        HashEmbedder(dims=EMBEDDING_DIMS_HARD + 1)


def test_tokenize_only_keeps_alphanumeric_runs():
    assert tokenize("Hello, World! 2026 — Sapphire") == [
        "hello",
        "world",
        "2026",
        "sapphire",
    ]


def test_normalize_text_handles_non_string_input():
    assert normalize_text(None) == ""
    assert normalize_text(42) == "42"


def test_default_registry_lists_mock_and_placeholders():
    registry = default_registry(dims=128)
    names = registry.names()
    assert "mock-hash" in names
    assert "vertex-gecko" in names
    assert "openai-ada-002" in names
    described = {row["name"]: row for row in registry.describe()}
    assert described["mock-hash"]["dims"] == 128
    assert described["vertex-gecko"]["kind"] == "VertexGeckoEmbedder"


def test_future_placeholder_embedder_fails_closed():
    registry = default_registry(dims=64)
    placeholder = registry.get("openai-ada-002")
    with pytest.raises(NotImplementedError):
        placeholder.embed("anything")


def test_vertex_registry_entry_defaults_to_dry_run():
    registry = default_registry(dims=64)
    vertex = registry.get("vertex-gecko")
    assert isinstance(vertex, VertexGeckoEmbedder)
    assert vertex.metadata["mode_actual"] == "dry-run"
    assert len(vertex.embed("anything")) == 64


def test_embed_batch_matches_embed():
    embedder = HashEmbedder(dims=64)
    texts = ["alpha beta", "gamma delta", "alpha beta"]
    batched = embedder.embed_batch(texts)
    assert batched[0] == embedder.embed("alpha beta")
    assert batched[2] == batched[0]
    assert batched[1] != batched[0]
