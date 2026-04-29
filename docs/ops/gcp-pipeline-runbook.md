# GCP Pipeline Sync Runbook

Last reviewed: 2026-04-29

This runbook covers the local Sapphire-to-GCP batch sync launched by
`infra/launchagents/com.sapphire.gcp-sync.plist`. The sync transforms selected
local files under `data/` into BigQuery-shaped NDJSON, uploads them to GCS, and
relies on the `sapphire-gcs-to-bq` Cloud Function to load them into BigQuery.

The sync is production-adjacent because it writes to GCS when run without
`--dry-run`. The default operator posture is dry-run first.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.gcp-sync.plist` |
| Sync entrypoint | `services/pipeline/gcp_sync.py` |
| Pub/Sub helper | `services/pipeline/pubsub_publisher.py` |
| Local state | `data/.gcp_sync_state.json` |
| Local staging dir | `data/.gcp_stage/` |
| Stdout | `~/Library/Logs/sapphire/gcp-sync.log` |
| Stderr | `~/Library/Logs/sapphire/gcp-sync.err` |
| Routine pause name | `gcp-sync` |

## Data Flow

```text
data/* local source files
  -> transformer in services/pipeline/gcp_sync.py
  -> data/.gcp_stage/<source>_<date>_<run>.ndjson
  -> gs://sapphire-data-lake/raw/<source>/<date>/
  -> sapphire-gcs-to-bq Cloud Function
  -> BigQuery dataset tho-ai-agent.sapphire
```

The sync currently knows these source families:

| Source | Local glob | Destination table |
|---|---|---|
| `signals` | `data/signals/*.jsonl` | `trading_signals` |
| `predictions` | `data/intelligence/*/predictions.json` | `predictions` |
| `threats` | `data/intelligence/*/threats.json` | `threat_intel` |
| `regime` | `data/chain/*.json` | `market_regime` |
| `leads` | `data/leads/pipeline_*.json` | `leads` |
| `metrics` | `data/metrics/*.ndjson` | `inference_metrics` |
| `health` | `data/health/*.ndjson` | `service_health` |

## Normal Operation

Check launchd:

```bash
launchctl list com.sapphire.gcp-sync
```

Inspect recent logs:

```bash
tail -n 200 ~/Library/Logs/sapphire/gcp-sync.log
tail -n 200 ~/Library/Logs/sapphire/gcp-sync.err
```

Run a dry-run for one source:

```bash
/usr/local/bin/python3 -m services.pipeline.gcp_sync --dry-run --source signals
```

Inspect the watermark:

```bash
python3 -m json.tool data/.gcp_sync_state.json
```

Pause the scheduled sync before maintenance:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/gcp-sync
```

Resume by removing the flag only after the dry-run is clean:

```bash
rm ~/.sapphire/routine_pause/gcp-sync
```

## Common Failures

### Dry-Run Fails Before Transforming Rows

Likely causes:

- Missing Google client libraries.
- Missing or unreadable ADC credentials.
- Import path drift in the canonical checkout.

Check:

```bash
/usr/local/bin/python3 - <<'PY'
from google.cloud import bigquery, storage
print("google clients import ok")
PY
```

Dry-run creates BigQuery/Storage client objects but skips upload/load. Treat any
credential problem as a readiness issue, not as a reason to run live.

### Rows Stage But Nothing Appears In BigQuery

The sync no longer calls `load_table_from_uri` directly. Uploading to GCS should
trigger the `sapphire-gcs-to-bq` Cloud Function. Check:

1. The uploaded `gs://...` URI in the gcp-sync log.
2. Cloud Function logs for `sapphire-gcs-to-bq`.
3. BigQuery table schema compatibility.
4. Whether a routine pause flag was present.

### Duplicate Rows

Duplicates usually mean a watermark reset or old staged file was uploaded
again. Inspect `data/.gcp_sync_state.json` and compare source file mtimes.
Never delete source data to fix duplicates. Deduplicate downstream or perform a
reviewed backfill repair.

### State File Corruption

`gcp_sync.py` writes state atomically, but manual edits can still break JSON.
Move the file aside and run a single dry-run before resetting live watermarks:

```bash
mv data/.gcp_sync_state.json data/.gcp_sync_state.json.$(date +%Y%m%dT%H%M%S).bak
/usr/local/bin/python3 -m services.pipeline.gcp_sync --dry-run --source signals
```

## Safety Notes

- `--dry-run` first for every incident response.
- Do not run `--reset-watermark` live unless the duplicate-load blast radius is
  understood.
- Do not print credential files or Secret Manager payloads.
- Do not change bucket, project, or dataset names during incident response.
- Do not treat GCP write failure as a trading outage; local JSONL remains the
  source of truth.

## Escalation

Escalate when:

- Dry-run cannot instantiate clients.
- GCS upload succeeds but Cloud Function loading fails repeatedly.
- BigQuery schemas reject transformed rows after a schema change.
- A live run would replay more history than intended.

Include the command, source name, dry-run summary, watermark file excerpt, GCS
URI if one exists, and Cloud Function error summary.
