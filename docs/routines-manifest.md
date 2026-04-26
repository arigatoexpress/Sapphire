# Sapphire OS — Routines Manifest

Last updated: 2026-04-26

Every automated routine in the Sapphire OS mesh. Single source of truth — if a job runs on a schedule, it is listed here with its schedule, owner process, output artifact, and recovery runbook. Anything not on this list should either be added or killed.

Three runtime surfaces host routines:

1. **Mac LaunchAgents** (`~/Library/LaunchAgents/com.sapphire.*.plist`) — always-on services and cron-style batch jobs. The Mac is commander.
2. **GCP Cloud Scheduler** (`tho-ai-agent` project) — off-host jobs that target Cloud Run / BigQuery.
3. **Claude Code scheduled tasks** (`~/.claude/scheduled-tasks/*.yaml`) — agent workflows; listed in `CLAUDE.md`. Not repeated here.

## 1. Always-on Mac services

| LaunchAgent | Port | Purpose | Log |
|-------------|------|---------|-----|
| `com.sapphire.inference-proxy`   | 11435 | 4-tier inference failover (GPU → Pi → Mac → Kimi) | `~/Library/Logs/sapphire/inference-proxy.log` |
| `com.sapphire.control-plane`     | 8082  | PM hub: projects, tasks, events, Kimi bridge | `~/Library/Logs/sapphire/control-plane.log` |
| `com.sapphire.dashboard`         | 8080  | Flask web UI (auth: sapphire) | `~/Library/Logs/sapphire/dashboard.log` |
| `com.sapphire.signal-logger`     | 18081 | Webhook receiver → signal pipeline → Telegram | `~/Library/Logs/sapphire/signal-logger.log` |
| `com.sapphire.openbb-api`        | 6900  | OpenBB REST gateway (32 providers) | `~/Library/Logs/sapphire/openbb-api.log` |
| `com.sapphire.regional-intel`    | 8787  | Vote monitor + intelligence console | `~/Library/Logs/sapphire/regional-intel.log` |
| `ai.hermes.gateway`              | —     | Telegram bot (NousResearch framework) | `~/.hermes/logs/gateway.log` |
| `com.sapphire.cloudflare-tunnel` | —     | Public tunnel for remote access | `~/Library/Logs/sapphire/cloudflare-tunnel.log` |

Check: `launchctl list | grep sapphire` — every row should show a PID (online) or `-` with exit code 0 (scheduled, last run OK).

## 2. Scheduled Mac LaunchAgents

| Label | Cadence | Script | Output | Runbook |
|-------|---------|--------|--------|---------|
| `com.sapphire.morning-brief`       | 06:00 local / 07:00 CT | `services/intelligence/daily_brief.py`      | `data/intelligence/latest/daily_brief.md` + Telegram digest        | Manual dry-run: `python3 services/intelligence/daily_brief.py --dry-run` |
| `com.sapphire.kronos-daily`        | 07:00 CT           | `scripts/kronos_daily_predictions.py`       | `data/intelligence/YYYY-MM-DD/predictions.json`                    | Manual: `python3 scripts/kronos_daily_predictions.py`; GPU must be up |
| `com.sapphire.threat-refresh`      | every 4h           | `services/dashboard/refresh_threats.py`     | `data/intelligence/YYYY-MM-DD/threats.json`                        | Manual: `python3 services/dashboard/refresh_threats.py`; check CISA/NVD reachability |
| `com.sapphire.chain-refresh`       | every 15 min       | `services.pipeline.chain_refresh`           | `data/chain/chain_<ts>.json` + `data/intelligence/latest/chain.json` | Manual: `python3 -m services.pipeline.chain_refresh` |
| `com.sapphire.correlation-refresh` | hourly at :17      | `services.pipeline.correlation_refresh`     | `data/intelligence/latest/correlations.json`                       | Manual: `python3 -m services.pipeline.correlation_refresh` |
| `com.sapphire.gcp-sync`            | hourly at :05      | `services.pipeline.gcp_sync`                | Uploads to `gs://sapphire-data-lake/raw/*`; Cloud Function loads BQ | Manual: `python3 -m services.pipeline.gcp_sync -v` |
| `com.sapphire.logrotate`           | 03:30 CT daily     | `infra/logrotate.py`                        | `.gz` archives under `~/autonomy-status/logs/` and `~/.hermes/logs/` | Manual: `python3 infra/logrotate.py` |
| `com.sapphire.backtest-weekly`      | Sat 22:00 local    | `python3 -m lib.analytics.run_strategies --days 90 --bankroll 10000` | `data/backtests/strategies/*.json`                                 | Remote shadow: `.github/workflows/weekly-backtest.yml`; keep local until artifacts soak clean |
| `com.sapphire.content-engine`       | daily 06:00 local  | `python3 -m lib.content`                    | `data/content/drafts/*.json`, `data/content/ready/**/*`, `data/market_pulse/*.md` | Remote shadow: `.github/workflows/content-engine.yml`; keep local until artifacts soak clean |

## 2.1 Remote-shadow schedules

Remote shadows run in parallel with local LaunchAgents during the migration window.
They do not replace the local routine until artifacts are compared and the local
plist is explicitly disabled.

| Workflow | Cron | Local routine shadowed | Output |
|----------|------|------------------------|--------|
| `.github/workflows/weekly-backtest.yml` | Sun 04:00 UTC | `com.sapphire.backtest-weekly` | GitHub Actions artifact `weekly-backtest-<run_id>` |
| `.github/workflows/threat-refresh.yml` | 01:10, 05:10, 09:10, 13:10, 17:10, 21:10 UTC | `com.sapphire.threat-refresh` | GitHub Actions artifact `threat-refresh-<run_id>`; uses the wrapper's native public-source mode so no private cross-repo token is required |
| `.github/workflows/content-engine.yml` | 12:00 UTC daily | `com.sapphire.content-engine` | GitHub Actions artifact `content-engine-<run_id>`; runs with `SAPPHIRE_PUBLISH_LIVE=0` and `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=0` |

Weekly backtest entered soak tracking on 2026-04-26 after local and remote
artifacts compared PASS across all 756 rows with matching top-3 leaderboard
order. Evidence: `docs/org/backtest-weekly-shadow-soak-2026-04-26.md`.

Threat-refresh entered soak tracking on 2026-04-26 after a close-time manual
comparison matched all 15 canonical IDs with 0 FAIL rows. Evidence:
`docs/org/threat-refresh-shadow-soak-2026-04-26.md`.

Content-engine entered remote shadow tracking on 2026-04-26 after publisher
Telegram side effects were explicitly opt-in. The remote shadow generates
draft/ready artifacts only; it does not run the live publisher. Evidence:
`docs/org/content-engine-shadow-soak-2026-04-26.md`.

Compare local and remote weekly backtest artifacts with:

```bash
python3 scripts/ops/compare_backtest_artifacts.py \
  --local-root data/backtests/strategies \
  --remote-root /path/to/gh-artifact \
  --max-skew-minutes 90
```

For explicit one-off comparisons, pass exact artifact paths:

```bash
python3 scripts/ops/compare_backtest_artifacts.py \
  --local-sweep data/backtests/strategies/strategy_sweep_<LOCAL_TS>.json \
  --remote-sweep /path/to/gh-artifact/data/backtests/strategies/strategy_sweep_<REMOTE_TS>.json \
  --local-best data/backtests/strategies/best_per_symbol_<LOCAL_TS>.json \
  --remote-best /path/to/gh-artifact/data/backtests/strategies/best_per_symbol_<REMOTE_TS>.json
```

Compare local and remote threat-refresh artifacts with:

```bash
python3 scripts/ops/compare_threat_artifacts.py \
  --local-root data/intelligence \
  --remote-root /path/to/gh-artifact \
  --max-skew-minutes 30
```

For explicit one-off comparisons, pass exact artifact paths:

```bash
python3 scripts/ops/compare_threat_artifacts.py \
  --local data/intelligence/runs/<LOCAL_TS>/threats.json \
  --remote /path/to/gh-artifact/data/intelligence/runs/<REMOTE_TS>/threats.json
```

Compare local and remote content-engine artifacts with:

```bash
python3 scripts/ops/compare_content_artifacts.py \
  --local-root /Users/aribs/Code/Sapphire \
  --remote-root /path/to/gh-artifact
```

All scripts are self-contained — they write their artifacts and exit. A routine is "healthy" if its artifact's mtime is within the expected cadence window.

## 3. GCP-side routines

### BigQuery scheduled queries (Data Transfer Service)

All four are owned by `sapphire-data-ops@tho-ai-agent.iam.gserviceaccount.com`; the BQ DTS service agent needs `roles/iam.serviceAccountTokenCreator` on that SA. Source DDL: [`infra/gcp/sql/scheduled_queries.sql`](../infra/gcp/sql/scheduled_queries.sql).

| Display name         | Cadence         | Source table       | Destination table          |
|----------------------|-----------------|--------------------|----------------------------|
| `daily_performance`  | every 24h       | `trading_signals`  | `sapphire.daily_performance`  |
| `daily_threats`      | every 24h       | `threat_intel`     | `sapphire.daily_threats`      |
| `prediction_accuracy`| every 24h       | `predictions`      | `sapphire.prediction_accuracy`|
| `weekly_regime`      | every Mon 02:00 | `market_regime`    | `sapphire.weekly_regime`      |

Manual trigger: `bq mk --transfer_run --run_time=<NOW-ISO> projects/691674245427/locations/us/transferConfigs/<id>`
List: `bq ls --transfer_config --transfer_location=us --project_id=tho-ai-agent`

### Cloud Scheduler jobs (planned)

These are documented but not yet provisioned — Cloud Scheduler API must first be enabled:

```bash
gcloud services enable cloudscheduler.googleapis.com --project=tho-ai-agent
```

| Job                        | Cadence (CT) | Target                                                          | Purpose |
|----------------------------|--------------|-----------------------------------------------------------------|---------|
| `sapphire-daily-sync`      | 07:05        | `POST https://sapphire-analytics-*.run.app/api/sync`            | Trigger a consolidated sync after morning brief + Kronos |
| `sapphire-weekly-aggregate`| Mon 08:00    | `POST https://sapphire-analytics-*.run.app/api/aggregate`       | Rebuild weekly rollups + export to GCS Parquet |

### Cloud Function triggers

| Function              | Trigger                          | Purpose |
|-----------------------|----------------------------------|---------|
| `sapphire-gcs-to-bq`  | GCS finalize on `sapphire-data-lake/raw/*` | Auto-load new NDJSON into matching BQ table |

### Pub/Sub → BigQuery subscriptions

| Topic                     | Subscription                  | Destination table        |
|---------------------------|-------------------------------|--------------------------|
| `sapphire-signals`        | `sapphire-signals-bq`         | `sapphire.trading_signals` |
| `sapphire-predictions`    | `sapphire-predictions-bq`     | `sapphire.predictions`     |
| `sapphire-regime-changes` | `sapphire-regime-changes-bq`  | `sapphire.market_regime`   |
| `sapphire-threats`        | `sapphire-threats-bq`         | `sapphire.threat_intel`    |
| `sapphire-alerts`         | `sapphire-alerts-pull`        | (pull — consumed by alerting) |

## 4. Planned routines (tracked; not yet implemented)

| Name                  | Cadence       | Script                                          | Notes |
|-----------------------|---------------|-------------------------------------------------|-------|
| `lead-refresh`        | Mon 09:00 CT  | `scripts/lead_refresh.sh` (not written)         | Re-collect Houston permits, score new leads |
| `ops-report`          | 23:00 CT      | `scripts/ops_report.py` (not written)           | Daily ops summary → Telegram + `data/intelligence/YYYY-MM-DD/ops_report.md` |
| `weekly-backup`       | Sun 04:00 CT  | `scripts/bq_export_parquet.sh` (not written)    | Export key BQ tables → `gs://sapphire-archives/parquet/<date>/` |

## 5. Monitoring

- `services.pipeline.check_routines` — audits every row in this manifest. Prints a pass/fail table and exits non-zero if any routine is stale.
  ```bash
  python3 -m services.pipeline.check_routines
  ```
- Watchdog tool (`plugins/claw-sapphire/tools/watchdog.py`) — runs every 2h, sends Telegram on service state transitions.
- `v_service_uptime_24h` BigQuery view — 24-hour rolling uptime per service, fed by `services.pipeline.telemetry_collector`.

## 6. Recovery playbook

A routine is broken when its artifact is stale *and* its log shows errors.

1. **Identify** — `python3 -m services.pipeline.check_routines` locates the stale routine.
2. **Inspect log** — `tail -100 ~/Library/Logs/sapphire/<label>.err`.
3. **Run manually** — each row above has a "Manual" command. If it succeeds interactively, the code path is fine.
4. **Reload the LaunchAgent** if the plist itself was edited:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.sapphire.<label>.plist
   launchctl load -w ~/Library/LaunchAgents/com.sapphire.<label>.plist
   ```
5. **For GCP** — scheduled queries: `bq ls --transfer_run ...`. Cloud Function: `gcloud functions logs read sapphire-gcs-to-bq --region=us-central1`.
