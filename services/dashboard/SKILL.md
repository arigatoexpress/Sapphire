---
name: sapphire-dashboard
description: Flask trading dashboard at sapphirealpha.xyz — PnL, positions, system status
type: service
runtime: python
deploy_target: rari1
dependencies: [sapphire-core]
entry_point: app.py
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
Use `app_with_auth.py` variant or set `ENABLE_AUTH=true` + `SESSION_SECRET`.

Public access: `dashboard.sapphirealpha.xyz` via Cloudflare Tunnel → rari1:8080.

## Deploy (on-prem — already running on rari1:8080)

```bash
# Restart with auth enabled:
ssh rari@100.120.191.1
sudo systemctl restart sapphire-dashboard
```

## Event Integration

Dashboard polls `recent_events(tags=["type:trading"], limit=100)` every 30s for live feed.
