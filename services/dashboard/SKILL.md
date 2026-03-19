---
name: sapphire-dashboard
description: Flask trading dashboard at sapphirealpha.xyz — PnL, positions, system status
type: service
runtime: python
deploy_target: cloud-run
dependencies: [sapphire-core]
entry_point: src/main.py
test_command: pytest tests/
---

# services/dashboard

Flask web dashboard at sapphirealpha.xyz. Displays live PnL, open positions, win rate, system health, and recent events from the event bus.

## Routes

- `/` — Dashboard home (PnL summary, positions)
- `/events` — Event stream (tag-filtered)
- `/health` — Service health check
- `/api/pnl` — PnL JSON (for Telegram bot queries)

## Security

**CRITICAL: Auth is required.** Dashboard is currently unprotected.
Add `@require_auth` decorator using a session token validated against Secret Manager.

## Deploy

```bash
gcloud run deploy sapphire-dashboard --source . --project sapphire-479610
# maps to sapphirealpha.xyz via Cloud Run domain mapping
```

## Event Integration

Dashboard polls `recent_events(tags=["type:trading"], limit=100)` every 30s for live feed.
