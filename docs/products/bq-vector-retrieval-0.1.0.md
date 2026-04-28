# Sapphire BQ Vector Retrieval 0.1.0

Sapphire BQ Vector Retrieval 0.1.0 turns Sapphire's intel — sovereign-thesis
assets, convergence-watchlist entries, and threat-intel summaries — into a
queryable vector substrate with a clear path from local CI mock to a live
BigQuery vector table. It is the first checkpoint on Sapphire's "lift our
intel into a queryable substrate" workstream.

The public library is `lib.intel.bq_vector_store`. The operator-facing entry
point is the `intel_search` plugin tool (stdin-JSON contract).

## Why A Buyer Cares

Pre-acquisition diligence almost always asks: *can your intel be queried by
something other than the people who wrote it?* Sapphire's previous answer
was "we have JSONL files and dashboards." That answer is now: *Sapphire has
a versioned, provenance-stamped, fixed-schema vector corpus that can be
indexed locally for CI, lifted into BigQuery for production retrieval, and
joined against the Sapphire ontology in Foundry without rewriting Sapphire
code.* The library is small (~600 LOC) and contract-first: a single
`BQVectorStore` class, a single `intel_search` tool, four actions, four
caps, three live-mode gates.

## Schema

Records share one shape across mock and live backends:

| Field        | Type           | Notes                                                |
|--------------|----------------|------------------------------------------------------|
| `id`         | string         | Stable per record; derived from text+source if unset |
| `text`       | string         | Required, non-empty, locale-stable                   |
| `embedding`  | list[float]    | Length must equal store `dims` (default 768)         |
| `source`     | string         | One of `KNOWN_SOURCES` (or any string with warning)  |
| `metadata`   | dict           | JSON-safe, no secrets; small                         |
| `created_at` | datetime (UTC) | Filled if missing                                    |

`KNOWN_SOURCES` is `sovereign_thesis`, `convergence_watchlist`,
`threat_intel`, `daily_brief`, `regional_intel`, `ad_hoc`. Unknown sources
are accepted but flagged in `UpsertResult.errors`, so corpus drift is
observable rather than silent.

Every `QueryHit` returned from `BQVectorStore.query` is stamped with a
`lib.core.provenance` envelope (schema v1) bound to the underlying record.
Consumers can verify the envelope with `lib.core.provenance.verify` to be
sure the record was produced by Sapphire and has not drifted since indexing.

## Modes

### Mock (default)

* In-memory dict keyed by `id`; cosine similarity computed in pure Python.
* Persisted to `~/.cache/sapphire/bq_vector_mock.jsonl` with a leading
  `__meta__` row. Corrupt lines are skipped on read; the file is rewritten
  in full on each upsert (trade-off: simple over fast, fine for ≤ 5K rows).
* Deterministic. Pinned by `lib.intel.embedders.HashEmbedder` and tested
  for reproducibility across calls, instances, and unicode normalization.
* Used by the entire test suite. CI never touches BigQuery.

### Live (gated)

A live BigQuery write/query is only attempted when **all three** of the
following are true at call time:

1. `SAPPHIRE_BQ_LIVE=1`
2. `GOOGLE_APPLICATION_CREDENTIALS` resolves to a readable credentials file
3. `SAPPHIRE_BQ_PROJECT` matches the constructor's `project` argument

The gate is fail-closed and re-checked on every call. The current 0.1.0
build *registers* live attempts (for rate accounting) but returns a clear
`live-not-implemented` marker — the actual BigQuery I/O is the next
tranche. The mock backend is intentionally good enough that the rest of
Sapphire (dashboard, hermes skills, scheduled tasks) can integrate against
the same API today.

## Embeddings

`lib.intel.embedders` ships:

* `HashEmbedder` — deterministic, locale-stable, unit-norm hash embedder.
  Tokens are SHA-256-hashed twice (once for slot, once for sign), summed,
  and L2-normalized. Strings differing only in unicode normalization or
  whitespace embed identically.
* Placeholder entries for `vertex-gecko`, `openai-ada-002`, and
  `anthropic-titan`. They are advertised by the `models` action so callers
  can plan, but `embed()` raises `NotImplementedError` — the system fails
  closed if a caller asks for a real embedder before it is wired up.

**Embeddings are placeholder.** The hash embedder is *enough* to verify
that ingestion, storage, ranking, and the provenance contract all work
end-to-end, but it is not a real semantic embedding. Swapping in a real
embedder is an explicit follow-up; the runbook documents the steps.

## Caps

All caps live in `lib.intel.bq_vector_store` and are mirrored in the tool
and the runbook so none of the three can drift independently:

| Cap                          | Value | Rationale                                             |
|------------------------------|-------|-------------------------------------------------------|
| `MAX_QUERY_K`                | 50    | Bounded fan-out for any single search                 |
| `MAX_INDEX_RECORDS_PER_RUN`  | 5000  | One run can't blow up the corpus                      |
| `MAX_LIVE_INDEX_PER_HOUR`    | 2     | Live writes are rate-limited regardless of caller     |
| `EMBEDDING_DIMS_HARD`        | 1536  | Largest dim we'll accept; matches OpenAI ada-002 size |

Violations are reported in the tool's `UpsertResult.errors` and the
relevant action result, never silently swallowed.

## Plugin Tool: `intel_search`

Lives at `plugins/claw-sapphire/tools/internal/intel_search.py` (with the
canonical 30-line shim at `plugins/claw-sapphire/tools/intel_search.py`).
Stdin-JSON contract; outputs JSON to stdout. Four actions:

* `search` — semantic search over the indexed corpus; returns top-k hits
  with provenance envelopes.
* `index`  — index a corpus snapshot. Always reads from local snapshots
  under `data/intelligence/`, `data/threat_intel/`, or any path the caller
  supplies in `snapshot_dir`. Never touches the network.
* `stats`  — record counts per source, last index timestamp, mock-vs-live
  posture, live-rate counter.
* `models` — list embedder modes (mock + placeholders) and the configured
  default.

Examples:

```bash
echo '{"action":"models"}' | python3 plugins/claw-sapphire/tools/intel_search.py
echo '{"action":"index","snapshot_dir":"data/intelligence"}' \
  | python3 plugins/claw-sapphire/tools/intel_search.py
echo '{"action":"search","query":"hard money bitcoin","k":5}' \
  | python3 plugins/claw-sapphire/tools/intel_search.py
echo '{"action":"stats"}' | python3 plugins/claw-sapphire/tools/intel_search.py
```

## Provenance Story

Every retrieved hit ships with a stamped envelope. The envelope's
`generator` is always `lib.intel.bq_vector_store`; `model` is the embedder
name (`mock-hash` today); `metadata.table` is the BigQuery FQN
(`<project>.<dataset>.<table>`) so the envelope identifies *where* the
record came from regardless of which backend served it. A diligence
consumer can:

1. Receive a `QueryHit`.
2. Verify `verify(hit.provenance)` returns `True`.
3. Check `metadata.mode` to see whether the hit came from the mock backend
   or the live BigQuery table.

`BQVectorStore.stamp_corpus_snapshot()` produces a stamped, hashed,
record-count-only snapshot suitable for diligence packets — it does not
expose any record text.

## What Lives Where

| File                                                             | Purpose                            |
|------------------------------------------------------------------|------------------------------------|
| `lib/intel/bq_vector_store.py`                                   | Store + dataclasses + caps + gate  |
| `lib/intel/embedders.py`                                         | Mock embedder + registry           |
| `plugins/claw-sapphire/tools/internal/intel_search.py`           | Plugin tool (real impl)            |
| `plugins/claw-sapphire/tools/intel_search.py`                    | 30-line compat shim                |
| `tests/unit/test_bq_vector_store.py`                             | 32-case lib tests                  |
| `tests/unit/test_intel_embedders.py`                             | 11-case embedder tests             |
| `plugins/claw-sapphire/tests/test_intel_search.py`               | 10-case plugin tool tests          |
| `docs/ops/intel-search-runbook.md`                               | Operator runbook                   |
| `infra/tool-registry.yaml`                                       | Registry entry under "Intel" block |

## Roadmap

* **0.2.0** — wire the live BigQuery upsert + `VECTOR_SEARCH` query;
  introduce a Vertex `text-embedding-gecko@003` embedder behind the same
  gate. Expand `MAX_LIVE_INDEX_PER_HOUR` only after a soak window.
* **0.3.0** — surface `intel_search` results in the dashboard intel page
  and through hermes skills.
* **0.4.0** — Foundry sync: write a `IntelVectorRecord` ontology object
  with `provenance` from this corpus, joined against existing
  `Region`/`IntelItem` ontology objects.
