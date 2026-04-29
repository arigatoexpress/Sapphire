# Telemetry Collector Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.telemetry-collector`, the local LaunchAgent
that snapshots inference-proxy metrics and service health every five minutes.
It writes local NDJSON files consumed later by GCP sync and downstream
BigQuery/Foundry paths.

The collector is observational. It should not mutate services, restart daemons,
send Telegram messages, execute trades, or upload to cloud storage by itself.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.telemetry-collector.plist` |
| Collector | `services/pipeline/telemetry_collector.py` |
| GCP sync consumer | `services/pipeline/gcp_sync.py` |
| Data engineering doc | `docs/gcp-data-engineering.md` |
| BigQuery views | `infra/gcp/sql/analytics_views.sql` |
| Unit test | `tests/unit/test_telemetry_collector.py` |
| Metrics output | `data/metrics/YYYY-MM-DD.ndjson` |
| Health output | `data/health/YYYY-MM-DD.ndjson` |
| Stdout log | `/Users/aribs/autonomy-status/logs/telemetry-collector.log` |
| Stderr log | `/Users/aribs/autonomy-status/logs/telemetry-collector.err` |
| Routine pause name | `telemetry-collector` |

## Schedule

The LaunchAgent has `RunAtLoad=true` and `StartInterval=300`. It runs once at
load, then every five minutes:

```bash
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/services/pipeline/telemetry_collector.py
```

Unlike several newer plists, this file does not set `WorkingDirectory` or
`PYTHONPATH`. The script inserts the repo root into `sys.path` from its own
location.

## Data Flow

```text
LaunchAgent every 5 minutes
  -> services/pipeline/telemetry_collector.py
  -> http://127.0.0.1:11435/metrics
  -> data/metrics/YYYY-MM-DD.ndjson
  -> service probes in SERVICES
  -> data/health/YYYY-MM-DD.ndjson
  -> later: services.pipeline.gcp_sync uploads raw/metrics and raw/health
  -> Cloud Function loads BigQuery tables and analytics views
```

Metrics rows map inference proxy endpoint names to BigQuery tiers through
`TIER_MAP`. Health rows probe local, Tailscale, and Cloud Run endpoints listed
in `SERVICES`.

Downstream cloud paths include `gs://sapphire-data-lake/raw/metrics/...` and
`gs://sapphire-data-lake/raw/health/...`, which are loaded by the
GCS-to-BigQuery function. That upload path is not part of this collector run.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.telemetry-collector
launchctl print gui/$(id -u)/com.sapphire.telemetry-collector
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/autonomy-status/logs/telemetry-collector.log
tail -n 200 /Users/aribs/autonomy-status/logs/telemetry-collector.err
```

Inspect today's local outputs:

```bash
today="$(date -u +%Y-%m-%d)"
tail -n 5 "data/metrics/$today.ndjson" 2>/dev/null
tail -n 5 "data/health/$today.ndjson" 2>/dev/null
```

Count rows:

```bash
today="$(date -u +%Y-%m-%d)"
wc -l "data/metrics/$today.ndjson" "data/health/$today.ndjson" 2>/dev/null
```

Run the safe test path:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_telemetry_collector.py -q
```

## Manual Collection

Run a one-shot collection only when appending local NDJSON is acceptable:

```bash
/usr/local/bin/python3 services/pipeline/telemetry_collector.py
```

Limit to one source when debugging:

```bash
/usr/local/bin/python3 services/pipeline/telemetry_collector.py --metrics
/usr/local/bin/python3 services/pipeline/telemetry_collector.py --health
```

These commands append to `data/metrics/` or `data/health/`. They do not upload
to GCS or BigQuery. Cloud upload is a separate `gcp_sync.py` action and should
follow that runbook/gate.

Do not unload, reload, bootstrap, or kickstart the LaunchAgent during read-only
inspection. The safe inspection surface is plist lint, launchctl status, logs,
row counts, and explicit one-shot commands when local NDJSON appends are
acceptable.

## Routine Pause

Pause before service endpoint changes, network maintenance, or data-retention
cleanup:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/telemetry-collector
```

Resume after the probe list and local outputs are verified:

```bash
rm ~/.sapphire/routine_pause/telemetry-collector
```

The collector calls `abort_if_paused("telemetry-collector")` before writing
rows.

## Common Failures

### Empty Metrics Output

`collect_metrics()` returns no rows when `http://127.0.0.1:11435/metrics` is
unreachable or malformed. Check inference-proxy health before editing the
collector:

```bash
curl -fsS http://127.0.0.1:11435/health | python3 -m json.tool
curl -fsS http://127.0.0.1:11435/metrics | python3 -m json.tool
```

### Health Rows Show Down for Remote Hosts

The service list includes Windows, Pi, regional-intel, and Cloud Run probes.
Transient Tailscale/offline failures should show as `down` rows, not as
collector crashes. Classify whether the endpoint is expected to be online
before changing `SERVICES`.

### Files Grow Quickly

The LaunchAgent appends every five minutes. Use retention/rotation policy
before deleting history. These files are downstream evidence for GCP sync and
service health analysis.

### GCP Sync Does Not See Rows

The collector only writes local NDJSON. Confirm `data/metrics/YYYY-MM-DD.ndjson`
and `data/health/YYYY-MM-DD.ndjson` first, then debug
`services/pipeline/gcp_sync.py`. Do not force cloud upload just to test the
collector, and do not edit `data/.gcp_sync_state.json` as a collector fix.

### Stale Endpoint List

When a service moves ports or paths, update `SERVICES` with a focused unit test.
The existing regional-intel test pins `/api/health` because route drift has
broken this surface before.

## Safety Notes

- Do not add secret-bearing URLs or tokens to `SERVICES`.
- Do not make probes mutate state; only GET health/readiness endpoints.
- Do not upload to GCS/BigQuery from this runbook.
- Do not call `bq load` directly for collector files; the Cloud Function path
  is the authoritative loader.
- Do not delete historical `data/metrics/` or `data/health/` without an
  explicit retention cleanup request.
- Do not restart monitored services as part of telemetry collection.
- Do not treat remote-host `down` rows as proof of an incident without checking
  expected availability.
- Do not add secrets or credential-bearing environment variables to the plist.

## Escalation

Escalate when:

- No metrics or health rows are written for more than two expected intervals.
- The collector crashes instead of recording down/degraded rows.
- A probe starts requiring credentials or returns secret-bearing content.
- GCP sync, Foundry, or dashboards depend on telemetry that is stale.
- A service move requires changing monitored endpoint contracts.

Include launchd status, today's row counts, last 200 stdout/stderr lines, the
specific endpoint failing, and whether the routine pause flag is present.
