#!/usr/bin/env python3
"""Sapphire Intel Search — semantic retrieval over the Sapphire intel corpus.

Wraps :mod:`lib.intel.bq_vector_store` with a stdin-JSON contract so it can
be invoked from scheduled tasks, hermes skills, dashboards, or directly by
an operator. Exposes four read-only-ish actions:

* ``search`` — semantic similarity query over the indexed corpus; returns
  top-k hits with provenance envelopes.
* ``index``  — index a corpus snapshot from local ``data/intelligence/``
  and ``world_knowledge/`` JSON files. Always reads from snapshots; never
  fetches anything from the network.
* ``stats``  — record counts per source, last index timestamp, mock-vs-live
  posture, and the live-rate counter.
* ``models`` — list embedder modes (``mock-hash`` is real; the others are
  placeholder names advertised so callers can plan a real-embedder swap).

Safety
------
* Mock-by-default. The live BigQuery path is only attempted when the
  caller passes ``"live": true`` *and* the environment satisfies all
  three gates (``SAPPHIRE_BQ_LIVE=1``, ``GOOGLE_APPLICATION_CREDENTIALS``,
  ``SAPPHIRE_BQ_PROJECT``).
* All hits carry a ``lib.core.provenance`` envelope.
* Hard caps mirror the library: ``k`` ≤ 50, batch ≤ 5000, live indexing
  ≤ 2/hour. The tool refuses to violate those.
* Never reads ``~/.sapphire/secrets.env``. Live credentials must be on the
  process environment when ``live=true`` is requested.

Input contract
--------------
::

    {
      "action": "search" | "index" | "stats" | "models",
      // search:
      "query": "string",
      "k": 5,
      "filters": {"source": "sovereign_thesis", "asset": "BTC"},
      // index:
      "snapshot_dir": "data/intelligence/",
      "sources": ["sovereign_thesis", "convergence_watchlist"],
      // shared:
      "project": "sapphire-data-lake",
      "dataset": "intel",
      "table": "vectors",
      "embedder": "mock-hash",
      "dims": 768,
      "live": false
    }
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_lib_module(qualname: str, relpath: str):
    """Load a Sapphire ``lib.*`` module from the repo even if shadowed.

    Plugin tests put ``plugins/claw-sapphire/lib/`` (a regular package)
    on ``sys.path``, which according to PEP 420 wins over the repo-root
    ``lib/`` namespace-package portion. Loading by file path and
    registering the result in ``sys.modules[qualname]`` lets the rest of
    the code use the canonical ``from lib.X import Y`` form regardless
    of the shadow.
    """
    import importlib.util

    if qualname in sys.modules:
        existing = sys.modules[qualname]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing
    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    return module


# Register ``lib`` as the repo namespace ourselves so that any subsequent
# ``from lib.X import Y`` lookup resolves through ``sys.modules`` rather
# than the path-finder (which is the level where the plugin-local ``lib``
# package wins). The ordering matters: load the leaf modules' transitive
# dependencies first.
import types

if "lib" not in sys.modules or (REPO_ROOT / "lib") not in [
    Path(p) for p in (getattr(sys.modules.get("lib"), "__path__", None) or [])
]:
    sys.modules["lib"] = types.ModuleType("lib")
    sys.modules["lib"].__path__ = [str(REPO_ROOT / "lib")]  # type: ignore[attr-defined]
if "lib.core" not in sys.modules:
    sys.modules["lib.core"] = types.ModuleType("lib.core")
    sys.modules["lib.core"].__path__ = [str(REPO_ROOT / "lib" / "core")]  # type: ignore[attr-defined]
if "lib.intel" not in sys.modules:
    sys.modules["lib.intel"] = types.ModuleType("lib.intel")
    sys.modules["lib.intel"].__path__ = [str(REPO_ROOT / "lib" / "intel")]  # type: ignore[attr-defined]

_load_repo_lib_module("lib.core.provenance", "lib/core/provenance.py")
_EMB = _load_repo_lib_module("lib.intel.embedders", "lib/intel/embedders.py")
_BQ = _load_repo_lib_module("lib.intel.bq_vector_store", "lib/intel/bq_vector_store.py")

# Wire the loaded modules onto their parent so attribute-lookup-style
# access (e.g. monkeypatch's "lib.intel.bq_vector_store.X" form) keeps
# working in tests.
sys.modules["lib"].core = sys.modules["lib.core"]  # type: ignore[attr-defined]
sys.modules["lib"].intel = sys.modules["lib.intel"]  # type: ignore[attr-defined]
sys.modules["lib.core"].provenance = sys.modules["lib.core.provenance"]  # type: ignore[attr-defined]
sys.modules["lib.intel"].embedders = _EMB  # type: ignore[attr-defined]
sys.modules["lib.intel"].bq_vector_store = _BQ  # type: ignore[attr-defined]

BQVectorStore = _BQ.BQVectorStore
VectorRecord = _BQ.VectorRecord
DEFAULT_DIMS = _BQ.DEFAULT_DIMS
KNOWN_SOURCES = _BQ.KNOWN_SOURCES
MAX_INDEX_RECORDS_PER_RUN = _BQ.MAX_INDEX_RECORDS_PER_RUN
MAX_QUERY_K = _BQ.MAX_QUERY_K
evaluate_live_gate = _BQ.evaluate_live_gate
describe_embedder_models = _BQ.describe_embedder_models
EMBEDDING_DIMS_HARD = _EMB.EMBEDDING_DIMS_HARD
HashEmbedder = _EMB.HashEmbedder
default_registry = _EMB.default_registry


DEFAULT_PROJECT = "sapphire-data-lake"
DEFAULT_DATASET = "intel"
DEFAULT_TABLE = "vectors"
DEFAULT_SNAPSHOT_DIRS = (
    "data/intelligence",
    "data/threat_intel",
    "world_knowledge/research",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_int(value: Any, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _build_store(payload: dict[str, Any]) -> BQVectorStore:
    project = str(payload.get("project") or DEFAULT_PROJECT)
    dataset = str(payload.get("dataset") or DEFAULT_DATASET)
    table = str(payload.get("table") or DEFAULT_TABLE)
    dims = _coerce_int(payload.get("dims"), DEFAULT_DIMS, lo=8, hi=EMBEDDING_DIMS_HARD)
    embedder_name = str(payload.get("embedder") or "mock-hash")
    registry = default_registry(dims=dims)
    if embedder_name == "mock-hash":
        embedder = registry.get("mock-hash")
    else:
        try:
            embedder = registry.get(embedder_name)
        except KeyError:
            embedder = HashEmbedder(dims=dims)
        else:
            # Future providers are placeholders that fail closed if used.
            # Keep the Vertex entry lazy so model selection never spends a
            # warmup call before the real query/index operation.
            if type(embedder).__name__ == "_PlaceholderEmbedder":
                embedder = HashEmbedder(dims=dims)
    if getattr(embedder, "dims", dims) != dims:
        embedder = HashEmbedder(dims=dims)
    mock = not bool(payload.get("live"))
    return BQVectorStore(
        project=project,
        dataset=dataset,
        table=table,
        mock=mock,
        embedder=embedder,
        dims=dims,
    )


# ---------------------------------------------------------------------------
# Snapshot loaders
# ---------------------------------------------------------------------------


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _coerce_text(blob: Any, *, max_chars: int = 4000) -> str:
    if isinstance(blob, str):
        text = blob
    elif isinstance(blob, dict):
        # Build a stable, dehydrated text representation. We deliberately
        # cap length so a giant dict can't dominate the corpus.
        parts: list[str] = []
        for key in sorted(blob.keys()):
            value = blob[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                parts.append(f"{key}: {value}")
            elif isinstance(value, (list, tuple)):
                snippet = ", ".join(str(v) for v in value[:8])
                parts.append(f"{key}: [{snippet}]")
            elif isinstance(value, dict):
                nested = ", ".join(f"{k}={value[k]}" for k in list(value)[:8])
                parts.append(f"{key}: {{{nested}}}")
        text = " | ".join(parts)
    else:
        text = str(blob)
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def _records_from_sovereign_thesis(payload: Any, *, root: Path) -> list[dict[str, Any]]:
    """Pull rows out of a sovereign-thesis-style JSON snapshot.

    The snapshot can either be the full thesis dict (with ``assets`` /
    ``lens_cells`` blocks) or a flat list of asset dicts. We accept both
    and also fall back to a single dehydrated record so that *something*
    is always indexable.
    """
    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        for key in ("assets", "rows", "thesis_assets", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(v for v in value if isinstance(v, dict))
        if not candidates:
            # Treat the whole dict as one record.
            candidates.append(payload)
    elif isinstance(payload, list):
        candidates.extend(v for v in payload if isinstance(v, dict))

    for entry in candidates:
        symbol = str(entry.get("symbol") or entry.get("ticker") or entry.get("id") or "")
        name = str(entry.get("name") or entry.get("label") or symbol or "thesis-asset")
        thesis = entry.get("thesis") or entry.get("description") or entry.get("note") or ""
        text_parts = [name]
        if symbol:
            text_parts.append(f"({symbol})")
        if thesis:
            text_parts.append(str(thesis))
        themes = entry.get("themes") or entry.get("thesis_tags")
        if isinstance(themes, (list, tuple)):
            text_parts.append("themes: " + ", ".join(str(t) for t in themes[:8]))
        text = " — ".join(p for p in text_parts if p).strip()
        if not text:
            text = _coerce_text(entry)
        rec_id = (
            f"sovereign_thesis:{symbol}"
            if symbol
            else f"sovereign_thesis:{abs(hash(text)) % (10**12)}"
        )
        rows.append(
            {
                "id": rec_id,
                "text": text,
                "source": "sovereign_thesis",
                "metadata": {
                    "symbol": symbol,
                    "name": name,
                    "asset_class": entry.get("asset_class"),
                    "themes": list(themes) if isinstance(themes, (list, tuple)) else None,
                },
            }
        )
    return rows


def _records_from_convergence_watchlist(payload: Any, *, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        items = payload.get("watchlist") or payload.get("items") or payload.get("entries")
    else:
        items = payload
    if not isinstance(items, list):
        return rows
    for entry in items:
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("symbol") or entry.get("ticker") or entry.get("name") or "")
        name = str(entry.get("name") or symbol)
        thesis = entry.get("thesis") or entry.get("rationale") or entry.get("note") or ""
        text = " — ".join(p for p in [name, str(thesis)] if p).strip() or _coerce_text(entry)
        rec_id = (
            f"convergence_watchlist:{symbol}"
            if symbol
            else f"convergence_watchlist:{abs(hash(text)) % (10**12)}"
        )
        rows.append(
            {
                "id": rec_id,
                "text": text,
                "source": "convergence_watchlist",
                "metadata": {
                    "symbol": symbol,
                    "name": name,
                    "asset_class": entry.get("asset_class"),
                    "tier": entry.get("tier") or entry.get("watch_level"),
                },
            }
        )
    return rows


def _records_from_threat_intel(path: Path) -> list[dict[str, Any]]:
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    text = text.strip()
    if not text:
        return []
    if len(text) > 4000:
        text = text[:3999] + "…"
    return [
        {
            "id": f"threat_intel:{path.stem}",
            "text": text,
            "source": "threat_intel",
            "metadata": {
                "path": str(path),
                "filename": path.name,
            },
        }
    ]


def _walk_snapshot(
    root: Path,
    snapshot_dir: Path,
    *,
    sources: list[str],
) -> list[dict[str, Any]]:
    """Walk a snapshot tree and emit candidate records.

    Heuristics:
      * ``*sovereign_thesis*.json`` → sovereign_thesis records
      * ``*convergence_watchlist*.json`` → convergence_watchlist records
      * ``data/threat_intel/*.md`` → threat_intel summaries (one per file)
      * ``*daily_brief*.json`` → daily_brief records
    """
    rows: list[dict[str, Any]] = []
    if not snapshot_dir.exists():
        return rows

    want_sovereign = "sovereign_thesis" in sources
    want_convergence = "convergence_watchlist" in sources
    want_threat = "threat_intel" in sources
    want_daily = "daily_brief" in sources

    for path in sorted(snapshot_dir.rglob("*.json")):
        if not path.is_file():
            continue
        name = path.name.lower()
        payload = _read_json_file(path)
        if payload is None:
            continue
        if want_sovereign and "sovereign_thesis" in name:
            rows.extend(_records_from_sovereign_thesis(payload, root=root))
        if want_convergence and (
            "convergence_watchlist" in name or "convergence-watchlist" in name
        ):
            rows.extend(_records_from_convergence_watchlist(payload, root=root))
        if want_daily and "daily_brief" in name:
            rows.append(
                {
                    "id": f"daily_brief:{path.stem}",
                    "text": _coerce_text(payload),
                    "source": "daily_brief",
                    "metadata": {"path": str(path), "filename": path.name},
                }
            )

    if want_threat:
        for path in sorted(snapshot_dir.rglob("*.md")):
            if not path.is_file():
                continue
            if "threat_intel" not in str(path).lower():
                continue
            rows.extend(_records_from_threat_intel(path))

    return rows


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if not query and not payload.get("embedding"):
        return {"error": "query is required (or pass an explicit embedding)"}
    k = _coerce_int(payload.get("k"), 5, lo=1, hi=MAX_QUERY_K)
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else None
    store = _build_store(payload)
    embedding = payload.get("embedding")
    hits = store.query(
        text=query if not embedding else None,
        embedding=embedding if isinstance(embedding, list) else None,
        k=k,
        filters=filters,
    )
    return {
        "ok": True,
        "query": query,
        "k": k,
        "filters": filters or {},
        "table": store.table_fqn,
        "mode": "mock" if store.mock else "live-intent",
        "hits": [hit.to_dict() for hit in hits],
    }


def _resolve_snapshot_dirs(payload: dict[str, Any], *, root: Path) -> list[Path]:
    raw = payload.get("snapshot_dir") or payload.get("snapshot_dirs")
    if raw:
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            return []
        return [(root / p).resolve() if not Path(p).is_absolute() else Path(p) for p in raw]
    return [root / d for d in DEFAULT_SNAPSHOT_DIRS]


def index(payload: dict[str, Any]) -> dict[str, Any]:
    sources_raw = payload.get("sources")
    if isinstance(sources_raw, list):
        sources = [str(s) for s in sources_raw]
    else:
        sources = list(KNOWN_SOURCES)
    root = Path(payload.get("repo_root") or REPO_ROOT)
    snapshot_dirs = _resolve_snapshot_dirs(payload, root=root)
    store = _build_store(payload)

    # Live indexing requires the gate. Mock indexing skips it entirely.
    live_requested = bool(payload.get("live"))
    gate_state: dict[str, Any] | None = None
    if live_requested:
        gate = evaluate_live_gate(project=store.project)
        gate_state = {"allowed": gate.allowed, "reason": gate.reason}
        if not gate.allowed:
            return {
                "ok": False,
                "error": "live gate refused",
                "gate": gate_state,
                "table": store.table_fqn,
            }

    raw_rows: list[dict[str, Any]] = []
    visited: list[str] = []
    for snapshot_dir in snapshot_dirs:
        visited.append(str(snapshot_dir))
        raw_rows.extend(_walk_snapshot(root, snapshot_dir, sources=sources))
        if len(raw_rows) >= MAX_INDEX_RECORDS_PER_RUN:
            break

    if not raw_rows:
        return {
            "ok": True,
            "indexed": 0,
            "scanned_dirs": visited,
            "sources": sources,
            "table": store.table_fqn,
            "mode": "mock" if store.mock else "live-intent",
            "note": "no snapshot files matched; nothing indexed",
        }

    records: list[VectorRecord] = []
    for row in raw_rows[:MAX_INDEX_RECORDS_PER_RUN]:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        embedding = store.embedder.embed(text)
        records.append(
            VectorRecord(
                id=str(row.get("id") or ""),
                text=text,
                embedding=embedding,
                source=str(row.get("source") or "ad_hoc"),
                metadata=dict(row.get("metadata") or {}),
                created_at=datetime.now(UTC),
            )
        )

    result = store.upsert(records)
    return {
        "ok": result.ok,
        "indexed": result.inserted + result.updated,
        "inserted": result.inserted,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors[:20],
        "scanned_dirs": visited,
        "sources": sources,
        "table": store.table_fqn,
        "mode": result.mode,
        "gate": gate_state,
    }


def stats(payload: dict[str, Any]) -> dict[str, Any]:
    store = _build_store(payload)
    summary = store.stats().to_dict()
    summary["timestamp"] = _now_iso()
    summary["live_env"] = (os.environ.get("SAPPHIRE_BQ_LIVE", "") or "") == "1"
    summary["max_query_k"] = MAX_QUERY_K
    summary["max_index_records_per_run"] = MAX_INDEX_RECORDS_PER_RUN
    summary["known_sources"] = list(KNOWN_SOURCES)
    return summary


def models(payload: dict[str, Any]) -> dict[str, Any]:
    dims = _coerce_int(payload.get("dims"), DEFAULT_DIMS, lo=8, hi=EMBEDDING_DIMS_HARD)
    return {
        "default": "mock-hash",
        "dims": dims,
        "embedders": describe_embedder_models(dims=dims),
        "swap_in_note": (
            "vertex-gecko is live-capable but dry-run by default. Other real "
            "providers remain placeholders; see docs/ops/intel-search-runbook.md."
        ),
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload.get("action") or "search").strip().lower()
    if action == "search":
        return search(payload)
    if action == "index":
        return index(payload)
    if action == "stats":
        return stats(payload)
    if action == "models":
        return models(payload)
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["search", "index", "stats", "models"],
    }


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
