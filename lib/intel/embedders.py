"""Deterministic local embedders for the BigQuery vector retrieval layer.

Sapphire's :mod:`lib.intel.bq_vector_store` is paired with an embedder so that
upserts and queries can run end-to-end without depending on any external model
provider. This module provides:

* :class:`HashEmbedder` — a reproducible, locale-stable bag-of-tokens hash
  embedder that maps text into a unit-norm float vector. It is intended only
  as a placeholder so that the surrounding plumbing (BigQuery schema, query
  ranking, provenance envelopes) can be exercised in CI and on operator
  laptops without spending a dollar on Vertex/OpenAI/Anthropic.
* :class:`EmbedderRegistry` — a tiny registry that lets callers ask for a
  named embedder (``mock-hash`` today; ``vertex-gecko``, ``openai-ada-002``,
  ``anthropic-titan`` are advertised as future placeholders that will fail
  closed until a real implementation is wired in).

The mock embedding is **not** semantically meaningful. It is a stable function
of token co-occurrence within the input string. Two strings with overlapping
tokens will produce vectors with non-zero cosine similarity, which is enough
to verify that ``upsert → query → ranking`` works deterministically; it is
not enough to support real retrieval. Swap-in of a real embedder is tracked as
an explicit follow-up in :doc:`/products/bq-vector-retrieval-0.1.0`.

The module performs no I/O at import time. Vector dimensions and rules are
read from arguments only.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

# Hard upper bound on emitted vector dimensions. Mirrors
# ``EMBEDDING_DIMS_HARD`` in :mod:`lib.intel.bq_vector_store` so neither side
# can drift independently.
EMBEDDING_DIMS_HARD = 1536
DEFAULT_EMBEDDING_DIMS = 768
MIN_EMBEDDING_DIMS = 8

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class EmbedderProtocol(Protocol):
    """Protocol every Sapphire embedder must satisfy."""

    name: str
    dims: int

    def embed(self, text: str) -> list[float]:
        """Return a unit-norm vector of ``self.dims`` floats for ``text``."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return a list of unit-norm vectors, one per input text."""
        ...


def normalize_text(text: str) -> str:
    """Return a locale-stable lowercased, unicode-normalized form of ``text``.

    Two strings differing only in unicode normalization or surrounding
    whitespace embed identically. This keeps the mock embedder portable
    across platforms with different default locales.
    """
    if not isinstance(text, str):
        text = str(text or "")
    nfc = unicodedata.normalize("NFKC", text)
    return nfc.strip().lower()


def tokenize(text: str) -> list[str]:
    """Split ``text`` into lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall(normalize_text(text))


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm <= 0.0:
        return list(vector)
    return [v / norm for v in vector]


@dataclass
class HashEmbedder:
    """Deterministic hash-based mock embedder.

    Each token is hashed to ``dims`` slots; the slot value is incremented by
    a stable per-token sign (+1 / -1) derived from a second hash. The full
    vector is then L2-normalized so cosine similarity is well-defined.

    This is a placeholder. It is good enough for unit tests, ranking
    determinism, and CI, but it is not a real embedding — see the runbook
    for swap-in steps.
    """

    name: str = "mock-hash"
    dims: int = DEFAULT_EMBEDDING_DIMS
    _salt: str = "sapphire-bq-mock-v1"
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dims < MIN_EMBEDDING_DIMS:
            raise ValueError(
                f"HashEmbedder dims={self.dims} is below MIN_EMBEDDING_DIMS={MIN_EMBEDDING_DIMS}"
            )
        if self.dims > EMBEDDING_DIMS_HARD:
            raise ValueError(
                f"HashEmbedder dims={self.dims} exceeds EMBEDDING_DIMS_HARD={EMBEDDING_DIMS_HARD}"
            )

    # -- hashing helpers --------------------------------------------------

    def _slot(self, token: str) -> int:
        digest = hashlib.sha256(f"{self._salt}|slot|{token}".encode()).digest()
        # First 8 bytes → 64-bit unsigned int → mod dims.
        slot = int.from_bytes(digest[:8], "big", signed=False)
        return slot % self.dims

    def _sign(self, token: str) -> float:
        digest = hashlib.sha256(f"{self._salt}|sign|{token}".encode()).digest()
        # First byte parity → +1 / -1.
        return 1.0 if (digest[0] & 1) == 0 else -1.0

    # -- public API -------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        vector = [0.0] * self.dims
        if not tokens:
            # Empty / whitespace-only input → zero vector. Cosine of two zero
            # vectors is undefined, so the store treats those hits as score 0.
            return vector
        for token in tokens:
            slot = self._slot(token)
            sign = self._sign(token)
            vector[slot] += sign
        return _l2_normalize(vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


@dataclass
class _PlaceholderEmbedder:
    """Stub for a future real embedder.

    Every method raises :class:`NotImplementedError` so the system fails
    closed if a caller asks for a real embedder before it is wired up.
    """

    name: str
    dims: int = DEFAULT_EMBEDDING_DIMS
    note: str = "placeholder — not implemented"

    def embed(self, text: str) -> list[float]:  # pragma: no cover - guard path
        raise NotImplementedError(
            f"Embedder '{self.name}' is a placeholder. {self.note}"
        )

    def embed_batch(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError(
            f"Embedder '{self.name}' is a placeholder. {self.note}"
        )


class EmbedderRegistry:
    """Tiny in-process registry of embedders by name."""

    def __init__(self) -> None:
        self._entries: dict[str, EmbedderProtocol] = {}

    def register(self, embedder: EmbedderProtocol) -> None:
        self._entries[embedder.name] = embedder

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def get(self, name: str) -> EmbedderProtocol:
        if name not in self._entries:
            available = ", ".join(self.names()) or "(none)"
            raise KeyError(f"Embedder '{name}' is not registered. Available: {available}")
        return self._entries[name]

    def describe(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for name in self.names():
            entry = self._entries[name]
            rows.append(
                {
                    "name": name,
                    "dims": getattr(entry, "dims", None),
                    "kind": type(entry).__name__,
                    "note": getattr(entry, "note", ""),
                }
            )
        return rows


def default_registry(*, dims: int = DEFAULT_EMBEDDING_DIMS) -> EmbedderRegistry:
    """Return a registry seeded with the mock embedder and known placeholders.

    Placeholder entries advertise *future* embedder modes so the
    ``intel_search models`` action can list them; calling ``embed`` on a
    placeholder raises ``NotImplementedError``.
    """
    registry = EmbedderRegistry()
    registry.register(HashEmbedder(dims=dims))
    registry.register(
        _PlaceholderEmbedder(
            name="vertex-gecko",
            dims=dims,
            note=(
                "Vertex AI text-embedding-gecko@003 — not wired. "
                "Will require GOOGLE_APPLICATION_CREDENTIALS + SAPPHIRE_BQ_LIVE=1."
            ),
        )
    )
    registry.register(
        _PlaceholderEmbedder(
            name="openai-ada-002",
            dims=dims,
            note=(
                "OpenAI text-embedding-ada-002 — not wired. "
                "Will require OPENAI_API_KEY and an explicit live flag."
            ),
        )
    )
    registry.register(
        _PlaceholderEmbedder(
            name="anthropic-titan",
            dims=dims,
            note=(
                "Anthropic embedding (placeholder name) — not wired. "
                "Will require ANTHROPIC_API_KEY and an explicit live flag."
            ),
        )
    )
    return registry


__all__ = [
    "DEFAULT_EMBEDDING_DIMS",
    "EMBEDDING_DIMS_HARD",
    "EmbedderProtocol",
    "EmbedderRegistry",
    "HashEmbedder",
    "MIN_EMBEDDING_DIMS",
    "default_registry",
    "normalize_text",
    "tokenize",
]
