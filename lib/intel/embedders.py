"""Deterministic and guarded live embedders for the vector retrieval layer.

Sapphire's :mod:`lib.intel.bq_vector_store` is paired with an embedder so that
upserts and queries can run end-to-end without depending on any external model
provider. This module provides:

* :class:`HashEmbedder` — a reproducible, locale-stable bag-of-tokens hash
  embedder that maps text into a unit-norm float vector. It is intended only
  as a placeholder so that the surrounding plumbing (BigQuery schema, query
  ranking, provenance envelopes) can be exercised in CI and on operator
  laptops without spending a dollar on Vertex/OpenAI/Anthropic.
* :class:`VertexGeckoEmbedder` — a guarded ``text-embedding-gecko@003``
  adapter. It defaults to the same deterministic local mock, and only attempts
  live Google embedding calls when the explicit live flag and operator secrets
  file are both present.
* :class:`EmbedderRegistry` — a tiny registry that lets callers ask for a
  named embedder (``mock-hash`` and ``vertex-gecko`` today; ``openai-ada-002``
  and ``anthropic-titan`` are advertised as future placeholders that will fail
  closed until a real implementation is wired in).

The dry-run embedding is **not** semantically meaningful. It is a stable
function of token co-occurrence within the input string. Two strings with
overlapping tokens will produce vectors with non-zero cosine similarity, which
is enough to verify that ``upsert → query → ranking`` works deterministically;
it is not enough to support real retrieval.

The module performs no I/O at import time. Vector dimensions and rules are
read from arguments only; the Vertex adapter reads ``~/.sapphire/secrets.env``
and imports ``google.generativeai`` only inside its constructor when live mode
has been explicitly requested.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

# Hard upper bound on emitted vector dimensions. Mirrors
# ``EMBEDDING_DIMS_HARD`` in :mod:`lib.intel.bq_vector_store` so neither side
# can drift independently.
EMBEDDING_DIMS_HARD = 1536
DEFAULT_EMBEDDING_DIMS = 768
MIN_EMBEDDING_DIMS = 8
VERTEX_GECKO_MODEL = "text-embedding-gecko@003"
VERTEX_GECKO_NAME = "vertex-gecko"
VERTEX_GECKO_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "vertex_embedder"
VERTEX_GECKO_SECRETS_FILE = Path.home() / ".sapphire" / "secrets.env"
MAX_EMBED_CALLS_PER_HOUR = 100
MAX_EMBED_TOKENS_PER_MONTH = 1_000_000

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


def _now_month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _load_secret_values(path: Path) -> dict[str, str]:
    """Read key/value pairs from ``secrets.env`` without exposing values."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            key, value = line.split("=", 1)
            value = value.strip().strip("'\"")
            if value:
                values[key.strip()] = value
    except OSError:
        return {}
    return values


@dataclass
class VertexGeckoEmbedder:
    """Guarded Vertex/Gemini ``text-embedding-gecko@003`` adapter.

    Dry-run is the default and never imports the Google SDK or reads secrets.
    Live calls require ``SAPPHIRE_VERTEX_EMBEDDER_LIVE=1`` plus a
    ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` entry in ``secrets.env``. Any
    missing gate, cap hit, SDK error, bad cache entry, or dimension mismatch
    returns the deterministic local mock vector and records the fallback in
    :attr:`metadata`.
    """

    name: str = VERTEX_GECKO_NAME
    dims: int = DEFAULT_EMBEDDING_DIMS
    model: str = VERTEX_GECKO_MODEL
    task_type: str = "retrieval_document"
    cache_dir: Path = VERTEX_GECKO_CACHE_DIR
    secrets_file: Path = VERTEX_GECKO_SECRETS_FILE
    env: Mapping[str, str] | None = None
    note: str = (
        "Vertex AI text-embedding-gecko@003; dry-run by default, live only with "
        "SAPPHIRE_VERTEX_EMBEDDER_LIVE=1 and a Gemini/Google API key in secrets.env."
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.dims < MIN_EMBEDDING_DIMS:
            raise ValueError(
                f"VertexGeckoEmbedder dims={self.dims} is below "
                f"MIN_EMBEDDING_DIMS={MIN_EMBEDDING_DIMS}"
            )
        if self.dims > EMBEDDING_DIMS_HARD:
            raise ValueError(
                f"VertexGeckoEmbedder dims={self.dims} exceeds "
                f"EMBEDDING_DIMS_HARD={EMBEDDING_DIMS_HARD}"
            )
        self.cache_dir = Path(self.cache_dir).expanduser()
        self.secrets_file = Path(self.secrets_file).expanduser()
        self._mock = HashEmbedder(name=f"{self.name}-dry-run", dims=self.dims)
        self._sdk: Any | None = None
        self._api_key: str | None = None
        env_map = self.env if self.env is not None else os.environ
        requested_live = (env_map.get("SAPPHIRE_VERTEX_EMBEDDER_LIVE", "") or "").strip() == "1"
        secrets = _load_secret_values(self.secrets_file) if requested_live else {}
        key_name = "GEMINI_API_KEY" if secrets.get("GEMINI_API_KEY") else "GOOGLE_API_KEY"
        self._api_key = secrets.get(key_name)
        mode_actual = "dry-run"
        reason = "live flag not set"
        if requested_live and not self._api_key:
            mode_actual = "dry-run-safety"
            reason = "live flag set but Gemini/Google API key is absent"
        elif requested_live:
            try:
                import google.generativeai as genai  # type: ignore[import-not-found]

                self._sdk = genai
                if hasattr(self._sdk, "configure"):
                    self._sdk.configure(api_key=self._api_key)
                mode_actual = "live"
                reason = "ok"
            except Exception as exc:  # noqa: BLE001 - fail closed on SDK setup
                self._sdk = None
                mode_actual = "dry-run-safety"
                reason = f"sdk unavailable: {type(exc).__name__}"

        self._base_metadata = {
            "mode_requested": "live" if requested_live else "dry-run",
            "mode_actual": mode_actual,
            "fallback_reason": reason,
            "model": self.model,
            "dims": self.dims,
            "cached": False,
            "api_key_present": bool(self._api_key),
            "api_key_source": key_name if self._api_key else "",
            "secrets_file_present": self.secrets_file.exists(),
            "max_embed_calls_per_hour": MAX_EMBED_CALLS_PER_HOUR,
            "max_embed_tokens_per_month": MAX_EMBED_TOKENS_PER_MONTH,
        }
        self.metadata.update(self._base_metadata)

    @property
    def counters_path(self) -> Path:
        return self.cache_dir / "counters.json"

    def _input_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_key(self, text: str) -> str:
        input_hash = self._input_hash(text)
        safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.model)
        return f"{safe_model}.d{self.dims}.{input_hash}"

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / f"{self._cache_key(text)}.json"

    def _load_cached(self, text: str) -> list[float] | None:
        path = self._cache_path(text)
        if not path.exists():
            return None
        data = _load_json_object(path)
        if (
            data.get("model") != self.model
            or data.get("dims") != self.dims
            or data.get("input_sha256") != self._input_hash(text)
        ):
            return None
        vector = data.get("embedding")
        if not isinstance(vector, list) or len(vector) != self.dims:
            return None
        try:
            return [float(v) for v in vector]
        except (TypeError, ValueError):
            return None

    def _save_cached(self, text: str, vector: list[float]) -> None:
        payload = {
            "model": self.model,
            "dims": self.dims,
            "input_sha256": self._input_hash(text),
            "embedding": vector,
            "cached_at": datetime.now(UTC).isoformat(),
        }
        try:
            _write_json_object(self._cache_path(text), payload)
        except OSError:
            # Cache write failures must not turn an otherwise successful live
            # embedding into an error path.
            pass

    def _load_counters(self) -> dict[str, Any]:
        data = _load_json_object(self.counters_path)
        calls = data.get("calls")
        month_tokens = data.get("month_tokens")
        return {
            "calls": list(calls) if isinstance(calls, list) else [],
            "month_tokens": int(month_tokens or 0),
            "month_key": str(data.get("month_key") or _now_month_key()),
        }

    def _prune_counters(self, counters: dict[str, Any]) -> dict[str, Any]:
        cutoff = time.time() - 3600
        counters["calls"] = [
            float(ts)
            for ts in counters.get("calls", [])
            if isinstance(ts, int | float) and float(ts) >= cutoff
        ]
        month_key = _now_month_key()
        if counters.get("month_key") != month_key:
            counters["month_key"] = month_key
            counters["month_tokens"] = 0
        return counters

    def _save_counters(self, counters: dict[str, Any]) -> None:
        try:
            _write_json_object(self.counters_path, counters)
        except OSError:
            pass

    def _estimated_tokens(self, text: str) -> int:
        normalized = normalize_text(text)
        if not normalized:
            return 0
        return max(1, math.ceil(len(normalized) / 4))

    def _check_caps(self, text: str) -> tuple[bool, str, dict[str, Any], int]:
        counters = self._prune_counters(self._load_counters())
        estimated_tokens = self._estimated_tokens(text)
        calls = counters.get("calls", [])
        if len(calls) >= MAX_EMBED_CALLS_PER_HOUR:
            return False, "dry-run-rate-limited", counters, estimated_tokens
        projected_tokens = int(counters.get("month_tokens") or 0) + estimated_tokens
        if projected_tokens > MAX_EMBED_TOKENS_PER_MONTH:
            return False, "dry-run-rate-limited", counters, estimated_tokens
        return True, "ok", counters, estimated_tokens

    def _record_live_call(self, counters: dict[str, Any], tokens: int) -> None:
        counters.setdefault("calls", []).append(time.time())
        counters["month_tokens"] = int(counters.get("month_tokens") or 0) + tokens
        counters["month_key"] = str(counters.get("month_key") or _now_month_key())
        self._save_counters(counters)

    def _fallback(
        self,
        text: str,
        *,
        mode_actual: str,
        reason: str,
        cached: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> list[float]:
        self.metadata.update(self._base_metadata)
        self.metadata.update(
            {
                "mode_actual": mode_actual,
                "fallback_reason": reason,
                "cached": cached,
                "input_sha256": self._input_hash(text),
            }
        )
        if extra:
            self.metadata.update(extra)
        return self._mock.embed(text)

    def _extract_vector(self, response: Any) -> list[float] | None:
        raw = None
        if isinstance(response, dict):
            raw = response.get("embedding")
            if isinstance(raw, dict):
                raw = raw.get("values") or raw.get("value")
        elif hasattr(response, "embedding"):
            raw = response.embedding
            if hasattr(raw, "values"):
                raw = raw.values
        if not isinstance(raw, list):
            return None
        try:
            return [float(v) for v in raw]
        except (TypeError, ValueError):
            return None

    def _live_embed(self, text: str) -> list[float] | None:
        if self._sdk is None:
            return None
        response = self._sdk.embed_content(
            model=self.model,
            content=text,
            task_type=self.task_type,
            output_dimensionality=self.dims,
        )
        return self._extract_vector(response)

    def embed(self, text: str) -> list[float]:
        text = str(text or "")
        if self._base_metadata.get("mode_actual") != "live":
            return self._fallback(
                text,
                mode_actual=str(self._base_metadata.get("mode_actual")),
                reason=str(self._base_metadata.get("fallback_reason")),
            )

        cached = self._load_cached(text)
        if cached is not None:
            self.metadata.update(self._base_metadata)
            self.metadata.update(
                {
                    "mode_actual": "live",
                    "cached": True,
                    "fallback_reason": "",
                    "input_sha256": self._input_hash(text),
                }
            )
            return cached

        allowed, cap_reason, counters, estimated_tokens = self._check_caps(text)
        cap_state = {
            "calls_last_hour": len(counters.get("calls", [])),
            "month_tokens": int(counters.get("month_tokens") or 0),
            "estimated_tokens": estimated_tokens,
        }
        if not allowed:
            return self._fallback(
                text,
                mode_actual=cap_reason,
                reason="embedder cap reached",
                extra=cap_state,
            )

        try:
            vector = self._live_embed(text)
        except Exception as exc:  # noqa: BLE001 - live failures fall back safely
            return self._fallback(
                text,
                mode_actual="dry-run-live-error",
                reason=type(exc).__name__,
                extra=cap_state,
            )

        if vector is None:
            return self._fallback(
                text,
                mode_actual="dry-run-live-error",
                reason="SDK response did not contain an embedding",
                extra=cap_state,
            )
        if len(vector) != self.dims:
            return self._fallback(
                text,
                mode_actual="dry-run-dim-mismatch",
                reason=f"embedding dims {len(vector)} != {self.dims}",
                extra=cap_state,
            )

        self._record_live_call(counters, estimated_tokens)
        self._save_cached(text, vector)
        cap_state["calls_last_hour"] += 1
        cap_state["month_tokens"] += estimated_tokens
        self.metadata.update(self._base_metadata)
        self.metadata.update(
            {
                "mode_actual": "live",
                "cached": False,
                "fallback_reason": "",
                "input_sha256": self._input_hash(text),
                **cap_state,
            }
        )
        return vector

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
        raise NotImplementedError(f"Embedder '{self.name}' is a placeholder. {self.note}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError(f"Embedder '{self.name}' is a placeholder. {self.note}")


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
    """Return a registry seeded with live-capable and placeholder embedders.

    ``vertex-gecko`` is live-capable but dry-run by default. Placeholder
    entries advertise future modes; calling ``embed`` on a placeholder raises
    ``NotImplementedError``.
    """
    registry = EmbedderRegistry()
    registry.register(HashEmbedder(dims=dims))
    registry.register(VertexGeckoEmbedder(dims=dims))
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
    "MAX_EMBED_CALLS_PER_HOUR",
    "MAX_EMBED_TOKENS_PER_MONTH",
    "MIN_EMBEDDING_DIMS",
    "VERTEX_GECKO_CACHE_DIR",
    "VERTEX_GECKO_MODEL",
    "VERTEX_GECKO_NAME",
    "VERTEX_GECKO_SECRETS_FILE",
    "VertexGeckoEmbedder",
    "default_registry",
    "normalize_text",
    "tokenize",
]
