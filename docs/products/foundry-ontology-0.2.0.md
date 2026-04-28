# Sapphire Foundry Ontology 0.2.0

Sapphire Foundry Ontology 0.2.0 expands the ontology surface that
`lib/foundry/sync.py` continuously lifts into Palantir Foundry from the
eight 0.1.0 types (PaperTrade, Alert, ServiceHealth, ThreatIntel,
DailyBrief, Region, IntelItem, IntelSourceHealth) to thirteen. The five
new types — `IntelVectorRecord`, `TelegramIntelMessage`,
`HyperliquidSignal`, `OODAPacket`, and `ThreatIndicator` — make every
Tranche-2 intelligence surface machine-discoverable inside Foundry without
operator handholding.

The 0.1.0 contract is unchanged. The new types ride the same versioned
envelope, the same idempotency ledger, and the same fail-closed live-mode
gate (`SAPPHIRE_FOUNDRY_LIVE=1`).

## Why a Buyer Cares

Tranche-2 shipped a portfolio of high-signal intel surfaces — vector
retrieval over Sapphire's intel corpus, a Telegram channel intel reader,
a public Hyperliquid microstructure feed, a bounded Gemini OODA lane, and
a granular threat-indicator extractor. Each was independently valuable
but their composition lived **only in the operator's head**.

Sapphire Foundry Ontology 0.2.0 lifts that composition onto disk:

* A Foundry analyst can query "which `TelegramIntelMessage` rows mention
  a `ThreatIndicator` whose `cve_ids` overlap with a `ServiceHealth.host`
  we run?" without re-parsing free text.
* An acquirer can trace a Hyperliquid microstructure signal
  (`HyperliquidSignal`) to the OODA packet (`OODAPacket`) it provoked
  and the alert (`Alert`) that fired downstream.
* A diligence reviewer sees one consistent envelope, one idempotency
  ledger, one provenance contract — across all 13 types.

## What's New (versus 0.1.0)

### 1. `IntelVectorRecord`

* **Source:** `lib/intel/bq_vector_store.py` mock JSONL (or its production
  BigQuery descendant once `SAPPHIRE_BQ_LIVE=1`).
* **Foundry primary key:** the original `VectorRecord.id`.
* **Lifted:** `text` (truncated to 2000 chars), `text_length` (full
  length), `source`, `metadata`, `embedding_dims`, `embedding_hash` (sha256
  of formatted floats — first 16 hex chars), `created_at`.
* **NOT lifted:** the raw embedding vector. High-dimensional vectors
  belong in BigQuery; the hash is enough for shape audits.

### 2. `TelegramIntelMessage`

* **Source:** `services/telegram_intel/sink.py` daily JSONL files.
* **Foundry primary key:** the sink's `canonical_id` (sha256-derived,
  guaranteed dedupe across re-uploads).
* **Lifted:** sanitized message text (≤4000 chars), full text length,
  channel attribution, quality decision (with score + reason), and the
  classifier label/confidence/source/model.

### 3. `HyperliquidSignal`

* **Source:** `~/.sapphire/hyperliquid_signals.jsonl` ledger written by
  the public WebSocket subscriber.
* **Foundry primary key:** `hl:<event_id>` when a Sapphire event-bus id
  is present; otherwise a deterministic hash over topic + symbol +
  signal_type + published_at.
* **Lifted:** topic, signal_type, symbol (upper-cased), price/size/notional
  + thresholds, imbalance ratio + sustained_seconds, depth + drop_ratio +
  window_seconds, exchange time + Sapphire observed/published times.
* **Posture:** `paper_only=true` and `live_trading_enabled=false` ride
  with every row so the acquirer sees that this signal feed never
  authorizes a wallet.

### 4. `OODAPacket`

* **Source:** `~/.cache/sapphire/gemini_ooda/*.json` cache files (each is
  a stamped Sapphire provenance envelope around a 4-field OODA dict).
* **Foundry primary key:** `ooda:<request_hash>` where the hash is the
  cache filename stem (sha256 of the request payload, first 32 hex chars).
* **Lifted:** the four OODA fields (each capped to 1000 chars), the act
  array (capped to 8 items × 500 chars), model id, generator id, mode,
  issued_at, ttl_seconds, cached flag, and per-call token counts when
  the original call was live.

### 5. `ThreatIndicator`

* **Source:** the same data as `ThreatIntel` (`data/intelligence/*/threats.json`,
  `data/threat_intel/*.md`), but reshaped per advisory.
* **Foundry primary key:** `ti:<advisory_id>` so the indicator joins
  cleanly to the underlying `ThreatIntel` row.
* **Lifted:** advisory metadata (title, severity, score, exploited, source)
  PLUS extracted IOC arrays — `cve_ids`, `ipv4_addresses`, `domains`,
  `hashes` (lower-cased) — each capped at 32 entries. `ioc_total` is the
  sum of array lengths so an analyst can rank by IOC density without
  reading row bodies.

## Watermarks (new in 0.2.0)

`lib/foundry/sync.py` now persists a per-type watermark JSON under
`~/.cache/sapphire/foundry_sync/<type>.json` after every sync cycle. Each
watermark records:

```json
{
  "object_type": "IntelVectorRecord",
  "last_synced_at": "2026-04-28T05:13:00+00:00",
  "object_count": 42,
  "changed_files": ["data/intel/bq_vector_mock.jsonl"],
  "force": false
}
```

Watermarks are written for **every** transform that ran cleanly — even
when the transform produced zero objects — so a dashboard or audit can
distinguish "we didn't look" from "we looked, the source was empty".

The directory is overridable via `SAPPHIRE_FOUNDRY_WATERMARK_DIR` (used
by the unit tests, where it points at `tmp_path/_watermark/`).

## Backward compatibility

* All eight 0.1.0 types continue to sync with no behavioral change. The
  existing `tests/unit/test_foundry_ingestion.py` (35 cases) and
  `tests/unit/test_foundry_sync.py` (44 cases) continue to pass with the
  new logic in place.
* The idempotency ledger absorbs the new types under the same uniqueness
  rules — re-uploads of the same payload produce the same envelope hash
  and are skipped on the same path.
* The Foundry client live-mode gate is unchanged. Live calls continue to
  require `SAPPHIRE_FOUNDRY_LIVE=1` and a configured ontology + upsert
  action.
* Existing watermarks (none — this surface is new) won't conflict with
  any operator state. The first sync after rollout populates them.

## Tests

* `tests/unit/test_foundry_ingestion_extensions.py` — 59 cases (≥5 per
  new type plus IOC-extraction + watermark-progression + transient-error
  tolerance + backward-compat smoke).
* `tests/unit/test_foundry_sync_extensions.py` — 18 cases (delta detection
  on the new patterns, watermark helper roundtrip, run_sync writes the
  expected watermarks, transform crashes don't leave stale watermarks,
  dry-run never contacts the live Foundry client).
* All new tests mock the Foundry client and override every external-cache
  path via env vars so CI never touches a developer's `~/.cache` or
  `~/.sapphire`.

## Operator-owed actions

* No operator action is required for the dry-run path — it activates as
  soon as this lane lands.
* To opt into live ingestion of the new types, the operator must (a)
  finish provisioning the Foundry ontology + upsert action and (b) set
  `SAPPHIRE_FOUNDRY_LIVE=1` (already documented in 0.1.0). The new types
  flow through the same fail-closed gate.

## Files

* `lib/foundry/ingestion.py` — five new `transform_*` callables + five
  matching `to_<TypeName>(record: dict)` single-record helpers.
* `lib/foundry/sync.py` — new pattern groups, watermark helpers
  (`watermark_path`, `load_watermark`, `write_watermark`), and watermark
  emission inside `run_sync`.
* `docs/foundry-ontology-schema.md` — bumped to 2.0 with five new
  schemas + ontology links.
* `docs/products/foundry-ontology-0.2.0.md` — this document.
* `tests/unit/test_foundry_ingestion_extensions.py`,
  `tests/unit/test_foundry_sync_extensions.py` — new test suites.
