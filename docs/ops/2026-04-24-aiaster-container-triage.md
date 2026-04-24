# AIAster Container Triage — 2026-04-24

## Decision

Decommission the three crash-looping AIAster application containers until the stack owner restores an authoritative compose file and source tree.

Containers:

- `aiaster-hyperliquid-trader-1`
- `aiaster-dashboard-1`
- `aiaster-cloud-trader-1`

Postgres and Redis are left running because they are healthy and may be needed for data recovery.

## Findings

- Docker labels point at `/Users/aribs/AIAster/docker-compose.yml`, but that compose file is absent.
- Host bind-mount directories under `/Users/aribs/AIAster/` are empty, which shadows valid files inside the existing images.
- Current crash causes:
  - hyperliquid trader: `/app/service.py` missing from the empty host mount.
  - dashboard: `/app/package.json` missing from the empty host mount.
  - cloud trader: `cloud_trader.api` missing from the empty host mount.
- The app containers include trading and Telegram environment variable names. Restarting from recovered image contents would reactivate an unreviewed trading stack, so the safe Day 1 remediation is to stop the crash loop rather than resurrect it blindly.

## Action Taken

Disable Docker restart policy and stop only the three broken app containers:

```bash
docker update --restart=no aiaster-hyperliquid-trader-1 aiaster-dashboard-1 aiaster-cloud-trader-1
docker stop aiaster-hyperliquid-trader-1 aiaster-dashboard-1 aiaster-cloud-trader-1
```

## Rollback

Restore the restart policy and start the containers after a reviewed compose file and source tree are in place:

```bash
docker update --restart=always aiaster-hyperliquid-trader-1 aiaster-dashboard-1 aiaster-cloud-trader-1
docker start aiaster-hyperliquid-trader-1 aiaster-dashboard-1 aiaster-cloud-trader-1
```

Do not run the rollback until `ENABLE_PAPER_TRADING=true` is confirmed for every trading process and Telegram production alert behavior is reviewed.
