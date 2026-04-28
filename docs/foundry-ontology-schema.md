# Foundry Ontology Schema — Sapphire

**Version:** 2.0 (Tranche-3 expansion)  
**Date:** 2026-04-28  
**Source:** `lib/foundry/ingestion.py` transforms  

This document defines the Foundry ontology object types that Sapphire syncs into Palantir Foundry.  Each object type maps to a local data source, is transformed by `lib/foundry/ingestion.py`, and uploaded by `lib/foundry/sync.py` on a 15-minute delta-aware schedule.

The 2.0 expansion adds five Tranche-2 surfaces (`IntelVectorRecord`, `TelegramIntelMessage`, `HyperliquidSignal`, `OODAPacket`, `ThreatIndicator`) and introduces per-type watermarks under `~/.cache/sapphire/foundry_sync/<type>.json`. The base directory is overridable via `SAPPHIRE_FOUNDRY_WATERMARK_DIR` for CI isolation. See `docs/products/foundry-ontology-0.2.0.md` for the buyer-facing summary.

---

## Object Types

### PaperTrade

Paper-traded signals from the autonomous trading pipeline.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `pipeline_id` | Unique signal/trade identifier |
| `symbol` | `string` | `symbol` | Trading pair (BTC, ETH, SOL, etc.) |
| `direction` | `string` | `direction` | `long` or `short` |
| `action` | `string` | `action` | `buy` or `sell` |
| `strategy` | `string` | `strategy` | Strategy name (e.g. PairTrading_v3, ema_cross) |
| `entry_price` | `double` | `price` | Entry price at signal generation |
| `take_profit` | `double` | `take_profit` | Target exit price |
| `stop_loss` | `double` | `stop_loss` | Stop-loss price |
| `rr_ratio` | `double` | `rr_ratio` | Risk/reward ratio |
| `confidence` | `double` | `confidence` | Model confidence [0–1] |
| `score` | `double` | `score` | Composite signal score |
| `position_usd` | `double` | `position_usd` | Position size in USD |
| `sizing_method` | `string` | `sizing_method` | `kelly`, `fixed`, etc. |
| `routing` | `string` | `routing` | `CONFIRMATION_REQUIRED`, `NOTIFY`, `AUTO` |
| `outcome` | `string` | `outcome` | `win`, `loss`, or null (open) |
| `pnl_usd` | `double` | `pnl_usd` | Realized P&L in USD |
| `close_price` | `double` | `close_price` | Exit price |
| `opened_at` | `timestamp` | `timestamp` | Signal generation time |
| `closed_at` | `timestamp` | `closed_at` | Trade close time |
| `source` | `string` | `source` | `webhook`, `test`, etc. |
| `regime` | `string` | `regime` | Market regime (TRANSITION, UNKNOWN, etc.) |
| `regime_score` | `double` | `regime_score` | Regime detection score |
| `fear_greed` | `integer` | `fear_greed` | Fear & Greed index value |
| `kronos_direction` | `string` | `kronos_direction` | Kronos model forecast direction |
| `funding_rate` | `double` | `funding_rate` | Perpetual funding rate |

**Data sources:** `data/signals/*.jsonl`, `data/paper_portfolio.json`

---

### Alert

Security findings, system incidents, and operational alerts.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `id` or derived | Alert identifier |
| `title` | `string` | `title` / `message` | Short alert title |
| `severity` | `string` | `priority` / `severity` | `low`, `medium`, `high`, `critical` |
| `category` | `string` | `type` | `alert`, `incident`, `security`, `error`, `circuit_breaker`, `security_report` |
| `source` | `string` | `service` / `source` | Originating service or system |
| `device` | `string` | `device` | Device name if applicable |
| `message` | `string` | `message` | Full alert text |
| `timestamp` | `timestamp` | `timestamp` | When the alert fired |
| `resolved` | `boolean` | `resolved` | Whether the alert has been resolved |
| `resolved_at` | `timestamp` | `resolved_at` | Resolution time |
| `tags` | `string[]` | `tags` | Categorization tags |

**Data sources:** `data/system_events.jsonl`, `data/security/*.json`

---

### ServiceHealth

Health and availability snapshots for Sapphire services and infrastructure.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | derived | Service + timestamp hash |
| `service` | `string` | `service` / `name` | Service identifier |
| `status` | `string` | `status` | `healthy`, `degraded`, `failed`, `unknown` |
| `latency_ms` | `double` | `latency_ms` | Response latency in milliseconds |
| `uptime_pct` | `double` | `uptime_pct` | Uptime percentage |
| `error_count` | `integer` | `error_count` | Recent error count |
| `last_check` | `timestamp` | `timestamp` | Last health check time |
| `host` | `string` | `host` / `endpoint` | Host address or endpoint URL |
| `tier` | `string` | `tier` | Infrastructure tier (T1–T4) |
| `notes` | `string` | `notes` | Additional context |

**Data sources:** `data/health/*.ndjson`, `data/device_topology.json`

---

### ThreatIntel

Cyber threat intelligence items from CISA, NVD, and internal threat feeds.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `canonical_id` / `id` | Threat item identifier |
| `title` | `string` | `title` | Threat advisory title |
| `description` | `string` | `description` | Full description or summary |
| `severity` | `string` | `severity` | `low`, `medium`, `high`, `critical` |
| `source` | `string` | `source` | Feed source (CISA, NVD, etc.) |
| `cve_ids` | `string[]` | `cve_ids` | Associated CVE identifiers |
| `affected_products` | `string[]` | `affected_products` | Affected software/products |
| `published_at` | `timestamp` | `published` | Publication date |
| `region` | `string` | `region` | Geographic region (`GLOBAL`, etc.) |
| `mitre_tactics` | `string[]` | `mitre_tactics` | MITRE ATT&CK tactic IDs |
| `ioc_count` | `integer` | derived | Number of indicators of compromise |
| `link` | `string` | `link` / `url` | Source URL |

**Data sources:** `data/intelligence/*/threats.json`, `data/threat_intel/*.md`

---

### DailyBrief

Generated daily intelligence briefs combining market, threat, and operational data.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `id` or derived | Brief identifier |
| `date` | `string` | directory name | Date (YYYY-MM-DD) |
| `title` | `string` | `title` | Brief title |
| `summary` | `string` | `summary` | Executive summary |
| `sections` | `object[]` | `sections` | Structured sections array |
| `market_outlook` | `string` | `market_outlook` | Market outlook assessment |
| `threat_level` | `string` | `threat_level` | `normal`, `elevated`, `high`, `critical` |
| `key_signals` | `string[]` | `key_signals` | Top signals of the day |
| `generated_at` | `timestamp` | `generated_at` | Generation time |

**Data sources:** `data/intelligence/*/daily_brief.json`, `data/intelligence/*/daily_brief.md`

---

### Region

Regional intelligence market and civic areas exported from the regional-intel workbench.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `object_id` | `string` (PK) | `object_id` | Stable regional ontology identifier |
| `id` | `string` | derived from `object_id` | Compatibility alias used by Sapphire audit tooling |
| `region_id` | `string` | `region_id` | Workbench region key, for example `austin_tx` |
| `name` | `string` | `name` | Human region label |
| `summary` | `string` | `summary` | Region context for operators and agents |
| `bbox` | `double[]` | `bbox` | Optional geographic bounds |
| `focus_keywords` | `string[]` | `focus_keywords` | Regional collection focus terms |
| `source_keys` | `string[]` | `source_keys` | Source identifiers used for this region |
| `snapshot_updated_at` | `timestamp` | `snapshot_updated_at` | Workbench snapshot timestamp |
| `notes` | `string[]` | `notes` | Operator notes |
| `provenance` | `object` | `provenance` | Public-source and ethics policy metadata |

**Data sources:** `data/foundry/regional-intel/Region.ndjson`

---

### IntelItem

Regional opportunities, permits, news, businesses, contacts, and organizations.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `object_id` | `string` (PK) | `object_id` | Stable regional-intel item identifier |
| `id` | `string` | derived from `object_id` | Compatibility alias used by Sapphire audit tooling |
| `item_id` | `string` | `item_id` | Workbench item key |
| `kind` | `string` | `kind` | `news`, `permit`, `business`, `contact`, or `organization` |
| `region_id` | `string` | `region_id` | Owning region key |
| `title` | `string` | `title` | Item title |
| `summary` | `string` | `summary` | Short operator summary |
| `score` | `double` | `score` | Workbench relevance or lead score |
| `source_name` | `string` | `source_name` | Public source label |
| `source_url` | `string` | `source_url` | Public source URL |
| `observed_at` | `timestamp` | `observed_at` | Source observation time when available |
| `snapshot_updated_at` | `timestamp` | `snapshot_updated_at` | Workbench snapshot timestamp |
| `attributes` | `object` | `attributes` | Kind-specific structured attributes |
| `notes` | `string[]` | `notes` | Item notes |
| `provenance` | `object` | `provenance` | Public-source and ethics policy metadata |

**Data sources:** `data/foundry/regional-intel/IntelItem.ndjson`

---

### IntelSourceHealth

Regional-intel source coverage and live-pull status.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `object_id` | `string` (PK) | `object_id` | Stable source identifier |
| `id` | `string` | derived from `object_id` | Compatibility alias used by Sapphire audit tooling |
| `source_key` | `string` | `source_key` | Regional workbench source key |
| `name` | `string` | `name` | Source display name |
| `category` | `string` | `category` | Source category |
| `region_ids` | `string[]` | `region_ids` | Regions covered by the source |
| `live_pull` | `boolean` | `live_pull` | Whether the source is collected live |
| `status` | `string` | `status` | `live`, `empty`, `manual`, or failure state |
| `item_count` | `integer` | `item_count` | Items emitted in the snapshot |
| `last_seen_at` | `timestamp` | `last_seen_at` | Last observed source activity |
| `snapshot_updated_at` | `timestamp` | `snapshot_updated_at` | Workbench snapshot timestamp |
| `notes` | `string[]` | `notes` | Source notes |
| `provenance` | `object` | `provenance` | Public-source and ethics policy metadata |

**Data sources:** `data/foundry/regional-intel/IntelSourceHealth.ndjson`

---

### IntelVectorRecord

Vector-store-backed intel records (sovereign-thesis, convergence-watchlist, threat-intel, regional-intel) lifted into Foundry as a queryable corpus surface.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `id` | Stable record identifier (mirror of `record_id`) |
| `record_id` | `string` | `id` | Original BQ-vector record id |
| `text` | `string` | `text` | Truncated intel text (≤2000 chars) |
| `text_length` | `integer` | derived | Original (un-truncated) text length |
| `source` | `string` | `source` | One of `KNOWN_SOURCES` (sovereign_thesis, convergence_watchlist, …) |
| `metadata` | `object` | `metadata` | JSON-safe dict; no secrets |
| `embedding_dims` | `integer` | derived | Length of the embedding vector |
| `embedding_hash` | `string` | derived | First 16 hex chars of sha256(`{:.8f}` joined embedding) |
| `created_at` | `timestamp` | `created_at` | ISO-8601 UTC |

**Indexed fields:** `id`, `source`, `created_at`. **Retention:** mirrors the BQ vector store mock (`MAX_INDEX_RECORDS_PER_RUN = 5000`); records older than 90 days may be pruned by the upstream store.

**Data sources:** `data/intel/bq_vector_mock.jsonl` (preferred), `~/.cache/sapphire/bq_vector_mock.jsonl` (fallback). Raw embedding vectors are intentionally NOT lifted into Foundry (`embedding_hash` lets you verify shape without exposing dimensionality details).

---

### TelegramIntelMessage

Provenance-stamped Telegram channel intel messages, written by `services/telegram_intel/sink.py` and lifted into Foundry as a discoverable intel feed.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | `canonical_id` | sha256-derived stable id (24 hex chars) |
| `canonical_id` | `string` | `canonical_id` | Same as `id` for join clarity |
| `schema_version` | `integer` | `schema_version` | Currently `1` |
| `channel_id` | `string` | `channel.id` | Telegram channel identifier |
| `channel_handle` | `string` | `channel.handle` / `channel.name` | Display handle |
| `channel_attribution` | `string` | `channel.attribution` | Public-source attribution string |
| `message_id` | `string` | `message.id` | Telegram message id |
| `text` | `string` | `message.text` | Sanitized message text (≤4000 chars) |
| `text_length` | `integer` | derived | Original message length |
| `truncated` | `boolean` | `message.truncated` | True if text was truncated by sanitizer |
| `published_at` | `timestamp` | `message.published_at` | Message publish time |
| `ingested_at` | `timestamp` | `ingested_at` | Sapphire sink ingestion time |
| `quality_decision` | `string` | `quality.decision` | `keep` / `drop` / `quarantine` |
| `quality_score` | `double` | `quality.score` | Quality filter confidence |
| `quality_reason` | `string` | `quality.reason` | Decision rationale |
| `classifier_label` | `string` | `classifier.label` | Topic/category label |
| `classifier_confidence` | `double` | `classifier.confidence` | Classifier confidence |
| `classifier_source` | `string` | `classifier.source` | Origin (`local-inference-proxy` etc.) |
| `classifier_model` | `string` | `classifier.model` | Model id (e.g. `hermes3:8b`) |

**Indexed fields:** `id`, `channel_id`, `published_at`, `quality_decision`, `classifier_label`. **Retention:** 180 days; daily JSONL files older than the retention window are pruned by the sink.

**Data sources:** `data/telegram_intel/<YYYY-MM-DD>/messages.jsonl` (preferred). The sink defaults to `services.telegram_intel.config.DEFAULT_DATA_DIR` which currently points at the repo `data/telegram_intel/`.

---

### HyperliquidSignal

Read-only public Hyperliquid market-structure signals from `services/hyperliquid/src/hyperliquid_bot/public_feed.py`. Strictly signal-only — no wallet keys, no live trading.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | derived (`hl:<event_id>` or hash fallback) | Stable signal id |
| `event_id` | `string` | `event_id` | Sapphire event-bus id (when present) |
| `topic` | `string` | `topic` | `hyperliquid.trade` / `hyperliquid.imbalance` / `hyperliquid.book.thin` |
| `schema_version` | `string` | `schema_version` | `hyperliquid.signal.v1` |
| `signal_type` | `string` | `signal_type` | `large_trade`, `top_of_book_imbalance`, `top_10_depth_drop` |
| `symbol` | `string` | `symbol` | Upper-cased coin symbol |
| `side` | `string` | `side` | Buy/sell (when applicable) |
| `dominant_side` | `string` | `dominant_side` | `bid`/`ask` for imbalance signals |
| `price` | `double` | `price` | Trade or quote price |
| `size` | `double` | `size` | Trade size |
| `notional_usd` | `double` | `notional_usd` | Trade notional |
| `threshold_usd` | `double` | `threshold_usd` | Configured large-trade threshold |
| `ratio` | `double` | `ratio` | Imbalance ratio (when applicable) |
| `threshold_ratio` | `double` | `threshold_ratio` | Threshold ratio for the signal |
| `sustained_seconds` | `double` | `sustained_seconds` | Duration the imbalance persisted |
| `current_depth_usd` | `double` | `current_depth_usd` | Current top-10 depth (USD) |
| `baseline_depth_usd` | `double` | `baseline_depth_usd` | Recent peak top-10 depth |
| `drop_ratio` | `double` | `drop_ratio` | Depth drop as a ratio |
| `threshold_drop_ratio` | `double` | `threshold_drop_ratio` | Threshold for the drop |
| `window_seconds` | `integer` | `window_seconds` | Sliding-window length |
| `exchange_time_ms` | `integer` | `exchange_time_ms` | Hyperliquid event time (ms) |
| `trade_id` | `string` | `trade_id` | Trade id (when present) |
| `observed_at` | `timestamp` | `observed_at` | When Sapphire saw the event |
| `baseline_observed_at` | `timestamp` | `baseline_observed_at` | When the baseline was captured |
| `published_at` | `timestamp` | `published_at` | Publisher emission time |
| `paper_only` | `boolean` | `paper_only` | Always `true` in current build |
| `live_trading_enabled` | `boolean` | `live_trading_enabled` | Always `false` in current build |
| `source` | `string` | `source` | `hyperliquid-public-feed` |

**Indexed fields:** `id`, `topic`, `symbol`, `published_at`, `signal_type`. **Retention:** 30 days (signals beyond that are de-prioritized; the local ledger rotates).

**Data sources:** `data/hyperliquid_signals.jsonl` (preferred), `~/.sapphire/hyperliquid_signals.jsonl` (fallback). Tests must override via `SAPPHIRE_HYPERLIQUID_SIGNAL_PATH` to keep CI isolated from a developer's home cache.

---

### OODAPacket

Bounded OODA (observe / orient / decide / act) packets emitted by the Gemini OODA tool (`plugins/claw-sapphire/tools/internal/gemini_ooda.py`). Live calls are gated by `SAPPHIRE_GEMINI_LIVE=1`; the cache files this transform reads are stamped with provenance.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | derived (`ooda:<request_hash>`) | Stable id |
| `request_hash` | `string` | `request_hash` / cache filename stem | sha256-derived; identifies the request payload |
| `observe` | `string` | `ooda.observe` | ≤1000 chars |
| `orient` | `string` | `ooda.orient` | ≤1000 chars |
| `decide` | `string` | `ooda.decide` | ≤1000 chars |
| `act` | `string[]` | `ooda.act` | 0–8 actions, each ≤500 chars |
| `model` | `string` | `provenance.model` | Gemini model id (e.g. `gemini-2.5-flash`) |
| `generator` | `string` | `provenance.generator` | Tool generator id |
| `mode` | `string` | `provenance.metadata.mode` | `live` / `dry-run` / `dry-run-safety` etc. |
| `issued_at` | `timestamp` | `provenance.generated_at` | Cache stamp time |
| `ttl_seconds` | `integer` | `provenance.ttl_seconds` | Cache TTL |
| `prompt_tokens` | `integer` | `tokens.prompt_tokens` | Live prompt tokens (live mode only) |
| `output_tokens` | `integer` | `tokens.output_tokens` | Live output tokens |
| `total_tokens` | `integer` | `tokens.total_tokens` | Sum |
| `cached` | `boolean` | `provenance.metadata.cache` | Whether the packet came from cache |

**Indexed fields:** `id`, `model`, `mode`, `issued_at`. **Retention:** 7 days (matches the tool's max cache TTL of 7×86400 seconds). Only stamped envelopes are lifted; counter files are excluded.

**Data sources:** `data/gemini_ooda/*.json` (preferred), `~/.cache/sapphire/gemini_ooda/*.json` (fallback). Override the directory with `SAPPHIRE_GEMINI_OODA_CACHE_DIR` for tests.

---

### ThreatIndicator

Granular IOC view: each indicator carries the same advisory context as `ThreatIntel` PLUS extracted indicator-of-compromise arrays (CVE ids, IPv4 addresses, suspicious domain-shaped tokens, hex hashes). Distinct from `ThreatIntel` by purpose: this surface is for joining IOCs against `Alert`, `ServiceHealth`, or `IntelVectorRecord` without re-parsing free text.

| Property | Type | Source Field | Description |
|----------|------|-------------|-------------|
| `id` | `string` (PK) | derived (`ti:<advisory_id>`) | Stable indicator id |
| `advisory_id` | `string` | `canonical_id` / `id` / derived | Underlying advisory identifier |
| `title` | `string` | `title` | Advisory title (≤500 chars) |
| `severity` | `string` | `severity` | `low`, `medium`, `high`, `critical` |
| `score` | `double` | `score` | CVSS or feed score (when present) |
| `exploited` | `boolean` | `exploited` | True if listed in CISA KEV |
| `source` | `string` | `source` | Feed source (CISA, NVD, internal) |
| `cve_ids` | `string[]` | extracted + author-supplied | Up to 32 |
| `ipv4_addresses` | `string[]` | extracted | Validated IPv4 strings, up to 32 |
| `domains` | `string[]` | extracted + author-supplied | Domain-shaped tokens, up to 32 |
| `hashes` | `string[]` | extracted + author-supplied | Hex digests (32–64 chars), lower-cased, up to 32 |
| `ioc_total` | `integer` | derived | Sum of the four IOC array lengths |
| `mitre_tactics` | `string[]` | `mitre_tactics` | MITRE ATT&CK tactic ids |
| `affected_products` | `string[]` | `affected_products` | Product list |
| `published_at` | `timestamp` | `published` | ISO-8601 |
| `region` | `string` | `region` | `GLOBAL` etc. |
| `link` | `string` | `link` / `url` | Source URL |

**Indexed fields:** `id`, `advisory_id`, `severity`, `exploited`, `published_at`, `region`. **Retention:** 365 days; KEV-flagged indicators retained indefinitely.

**Data sources:** `data/intelligence/*/threats.json`, `data/threat_intel/*.md`. Reads the same source files as `ThreatIntel` but emits one row per advisory with extracted IOC arrays.

---

## Regional Manifest v2 Readiness

The regional-intel workbench exports a runtime manifest at
`data/foundry/regional-intel/manifest.json`. Sapphire treats this file as local
runtime data and does not commit it, but the Foundry readiness audit validates
the v2 contract when the file is present.

Required manifest fields:

| Field | Purpose |
|-------|---------|
| `schema_version` | Must be `2` |
| `generated_at` | Manifest generation timestamp |
| `snapshot_updated_at` | Regional snapshot timestamp |
| `region` | Workbench region or region bundle identifier |
| `object_types` | `Region`, `IntelItem`, and `IntelSourceHealth` metadata with `filename`, `rows`, `file_sha256`, and `row_hashes` |
| `dropped_rows` | Paste-safe provenance counts: `total`, `by_reason`, and detail buckets |
| `source_health_summary` | Source coverage counts by status, category, and region |
| `policy` | Public-source and operator-use policy metadata |

The readiness audit reports dropped-row counts by reason, object type, kind, and
missing field only. It does not expose source payloads or row bodies.

## Ontology Links

These relationships connect object types in the Foundry ontology:

| Link | From | To | Cardinality | Description |
|------|------|----|-------------|-------------|
| `trade_alerts` | PaperTrade | Alert | 1:N | Alerts triggered by a trade |
| `service_alerts` | ServiceHealth | Alert | 1:N | Alerts for a service |
| `threat_alerts` | ThreatIntel | Alert | 1:N | Alerts from threat intel |
| `brief_threats` | DailyBrief | ThreatIntel | 1:N | Threats referenced in brief |
| `brief_trades` | DailyBrief | PaperTrade | 1:N | Trades referenced in brief |
| `service_threats` | ServiceHealth | ThreatIntel | N:M | Threats affecting services |
| `region_items` | Region | IntelItem | 1:N | Regional items observed inside a region |
| `region_sources` | Region | IntelSourceHealth | N:M | Public sources covering a region |
| `item_alerts` | IntelItem | Alert | 1:N | Operational alerts derived from regional intelligence |
| `vector_alerts` | IntelVectorRecord | Alert | N:M | Vector hits surfacing in alerts |
| `intel_threats` | TelegramIntelMessage | ThreatIndicator | N:M | Telegram intel mentioning IOCs |
| `signal_alerts` | HyperliquidSignal | Alert | 1:N | Alerts driven by Hyperliquid microstructure |
| `ooda_threats` | OODAPacket | ThreatIndicator | N:M | OODA packets reasoning over indicators |
| `indicator_alerts` | ThreatIndicator | Alert | 1:N | Alerts driven by IOC matches |
| `indicator_services` | ThreatIndicator | ServiceHealth | N:M | Services impacted by an indicator |

---

## Sync Behavior

The sync engine (`lib/foundry/sync.py`) runs on a 15-minute schedule with these characteristics:

- **Delta detection:** Compares file mtime + SHA-256 content hash (first 1MB) against saved state in `data/foundry_sync_state.json`
- **Selective sync:** Only transforms and uploads object types whose source files changed
- **Force mode:** `--force` flag syncs all types regardless of changes
- **Dry-run mode:** `--dry-run` transforms data but skips Foundry upload
- **History:** Append-only log at `data/foundry_sync_history.jsonl`
- **Alerting:** Telegram notification on sync failure (via `lib.telegram` or direct API)
- **Dashboard:** `/api/foundry/sync-status` endpoint exposes sync state to the intel page

Regional intelligence objects are staged by the sibling workbench and then read
by Sapphire's normal Foundry sync. From `~/Code/regional-intel-workbench`, run:

```bash
python3 -m app.cli intel-foundry-export --output-dir ~/Code/Sapphire/data/foundry/regional-intel --json
```

Use `--refresh` only when the operator explicitly wants to refresh public
sources before export; the default reads the latest stored local snapshot.

### Local Schema + Read-Back Audit

`lib/foundry/readiness.py` exposes `build_foundry_schema_audit()` and includes the
same paste-safe payload under `/api/foundry/readiness` as `schema_audit`.

The audit runs each local transform, checks emitted objects against the required
fields above, and reads back `data/foundry_sync_history.jsonl` for sync-history
shape only. It returns object counts, missing-field counts, source-reference
counts, transform error classes, and sync-history counters. It does not return
raw object rows, request bodies, Foundry credentials, Telegram values, or raw
sync error strings.

### Runtime Foundry Target

`lib/foundry/client.py` defaults to the historical Foundry API path:

- Ontology API name: `ontology`
- Upsert action API name: `sapphire-upsert`

If the Foundry partner renames the ontology or action, set these without code changes:

- `PALANTIR_FOUNDRY_ONTOLOGY` or `FOUNDRY_ONTOLOGY`
- `PALANTIR_FOUNDRY_UPSERT_ACTION` or `FOUNDRY_UPSERT_ACTION`
- `~/.config/sapphire-secrets/foundry_ontology`
- `~/.config/sapphire-secrets/foundry_upsert_action`

The sync preflights the configured ontology/action once per run. If the target is missing, it records
`last_status=not_configured` instead of logging one upload 404 per object type. Use
`FoundryClient.list_ontologies()` and `FoundryClient.list_action_types()` to inspect available API names
once the service credential has permission.

---

## Foundry Actions (Planned — Phase 2)

Per the strategy doc, these Actions will be implemented after the ontology layer stabilizes:

| Action | Target Type | Submission Criteria |
|--------|-------------|---------------------|
| `AcknowledgeAlert` | Alert | Requires `resolved=false` |
| `EscalateAlert` | Alert | Requires severity ≥ medium |
| `PauseService` | ServiceHealth | Requires elevated role |
| `PromotePredictionRule` | PaperTrade | Win rate ≥ 60% on ≥ 10 trades |
| `MarkThreatReviewed` | ThreatIntel | Requires review notes |
| `ApproveMitigation` | Alert | Requires linked ServiceHealth |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/foundry/readiness` | GET | Repo-grounded Foundry config check |
| `/api/foundry/sync-status` | GET | Current sync state + recent history |

---

## Files

| Path | Description |
|------|-------------|
| `lib/foundry/__init__.py` | Package init |
| `lib/foundry/readiness.py` | Repo artifact + config inspection, local schema audit, sanitized sync-history read-back |
| `lib/foundry/client.py` | Foundry REST API client (auth, datasets, ontology) |
| `lib/foundry/ingestion.py` | Local data → Foundry object transforms |
| `lib/foundry/sync.py` | Delta-aware sync engine + daemon |
| `data/foundry/regional-intel/*.ndjson` | Ignored staging area for regional workbench Foundry exports |
| `data/foundry_sync_state.json` | Persisted file-change state |
| `data/foundry_sync_history.jsonl` | Append-only sync log |
| `tests/unit/test_foundry_client.py` | Client unit tests |
| `tests/unit/test_foundry_ingestion.py` | Ingestion transform tests |
| `tests/unit/test_foundry_ingestion_extensions.py` | Tranche-3 ontology v0.2.0 transform tests |
| `tests/unit/test_foundry_readiness.py` | Readiness + schema audit tests |
| `tests/unit/test_foundry_sync.py` | Sync engine tests |
| `tests/unit/test_foundry_sync_extensions.py` | Tranche-3 sync watermark + new-type tests |
