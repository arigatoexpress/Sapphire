"""Tests for the guarded Vertex Gecko embedder.

No test calls Google. Live behavior is exercised only through a mocked
``google.generativeai`` module installed in ``sys.modules``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lib.intel.bq_vector_store import describe_embedder_models
from lib.intel.embedders import (
    DEFAULT_EMBEDDING_DIMS,
    EMBEDDING_DIMS_HARD,
    MAX_EMBED_CALLS_PER_HOUR,
    MAX_EMBED_TOKENS_PER_MONTH,
    VERTEX_GECKO_MODEL,
    VertexGeckoEmbedder,
)


class FakeGenerativeAI:
    def __init__(self, embedding: list[float] | None = None, *, error: Exception | None = None):
        self.embedding = embedding if embedding is not None else [0.01] * DEFAULT_EMBEDDING_DIMS
        self.error = error
        self.configured_api_key: str | None = None
        self.calls: list[dict[str, Any]] = []

    def configure(self, *, api_key: str) -> None:
        self.configured_api_key = api_key

    def embed_content(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"embedding": list(self.embedding)}


def _install_fake_genai(monkeypatch: pytest.MonkeyPatch, fake: FakeGenerativeAI) -> None:
    google = types.ModuleType("google")
    google.generativeai = fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)


def _write_secret(path: Path, key: str = "GEMINI_API_KEY", value: str = "test-key") -> None:
    path.write_text(f"{key}={value}\n", encoding="utf-8")


def _live_embedder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeGenerativeAI,
    *,
    dims: int = DEFAULT_EMBEDDING_DIMS,
    secret_key: str = "GEMINI_API_KEY",
) -> VertexGeckoEmbedder:
    _install_fake_genai(monkeypatch, fake)
    secrets_file = tmp_path / "secrets.env"
    _write_secret(secrets_file, key=secret_key)
    return VertexGeckoEmbedder(
        dims=dims,
        cache_dir=tmp_path / "cache",
        secrets_file=secrets_file,
        env={"SAPPHIRE_VERTEX_EMBEDDER_LIVE": "1"},
    )


def _month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def test_dry_run_default_returns_deterministic_mock_vector(tmp_path):
    embedder = VertexGeckoEmbedder(cache_dir=tmp_path / "cache", secrets_file=tmp_path / "none")
    first = embedder.embed("Sapphire semantic search")
    second = embedder.embed("Sapphire semantic search")

    assert first == second
    assert len(first) == DEFAULT_EMBEDDING_DIMS
    assert embedder.metadata["mode_actual"] == "dry-run"
    assert embedder.metadata["cached"] is False
    assert not (tmp_path / "cache").exists()


def test_dry_run_constructor_does_not_import_google_sdk(tmp_path):
    embedder = VertexGeckoEmbedder(
        cache_dir=tmp_path / "cache",
        secrets_file=tmp_path / "none",
        env={},
    )

    assert embedder._sdk is None
    assert embedder.metadata["mode_requested"] == "dry-run"


def test_live_flag_without_key_falls_back_to_dry_run_safety(tmp_path, monkeypatch):
    fake = FakeGenerativeAI()
    _install_fake_genai(monkeypatch, fake)
    embedder = VertexGeckoEmbedder(
        cache_dir=tmp_path / "cache",
        secrets_file=tmp_path / "missing.env",
        env={"SAPPHIRE_VERTEX_EMBEDDER_LIVE": "1"},
    )

    vector = embedder.embed("no key means no spend")

    assert len(vector) == DEFAULT_EMBEDDING_DIMS
    assert embedder.metadata["mode_actual"] == "dry-run-safety"
    assert "API key is absent" in embedder.metadata["fallback_reason"]
    assert fake.calls == []


def test_environment_key_without_secrets_file_does_not_enable_live(tmp_path, monkeypatch):
    fake = FakeGenerativeAI()
    _install_fake_genai(monkeypatch, fake)
    embedder = VertexGeckoEmbedder(
        cache_dir=tmp_path / "cache",
        secrets_file=tmp_path / "missing.env",
        env={
            "SAPPHIRE_VERTEX_EMBEDDER_LIVE": "1",
            "GEMINI_API_KEY": "ignored-env-key",
        },
    )

    embedder.embed("env-only key is intentionally ignored")

    assert embedder.metadata["mode_actual"] == "dry-run-safety"
    assert embedder.metadata["api_key_present"] is False
    assert fake.calls == []


def test_live_with_mocked_sdk_returns_768_dim_vector_and_call_args(tmp_path, monkeypatch):
    live_vector = [float(i) / 1000.0 for i in range(DEFAULT_EMBEDDING_DIMS)]
    fake = FakeGenerativeAI(live_vector)
    embedder = _live_embedder(tmp_path, monkeypatch, fake)

    vector = embedder.embed("semantic substrate")

    assert vector == live_vector
    assert len(vector) == 768
    assert fake.configured_api_key == "test-key"
    assert fake.calls == [
        {
            "model": VERTEX_GECKO_MODEL,
            "content": "semantic substrate",
            "task_type": "retrieval_document",
            "output_dimensionality": DEFAULT_EMBEDDING_DIMS,
        }
    ]
    assert embedder.metadata["mode_actual"] == "live"


def test_live_accepts_google_api_key_from_secrets_file(tmp_path, monkeypatch):
    fake = FakeGenerativeAI()
    embedder = _live_embedder(tmp_path, monkeypatch, fake, secret_key="GOOGLE_API_KEY")

    embedder.embed("alternate key name")

    assert fake.configured_api_key == "test-key"
    assert embedder.metadata["api_key_source"] == "GOOGLE_API_KEY"
    assert embedder.metadata["mode_actual"] == "live"


def test_cache_short_circuits_repeat_live_call(tmp_path, monkeypatch):
    fake = FakeGenerativeAI([0.25] * DEFAULT_EMBEDDING_DIMS)
    embedder = _live_embedder(tmp_path, monkeypatch, fake)

    first = embedder.embed("cache me once")
    fake.embedding = [0.5] * DEFAULT_EMBEDDING_DIMS
    second = embedder.embed("cache me once")

    assert first == second
    assert len(fake.calls) == 1
    assert embedder.metadata["cached"] is True
    assert embedder.metadata["mode_actual"] == "live"


def test_cache_key_and_payload_include_model_dimension_and_input_hash(tmp_path, monkeypatch):
    fake = FakeGenerativeAI([0.125] * DEFAULT_EMBEDDING_DIMS)
    embedder = _live_embedder(tmp_path, monkeypatch, fake)
    text = "cache key inspection"

    embedder.embed(text)

    input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_files = [
        path for path in (tmp_path / "cache").glob("*.json") if path.name != "counters.json"
    ]
    assert len(cache_files) == 1
    assert ".d768." in cache_files[0].name
    assert input_hash in cache_files[0].name
    payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert payload["model"] == VERTEX_GECKO_MODEL
    assert payload["dims"] == DEFAULT_EMBEDDING_DIMS
    assert payload["input_sha256"] == input_hash


def test_hourly_call_cap_triggers_dry_run_fallback(tmp_path, monkeypatch):
    fake = FakeGenerativeAI()
    embedder = _live_embedder(tmp_path, monkeypatch, fake)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "counters.json").write_text(
        json.dumps(
            {
                "calls": [datetime.now(UTC).timestamp()] * MAX_EMBED_CALLS_PER_HOUR,
                "month_key": _month_key(),
                "month_tokens": 0,
            }
        ),
        encoding="utf-8",
    )

    vector = embedder.embed("cap should fall back")

    assert len(vector) == DEFAULT_EMBEDDING_DIMS
    assert embedder.metadata["mode_actual"] == "dry-run-rate-limited"
    assert fake.calls == []


def test_monthly_token_cap_triggers_dry_run_fallback(tmp_path, monkeypatch):
    fake = FakeGenerativeAI()
    embedder = _live_embedder(tmp_path, monkeypatch, fake)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "counters.json").write_text(
        json.dumps(
            {
                "calls": [],
                "month_key": _month_key(),
                "month_tokens": MAX_EMBED_TOKENS_PER_MONTH,
            }
        ),
        encoding="utf-8",
    )

    embedder.embed("monthly cap should fall back")

    assert embedder.metadata["mode_actual"] == "dry-run-rate-limited"
    assert embedder.metadata["month_tokens"] == MAX_EMBED_TOKENS_PER_MONTH
    assert fake.calls == []


def test_dimension_mismatch_rejects_live_response_and_falls_back(tmp_path, monkeypatch):
    fake = FakeGenerativeAI([0.1] * 12)
    embedder = _live_embedder(tmp_path, monkeypatch, fake)

    vector = embedder.embed("bad dimension from provider")

    assert len(vector) == DEFAULT_EMBEDDING_DIMS
    assert vector != [0.1] * 12
    assert embedder.metadata["mode_actual"] == "dry-run-dim-mismatch"
    assert "12 != 768" in embedder.metadata["fallback_reason"]


def test_sdk_error_falls_back_without_cache_write(tmp_path, monkeypatch):
    fake = FakeGenerativeAI(error=RuntimeError("boom"))
    embedder = _live_embedder(tmp_path, monkeypatch, fake)

    vector = embedder.embed("provider exception")

    assert len(vector) == DEFAULT_EMBEDDING_DIMS
    assert embedder.metadata["mode_actual"] == "dry-run-live-error"
    assert embedder.metadata["fallback_reason"] == "RuntimeError"
    cache_files = list((tmp_path / "cache").glob("*.json")) if (tmp_path / "cache").exists() else []
    assert cache_files == []


def test_malformed_sdk_response_falls_back(tmp_path, monkeypatch):
    class MalformedSDK(FakeGenerativeAI):
        def embed_content(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            return {"not_embedding": []}

    fake = MalformedSDK()
    embedder = _live_embedder(tmp_path, monkeypatch, fake)

    embedder.embed("malformed response")

    assert embedder.metadata["mode_actual"] == "dry-run-live-error"
    assert "did not contain an embedding" in embedder.metadata["fallback_reason"]


def test_invalid_dimensions_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        VertexGeckoEmbedder(dims=4, cache_dir=tmp_path / "cache")
    with pytest.raises(ValueError):
        VertexGeckoEmbedder(dims=EMBEDDING_DIMS_HARD + 1, cache_dir=tmp_path / "cache")


def test_embed_batch_matches_individual_calls_in_dry_run(tmp_path):
    embedder = VertexGeckoEmbedder(cache_dir=tmp_path / "cache")
    texts = ["alpha", "beta", "alpha"]

    batch = embedder.embed_batch(texts)

    assert batch[0] == embedder.embed("alpha")
    assert batch[1] == embedder.embed("beta")
    assert batch[2] == batch[0]


def test_bq_model_list_exposes_vertex_gecko_as_live_capable():
    rows = {row["name"]: row for row in describe_embedder_models(dims=64)}

    assert rows["vertex-gecko"]["kind"] == "VertexGeckoEmbedder"
    assert rows["vertex-gecko"]["dims"] == 64
    assert "dry-run by default" in str(rows["vertex-gecko"]["note"])
