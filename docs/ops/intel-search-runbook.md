# Intel Search Runbook

This runbook covers day-to-day operation of `intel_search` — the Sapphire
plugin tool that wraps `lib.intel.bq_vector_store` and serves semantic
queries over the Sapphire intel corpus (sovereign-thesis assets,
convergence-watchlist entries, threat-intel summaries).

The product doc is `docs/products/bq-vector-retrieval-0.1.0.md`. Read that
first if you need the design rationale or the schema.

## What `intel_search` Does

`intel_search` is a stdin-JSON tool. It exposes four actions:

| Action  | What it does                                                              |
|---------|---------------------------------------------------------------------------|
| `search`| Semantic similarity query over the indexed corpus; returns top-k hits     |
| `index` | Index a corpus snapshot from local JSON snapshots; never touches network  |
| `stats` | Reports record counts per source, last index timestamp, mode, rate state  |
| `models`| Lists embedder modes (mock, guarded Vertex, placeholder names)             |

Mock-by-default. The library mirrors the same caps the tool advertises
(`MAX_QUERY_K=50`, `MAX_INDEX_RECORDS_PER_RUN=5_000`,
`MAX_LIVE_INDEX_PER_HOUR=2`, `EMBEDDING_DIMS_HARD=1536`). Violating any of
those is reported in the response, never silently swallowed.

## Setup

Nothing has to be installed beyond the standard Sapphire dev environment.
The mock backend has no external dependencies, persists to
`~/.cache/sapphire/bq_vector_mock.jsonl`, and recovers cleanly if that
file is missing or corrupt.

Smoke-test the tool from the repo root:

```bash
echo '{"action":"models"}' | python3 plugins/claw-sapphire/tools/intel_search.py
echo '{"action":"stats"}'  | python3 plugins/claw-sapphire/tools/intel_search.py
```

The first should list `mock-hash`, the guarded `vertex-gecko` embedder, and
the remaining placeholder names (`openai-ada-002`, `anthropic-titan`). The
second should report `mode: mock` and `total_records: 0` until you index
something.

## `search` — Day-To-Day Query

```bash
echo '{
  "action": "search",
  "query": "renewable infrastructure ai-power tailwind",
  "k": 5,
  "filters": {"source": "sovereign_thesis"}
}' | python3 plugins/claw-sapphire/tools/intel_search.py
```

Notes:

* `query` is required (or pass an explicit `embedding` of `dims` floats).
* `k` is hard-capped at 50; larger values are silently clipped and the
  response reports the actual `k` used.
* `filters` accepts a `source` key plus arbitrary metadata equality
  filters (e.g. `{"asset": "BTC"}`). Non-matching records are skipped
  before scoring.
* Every hit carries a `provenance` envelope; verify it with
  `lib.core.provenance.verify` before treating the hit as authoritative.

## `index` — Refresh The Corpus

The tool always reads from snapshots under `data/intelligence/`,
`data/threat_intel/`, or any directory you pass in `snapshot_dir`. It
never makes network calls during indexing.

```bash
echo '{
  "action": "index",
  "snapshot_dir": "data/intelligence",
  "sources": ["sovereign_thesis", "convergence_watchlist"]
}' | python3 plugins/claw-sapphire/tools/intel_search.py
```

Snapshot conventions:

* `*sovereign_thesis*.json` → `sovereign_thesis` records. The loader
  accepts either the full thesis dict (with `assets` / `rows` /
  `thesis_assets`) or a flat list of asset dicts.
* `*convergence_watchlist*.json` → `convergence_watchlist` records.
  Accepts a `watchlist`/`items`/`entries` key or a flat list.
* `data/threat_intel/*.md` → one `threat_intel` record per file (text
  capped at 4 KB).
* `*daily_brief*.json` → one `daily_brief` record per file.

Per-run cap: 5000 records. The response includes `inserted`, `updated`,
`skipped`, and a list of the first 20 errors (dim mismatch, empty text,
duplicate IDs in the same batch, etc).

## `stats` — Health & Posture

```bash
echo '{"action":"stats"}' | python3 plugins/claw-sapphire/tools/intel_search.py
```

Returns:

```json
{
  "mode": "mock",
  "total_records": 24,
  "by_source": {"convergence_watchlist": 1, "sovereign_thesis": 22, "threat_intel": 1},
  "table_fqn": "sapphire-data-lake.intel.vectors",
  "dims": 768,
  "last_index_at": "2026-04-27T14:31:08+00:00",
  "live_calls_last_hour": 0,
  "max_live_index_per_hour": 2,
  "live_env": false,
  "max_query_k": 50,
  "known_sources": ["sovereign_thesis", "convergence_watchlist", ...]
}
```

`mode` is `mock` (default), `live-intent` (the caller asked for live but
the gate hasn't been re-verified yet), or one of the `live-*` markers
returned from a refused or rate-limited live call.

## `models` — Embedder Inventory

```bash
echo '{"action":"models"}' | python3 plugins/claw-sapphire/tools/intel_search.py
```

The default is `mock-hash`. `vertex-gecko` is implemented by
`lib.intel.embedders.VertexGeckoEmbedder` and stays dry-run unless every
Vertex live gate passes. `openai-ada-002` and `anthropic-titan` remain
placeholder names only.

**Dry-run embeddings are placeholders.** The mock embedder is enough to test
ingestion, storage, ranking, and the provenance contract end-to-end, but it is
not a real semantic embedding. To run the Vertex-backed embedder manually,
instantiate `VertexGeckoEmbedder` with `SAPPHIRE_VERTEX_EMBEDDER_LIVE=1` and a
`GEMINI_API_KEY` or `GOOGLE_API_KEY` entry in `~/.sapphire/secrets.env`.

## Mock vs Live

### Mock (default)

* Triggered by `live: false` (or by omitting the field).
* Backed by `~/.cache/sapphire/bq_vector_mock.jsonl`.
* No external services contacted.
* CI uses this path exclusively.

### Vertex Gecko Embedder

`VertexGeckoEmbedder` wraps `text-embedding-gecko@003` with a no-spend default:

1. If `SAPPHIRE_VERTEX_EMBEDDER_LIVE` is not `1`, it returns the deterministic
   local mock and reports `mode_actual: dry-run`.
2. If the live flag is set but `~/.sapphire/secrets.env` lacks
   `GEMINI_API_KEY` or `GOOGLE_API_KEY`, it returns the mock and reports
   `mode_actual: dry-run-safety`.
3. Live calls are capped at `MAX_EMBED_CALLS_PER_HOUR = 100` and
   `MAX_EMBED_TOKENS_PER_MONTH = 1_000_000`.
4. Counters and live-result cache files live under
   `~/.cache/sapphire/vertex_embedder/`.
5. Cache keys include the model name, requested dimension, and
   `sha256(input)`, so repeat calls short-circuit before any SDK call.
6. Any SDK error or returned-vector dimension mismatch falls back to the local
   mock; mismatches report `mode_actual: dry-run-dim-mismatch`.

Tests mock `google.generativeai.embed_content`; CI never calls Vertex.

### Live

A live BigQuery operation is only attempted when **all three** of these
are true at call time:

1. `SAPPHIRE_BQ_LIVE=1`
2. `GOOGLE_APPLICATION_CREDENTIALS` resolves to a readable file
3. `SAPPHIRE_BQ_PROJECT` matches the constructor's `project` argument

The live path is wired. A passing gate will contact BigQuery: `index`
creates the destination table idempotently, loads a staging table, and
MERGEs rows by stable `id`; `search` executes parameterized
`VECTOR_SEARCH`. Live `index` attempts are rate-limited at 2/hour
regardless; the counter is persisted under
`~/.cache/sapphire/bq_vector_live_rate.json` and pruned to a 1-hour
window on every check.

For no-spend local verification, leave `live` unset/false and use the mock
backend. Only run the live command when the operator has approved a bounded
BigQuery write/search:

```bash
SAPPHIRE_BQ_LIVE=1 \
GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/sapphire-secrets/gcp-readonly.json \
SAPPHIRE_BQ_PROJECT=sapphire-data-lake \
echo '{"action":"index","live":true,"snapshot_dir":"data/intelligence"}' \
  | python3 plugins/claw-sapphire/tools/intel_search.py
```

If any gate fails, the response includes a clear `gate.reason` and no
BigQuery client is constructed.

## Troubleshooting

| Symptom                                              | Cause                                            | Fix                                                        |
|------------------------------------------------------|--------------------------------------------------|------------------------------------------------------------|
| `error: query is required`                           | Missing `query` and `embedding` in `search`      | Provide one of the two                                     |
| `embedding dims X != store dims Y`                   | Embedding length mismatch                        | Match the store's `dims` (768 default; max 1536)           |
| `unknown source 'X' (allowed: ...) ; record kept`    | Custom source string, accepted but logged        | Use one of `KNOWN_SOURCES` to silence                      |
| `truncating batch from N to 5000`                    | Indexing batch too large                         | Split the snapshot or accept the cap                       |
| `live gate refused: SAPPHIRE_BQ_LIVE != 1`           | Live mode requested without the env flag         | Set the three live env vars or stay in mock mode           |
| `live index rate limit hit: 2/2 in the last hour`    | Two live indexes already happened this hour      | Wait, or audit the caller — 2/hour is intentional          |
| `mode_actual: dry-run-safety` on `vertex-gecko`      | Live flag set without a key in `secrets.env`     | Add the key to `~/.sapphire/secrets.env` or stay dry-run   |
| `mode_actual: dry-run-dim-mismatch` on `vertex-gecko`| Provider returned a vector with the wrong length | Keep mock fallback; inspect SDK/model settings             |
| Mock backend returns 0 records after restart        | JSONL file missing or in a different `mock_path` | Confirm `~/.cache/sapphire/bq_vector_mock.jsonl` exists    |

## Cap State

| Cap                          | Source                                       |
|------------------------------|----------------------------------------------|
| `MAX_QUERY_K = 50`           | `lib.intel.bq_vector_store.MAX_QUERY_K`      |
| `MAX_INDEX_RECORDS_PER_RUN = 5000` | `lib.intel.bq_vector_store.MAX_INDEX_RECORDS_PER_RUN` |
| `MAX_LIVE_INDEX_PER_HOUR = 2` | `lib.intel.bq_vector_store.MAX_LIVE_INDEX_PER_HOUR`  |
| `EMBEDDING_DIMS_HARD = 1536` | `lib.intel.embedders.EMBEDDING_DIMS_HARD`    |
| `MAX_EMBED_CALLS_PER_HOUR = 100` | `lib.intel.embedders.MAX_EMBED_CALLS_PER_HOUR` |
| `MAX_EMBED_TOKENS_PER_MONTH = 1_000_000` | `lib.intel.embedders.MAX_EMBED_TOKENS_PER_MONTH` |

The library, the tool, this runbook, and the product doc all reference
these constants directly so they cannot drift.

## Soak Posture

* The default `intel_search` tool path remains mock-only unless an operator
  explicitly wires `VertexGeckoEmbedder` into a local experiment.
* The Vertex embedder's safe soak is repeat-call cache validation: run one
  mocked or live-gated call, rerun the same input, confirm the cache hit, then
  inspect counters under `~/.cache/sapphire/vertex_embedder/`.
* Live BigQuery writes/searches are available but remain opt-in behind the
  three live gates.
* Before any recurring production use, run one operator-approved index from
  a representative snapshot, watch the per-hour counter, confirm the table
  schema in BigQuery, and verify that `search` from a fresh shell hits the
  live table.
* Telegram-style alerting is not wired today; a later tranche can add a
  failure alert path that mirrors the Foundry sync pattern in
  `lib/foundry/sync.py`.
* For this build, the verification gate is the local pytest run plus
  `python3 scripts/validate_tool_registry.py`. Both must pass before
  promotion.

## Verification Checklist

```bash
ruff check .
python3 -m pytest tests/unit/test_bq_vector_store.py \
                  tests/unit/test_bq_vector_store_live.py \
                  tests/unit/test_intel_embedders.py \
                  plugins/claw-sapphire/tests/test_intel_search.py \
                  -x --tb=short
python3 -m pytest tests/unit/ plugins/claw-sapphire/tests/ -x --tb=short -q
python3 scripts/validate_tool_registry.py
python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

All four MUST pass. The readiness sweep MUST report `0 fail`.

## Telegram & Trading Critical Path

`intel_search` is **not** on the trading critical path. It does not place
orders, sign transactions, send Telegram messages, write to
`data/system_events.jsonl`, or modify any service state. It is a
read-only retrieval tool plus a corpus indexer that writes only to
`~/.cache/sapphire/`. Promoting it does not change the kill-switch
posture or the live-capital surface.
