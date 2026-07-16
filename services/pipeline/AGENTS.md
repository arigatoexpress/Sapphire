# Sapphire — Pipeline Service

Agent charter for `services/pipeline/`.  This directory contains the autonomous
routines that move data from external sources into the Sapphire intelligence
layer and the Knowledge vault.

## Scope

- `tdr_pro_sync.py` — polls The DeFi Report Pro RSS, fetches transcripts, writes
  Markdown clippings to `~/Knowledge/0-Inbox/Clippings`, and maintains a master
  episode index at `~/Knowledge/3-Resources/Clippings/tdr-pro-index.md`.
- `check_routines.py` — orchestrates daily/weekly pipeline health checks.
- `fleet_status.py` — snapshots fleet health to `data/intelligence/latest/`.
- `chain_refresh.py`, `correlation_refresh.py`, `telemetry_collector.py`,
  `gcp_sync.py`, `pubsub_publisher.py`, `routine_controller.py` — other
  ingestion/refresh routines.

## How to run

```bash
# Rebuild the TDR Pro hub index from local clippings (no network required)
python3 -m services.pipeline.tdr_pro_sync --index-only

# Manual live sync (requires SAPPHIRE_TDR_PRO_LIVE=1)
SAPPHIRE_TDR_PRO_LIVE=1 python3 -m services.pipeline.tdr_pro_sync --dry-run

# Run pipeline health checks
python3 services/pipeline/check_routines.py
```

## Safety boundaries

- Live RSS/network pulls are gated by environment variables
  (`SAPPHIRE_TDR_PRO_LIVE=1`).  Do not bypass the gate in tests or CI.
- Pipeline scripts write under `~/Knowledge/` and `data/intelligence/latest/`.
  Do not write to THO/Project-Go-Forward paths.
- Prefer `--dry-run` when testing sync logic.

## Stack notes

- Python 3.11+, run from repo root or via `python3 -m services.pipeline.<module>`.
- `lib/sources/` contains the source adapters consumed here.
- LaunchAgent `com.sapphire.tdr-pro-sync` runs `tdr_pro_sync.py` on a schedule.
