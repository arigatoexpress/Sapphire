# Pi ASTER Execution Runbook

## Purpose
Run ASTER execution from `rari2` (Pi) so exchange orders are placed from edge network context when Cloud Run ASTER is region-blocked.

## Current Topology
- Signal ingress: TradingView/Windows webhook and Gateway publish to Pub/Sub topic `trading-signals`.
- Pi executor: `sapphire-aster-pi.service` on `rari2` consumes `trading-signals-bot-aster-pi-sub`.
- Trade telemetry: Pi worker publishes `trade-executed`, consumed by Gateway and surfaced via `/api/platform/trades`.
- Cloud ASTER: deployed but passive (`TRADING_ENABLED=false`) to avoid duplicate + region-blocked attempts.

## Deploy / Reconcile
From canonical repo root (`/Users/aribs/Sapphire`):

```bash
./scripts/deploy_rari2_aster_worker.sh
```

Key effects:
- Ensures `trading-signals-bot-aster-pi-sub` and `risk-alerts-bot-aster-pi-sub` exist.
- Ensures Pub/Sub publisher/subscriber roles for `pi-trading-agent@sapphire-479610.iam.gserviceaccount.com`.
- Syncs `services/bot-aster/src/main.py` to `rari2`.
- Installs/restarts `sapphire-aster-pi.service`.
- Keeps Cloud Run `sapphire-aster` passive unless overridden.

## Service Checks
- Pi worker status:
```bash
ssh rari@100.87.225.89 "systemctl status sapphire-aster-pi.service --no-pager"
```
- Pi worker health endpoint:
```bash
ssh rari@100.87.225.89 "curl -fsS http://127.0.0.1:18080/health"
```
- Public trade telemetry:
```bash
curl -u sapphire:alpha2024 "https://sapphirealpha.xyz/api/platform/trades?include_failed=true&limit=20"
```

## Failover / Safety Semantics
- Missing `quantity` on inbound signals can be auto-sized on Pi with:
  - `ASTER_AUTO_SIZE_NOTIONAL_USD` (enabled on Pi worker),
  - fallback `ASTER_AUTO_SIZE_FALLBACK_QUANTITY`.
- Market orders are polled for terminal status before `trade-executed` emit to avoid false `NEW` non-fill telemetry.
- Cloud ASTER remains disabled for execution (`TRADING_ENABLED=false`) while Pi route is primary.

## Rollback
### Roll back to Cloud ASTER execution
```bash
gcloud run services update sapphire-aster \
  --project sapphire-479610 \
  --region us-central1 \
  --update-env-vars TRADING_ENABLED=true
```

### Stop Pi ASTER worker
```bash
ssh rari@100.87.225.89 "sudo systemctl disable --now sapphire-aster-pi.service"
```

### Re-enable Pi ASTER worker
```bash
ssh rari@100.87.225.89 "sudo systemctl enable --now sapphire-aster-pi.service"
```

## Known Open Items
- LIGHTER live execution remains blocked by signer credential mismatch.
- `close_all` position cleanup path on ASTER needs a targeted fix for deterministic flattening through bot-managed path.
