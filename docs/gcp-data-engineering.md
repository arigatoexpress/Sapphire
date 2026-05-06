# Sapphire OS — GCP Data Engineering

Last updated: 2026-05-06

End-to-end reference for the `tho-ai-agent` project's data plane: what lives in GCP, how data flows from the Mac into BigQuery, and how to recover when something breaks.

Cost-aware Vertex AI augmentation is tracked in
[`docs/ops/gcp-vertex-ai-complement-plan.md`](ops/gcp-vertex-ai-complement-plan.md).
Use `python3 scripts/ops/gcp_ai_inventory.py --format markdown` for read-only
AI/data-plane inventory before any batch prediction, embedding, tuning, or
training work.

## 1. Resource inventory

### Project, location, identities

| Item | Value |
|------|-------|
| Project ID           | `tho-ai-agent` |
| Project number       | `691674245427` |
| Region (default)     | `us-central1` |
| BQ location          | `us` (multi-region) |
| Data service account | `sapphire-data-ops@tho-ai-agent.iam.gserviceaccount.com` |
| DTS service agent    | `service-691674245427@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com` |
| GCF service agent    | `service-691674245427@gcf-admin-robot.iam.gserviceaccount.com` |

### GCS

| Bucket | Purpose |
|--------|---------|
| `gs://sapphire-data-lake/raw/<source>/YYYY-MM-DD/*.ndjson` | Landing zone for Mac-generated NDJSON, watched by `sapphire-gcs-to-bq` |
| `gs://sapphire-archives/` (planned) | Weekly Parquet exports of BQ tables |

### BigQuery — dataset `sapphire`

**Raw / event tables** (partitioned by `DAY` on `timestamp` unless noted,
labeled `owner:sapphire env:prod`):

| Table | Clustering | Loaded by | Source |
|-------|------------|-----------|--------|
| `trading_signals`    | `symbol, source, outcome`   | Pub/Sub sub + GCF  | signal-logger → `sapphire-signals` topic |
| `predictions`        | `symbol, model`             | Pub/Sub sub + GCF  | prediction engine → `sapphire-predictions` topic |
| `market_regime`      | `regime`                    | Pub/Sub sub + GCF  | regime classifier → `sapphire-regime-changes` topic |
| `threat_intel`       | `severity, source`          | Pub/Sub sub + GCF  | cyber-threat-bot → `sapphire-threats` topic |
| `inference_metrics`  | `tier, model`               | GCF from GCS       | telemetry_collector → `raw/metrics/` |
| `service_health`     | `service_name, status`      | GCF from GCS       | telemetry_collector → `raw/health/` |
| `leads`              | `grade, status`             | GCF from GCS       | `gcp_sync` warm path from `data/leads/pipeline_*.json` and `data/leads/houston_leads.jsonl` |
| `regional_regions`   | `region_id, name`           | planned GCF from GCS | regional-intel workbench export → `raw/regional_regions/` |
| `regional_intel_items` | `region_id, kind, source_name` | planned GCF from GCS | regional-intel workbench export → `raw/regional_intel_items/` |
| `regional_source_health` | `status, category`       | planned GCF from GCS | regional-intel workbench export → `raw/regional_source_health/` |
| `fred_series_observations` | `series_id, realtime_start, realtime_end` | GCF from GCS | macro-intel FRED writer → `raw/fred/` (`DAY` partition on `observation_date`) |

**Rollup tables** (materialized by scheduled queries):

| Table | Cadence | Source |
|-------|---------|--------|
| `daily_performance`   | every 24h       | `trading_signals` |
| `daily_threats`       | every 24h       | `threat_intel` |
| `prediction_accuracy` | every 24h       | `predictions` |
| `weekly_regime`       | every Mon 02:00 | `market_regime` |

**Views** (14 — queries, no storage):

| View | Purpose |
|------|---------|
| `v_signals_latest`             | Most recent signal per (symbol, source) |
| `v_signals_enriched`           | `trading_signals` + concurrent regime + threat level |
| `v_signals_by_regime`          | PnL and win-rate cube: regime × outcome |
| `v_confidence_calibration`     | Confidence-bucket vs realized win-rate (model calibration) |
| `v_inference_tier_efficiency`  | p50/p95 latency, cost, failover rate per tier |
| `v_service_uptime_24h`         | 24h rolling uptime % per service |
| `v_open_threats`               | Unresolved `threat_intel` rows, severity DESC |
| `v_threat_severity_trend`      | 7d threat-count cube by severity |
| `v_prediction_vs_signal_overlap` | Did we trade when the model predicted? |
| `v_prediction_accuracy`        | Rolling prediction MAE / hit-rate |
| `v_daily_performance`          | Presentation layer on top of `daily_performance` |
| `v_regime_transitions`         | regime → regime transition matrix |
| `v_leads_funnel`               | Lead stage counts (planned data) |
| `v_trading_dashboard`          | Single view backing the dashboard card |

### BigQuery Data Transfer Service — scheduled queries

All four run as `sapphire-data-ops@`; source DDL: [`infra/gcp/sql/scheduled_queries.sql`](../infra/gcp/sql/scheduled_queries.sql).

| Display name         | Transfer config ID                        | Cadence         | Destination               |
|----------------------|-------------------------------------------|-----------------|---------------------------|
| `daily_performance`  | `69f08739-0000-2ef4-a18c-5c337bc73dfb`    | every 24h       | `sapphire.daily_performance`  |
| `weekly_regime`      | `6a171c83-0000-2292-8ab5-3c286d46cb7e`    | every Mon 02:00 | `sapphire.weekly_regime`      |
| `daily_threats`      | `6a2d0d4e-0000-28ed-abae-5c337bc5e7c7`    | every 24h       | `sapphire.daily_threats`      |
| `prediction_accuracy`| `6a3b11c0-0000-2ed7-be8a-2405888140a4`    | every 24h       | `sapphire.prediction_accuracy`|

### Pub/Sub

| Topic | Subscription | Delivery | BQ destination |
|-------|-------------|----------|----------------|
| `sapphire-signals`         | `sapphire-signals-bq`         | BQ sub | `sapphire.trading_signals` |
| `sapphire-predictions`     | `sapphire-predictions-bq`     | BQ sub | `sapphire.predictions`     |
| `sapphire-regime-changes`  | `sapphire-regime-changes-bq`  | BQ sub | `sapphire.market_regime`   |
| `sapphire-threats`         | `sapphire-threats-bq`         | BQ sub | `sapphire.threat_intel`    |
| `sapphire-alerts`          | `sapphire-alerts-pull`        | Pull   | (alerting consumer)        |

BQ subscriptions use `use_topic_schema=false` and `write_metadata=false` — the message body itself is the row payload (schema-on-write handled by the BQ table). The `eventarc-*` topic is the Cloud Function trigger plumbing; do not publish to it directly.

### Cloud Function

| Function | Trigger | Purpose |
|----------|---------|---------|
| `sapphire-gcs-to-bq` | GCS finalize on `sapphire-data-lake/raw/**` | Parse NDJSON filename → table name, append rows into matching BQ table with `WRITE_APPEND` |

Runtime: Python 3.11, `us-central1`, entrypoint `gcs_to_bq`, service account = `sapphire-data-ops`.

### Cloud Scheduler (planned)

Cloud Scheduler API is not yet enabled — `gcloud services enable cloudscheduler.googleapis.com --project=tho-ai-agent`.

| Job | Cadence (CT) | Target |
|-----|--------------|--------|
| `sapphire-daily-sync`      | 07:05       | `POST https://sapphire-analytics-*.run.app/api/sync` |
| `sapphire-weekly-aggregate`| Mon 08:00   | `POST https://sapphire-analytics-*.run.app/api/aggregate` |

## 2. Data flow

Two complementary paths land data in BigQuery:

### Path A — real-time Pub/Sub (hot path)

```
Producer (Mac)                   Pub/Sub                 BigQuery
─────────────────                ───────                 ────────
signal_pipeline.py ──┐
                     ├── publish_signal() ──► sapphire-signals ──► sapphire-signals-bq ──► trading_signals
prediction engine ───┤           
regime classifier ───┤           sapphire-predictions   ─► sapphire-predictions-bq ─► predictions
cyber-threat-bot ────┘           sapphire-regime-changes─► sapphire-regime-changes-bq ► market_regime
                                 sapphire-threats       ─► sapphire-threats-bq      ► threat_intel
```

The producer calls `services.pipeline.pubsub_publisher.publish_signal(topic, payload)`. The payload is a JSON-serializable dict that matches the destination table's schema. The BQ subscription writes it directly — end-to-end latency is typically <2s.

### Path B — batch upload (warm path)

```
Producer (Mac)             Watermark            GCS                              Cloud Function               BigQuery
─────────────────          ─────────            ───                              ──────────────               ────────
telemetry_collector ──► .gcp_sync_state.json ──┐
                                               │
gcp_sync.py (hourly :05) ──────────────────────┴──► sapphire-data-lake/raw/metrics/2026-04-17/HHMMSS.ndjson
                                                                                 │
                                                    (GCS finalize event) ───────►│
                                                                                 ▼
                                                                        sapphire-gcs-to-bq  ──► inference_metrics
                                                                        (parses filename → table,
                                                                         WRITE_APPEND, no dedup)
```

`gcp_sync.py` is **upload-only** — it does not load into BQ directly. The Cloud Function is the single authoritative loader. This is deliberate (see §5).

### Path C — scheduled rollups

```
BigQuery Data Transfer Service (running as sapphire-data-ops@)
    │
    ├─ daily_performance   ◄─ SELECT ... FROM trading_signals    ─► sapphire.daily_performance   (WRITE_TRUNCATE)
    ├─ weekly_regime       ◄─ SELECT ... FROM market_regime      ─► sapphire.weekly_regime       (WRITE_TRUNCATE)
    ├─ daily_threats       ◄─ SELECT ... FROM threat_intel       ─► sapphire.daily_threats       (WRITE_TRUNCATE)
    └─ prediction_accuracy ◄─ SELECT ... FROM predictions        ─► sapphire.prediction_accuracy (WRITE_TRUNCATE)
```

## 3. Topic → table mapping (authoritative)

Any new producer must pick one path. This is the contract.

| Producer                        | Path | Channel                                                | Destination table           |
|---------------------------------|------|--------------------------------------------------------|-----------------------------|
| `services/alpha/signal_pipeline.py` (signal emit)   | A    | topic `sapphire-signals`                     | `trading_signals` |
| `services/alpha/signal_pipeline.py` (outcome close) | A    | topic `sapphire-signals`                     | `trading_signals` (update row) |
| `scripts/kronos_daily_predictions.py`               | A    | topic `sapphire-predictions`                 | `predictions` |
| regime classifier in `lib/analytics/`               | A    | topic `sapphire-regime-changes`              | `market_regime` |
| `cyber-threat-bot` ingesters                        | A    | topic `sapphire-threats`                     | `threat_intel` |
| `services/pipeline/telemetry_collector.py` (proxy)  | B    | GCS `raw/metrics/YYYY-MM-DD/*.ndjson`        | `inference_metrics` |
| `services/pipeline/telemetry_collector.py` (probes) | B    | GCS `raw/health/YYYY-MM-DD/*.ndjson`         | `service_health` |
| `python3 -m lib.intel.pipeline --run` + `services.pipeline.gcp_sync` | B | GCS `raw/leads/YYYY-MM-DD/*.ndjson` | `leads` |
| `python3 -m services.macro_intel.run run-once --fred` + `services.pipeline.gcp_sync --source fred` | B | GCS `raw/fred/YYYY-MM-DD/*.ndjson` | `fred_series_observations` |
| (planned) regional-intel export promotion           | B    | GCS `raw/regional_regions/YYYY-MM-DD/*.ndjson` | `regional_regions` |
| (planned) regional-intel export promotion           | B    | GCS `raw/regional_intel_items/YYYY-MM-DD/*.ndjson` | `regional_intel_items` |
| (planned) regional-intel export promotion           | B    | GCS `raw/regional_source_health/YYYY-MM-DD/*.ndjson` | `regional_source_health` |
| alerting consumers                                  | —    | topic `sapphire-alerts` (pull)               | (no BQ sink)  |

Rule: **pick one path per table.** Never publish and batch-load into the same table — duplicate keys cannot be deduped post-hoc without a partitioning rewrite (see §5).

Regional-intel promotion is metadata-ready but intentionally not automated from
this repo. The tracked contract is
[`infra/gcp/regional_intel_mapping.json`](../infra/gcp/regional_intel_mapping.json):
runtime NDJSON and the manifest stay under ignored `data/foundry/regional-intel/`,
while paste-safe readiness is exposed through the local Foundry readiness audit.

## 4. Operational runbook

### Health check everything in one command

```bash
python3 -m services.pipeline.check_routines        # human
python3 -m services.pipeline.check_routines --json # machine
```

Covers launchagents, artifact freshness, and BQ DTS run state for all 4 scheduled queries.

### Manual Pub/Sub publish (smoke test)

```bash
gcloud pubsub topics publish sapphire-signals --project=tho-ai-agent \
  --message='{"timestamp":"2026-04-17T00:00:00Z","symbol":"BTC","source":"test","action":"BUY","confidence":0.9}'
# Row should appear in sapphire.trading_signals within ~2s.
```

### Manually trigger a scheduled query

```bash
bq mk --transfer_run --run_time=$(gdate -u +'%Y-%m-%dT%H:%M:%SZ') \
  projects/691674245427/locations/us/transferConfigs/69f08739-0000-2ef4-a18c-5c337bc73dfb
bq ls --transfer_run --run_attempt=LATEST --format=prettyjson \
  projects/691674245427/locations/us/transferConfigs/69f08739-0000-2ef4-a18c-5c337bc73dfb
```

### Force a GCS→BQ sync for telemetry

```bash
python3 -m services.pipeline.telemetry_collector   # writes fresh NDJSON
python3 -m services.pipeline.gcp_sync -v           # uploads to GCS; Cloud Function appends
```

### Inspect Cloud Function logs

```bash
gcloud functions logs read sapphire-gcs-to-bq --region=us-central1 --limit=100
```

### List transfer configs / subs / topics

```bash
bq ls --transfer_config --transfer_location=us --project_id=tho-ai-agent
gcloud pubsub topics list --project=tho-ai-agent
gcloud pubsub subscriptions list --project=tho-ai-agent
```

## 5. Key architectural decisions

### 5.1 Cloud Function is the single authoritative BQ loader (no direct loads from Mac)

**Why:** early implementation had `gcp_sync.py` upload to GCS *and* call `bq load`. The Cloud Function, triggered by the same GCS finalize event, did the same load. Every row landed twice.

**Fix:** stripped `_load_to_bq()` from `gcp_sync.sync_source()`. Mac uploads; GCF loads. If the function is down, data queues in GCS and backfills on the next event.

**Implication for new batch sources:** just drop NDJSON under `raw/<table>/YYYY-MM-DD/*.ndjson` and let the function pick it up. Do not call `bq load` from local scripts.

### 5.2 BQ DTS service agent needed `serviceAccountTokenCreator` on the runner SA

**Why:** the DTS service agent impersonates `sapphire-data-ops@` to execute scheduled queries. Without the binding, all four scheduled queries failed with `iam.serviceAccounts.getAccessToken` denied.

**Binding (once, already applied):**
```bash
gcloud iam service-accounts add-iam-policy-binding \
  sapphire-data-ops@tho-ai-agent.iam.gserviceaccount.com \
  --member='serviceAccount:service-691674245427@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com' \
  --role='roles/iam.serviceAccountTokenCreator'
```

Any new scheduled query owned by this SA inherits the binding automatically.

### 5.3 Partitioned tables cannot be rewritten with `CREATE OR REPLACE`

Raw tables are partitioned by `DAY` on `timestamp` and labeled. `CREATE OR REPLACE TABLE` with a non-matching partition spec fails with `Cannot replace a table with a different partitioning spec`. To dedupe or backfill: `DELETE … WHERE TRUE;` then re-sync, or use `MERGE` with an explicit row key.

### 5.4 Pub/Sub BQ subscriptions use plain-JSON schemas

`use_topic_schema=false` + `write_metadata=false`. The topic does not need a schema registered — the BQ table's schema is authoritative. Add a new field: `bq update --schema ...` on the table, then publishers can start emitting it. Old messages without the field land as NULL.

## 6. Current state (verified 2026-04-17)

Row counts:

| Table | Rows |
|-------|------|
| trading_signals     | 11 |
| predictions         | 11 |
| market_regime       | 1  |
| threat_intel        | 45 |
| inference_metrics   | 6  |
| service_health      | 11 |
| daily_performance   | 6  |
| weekly_regime       | 1  |
| daily_threats       | 8  |
| prediction_accuracy | 6  |

All 4 DTS scheduled queries: `SUCCEEDED` on their latest run. All 6 Pub/Sub subscriptions active. Cloud Function `sapphire-gcs-to-bq` healthy.
