# Foundry Ontology Schema — Sapphire

**Version:** 1.0  
**Date:** 2026-04-19  
**Source:** `lib/foundry/ingestion.py` transforms  

This document defines the Foundry ontology object types that Sapphire syncs into Palantir Foundry.  Each object type maps to a local data source, is transformed by `lib/foundry/ingestion.py`, and uploaded by `lib/foundry/sync.py` on a 15-minute delta-aware schedule.

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
| `tests/unit/test_foundry_readiness.py` | Readiness + schema audit tests |
| `tests/unit/test_foundry_sync.py` | Sync engine tests |
