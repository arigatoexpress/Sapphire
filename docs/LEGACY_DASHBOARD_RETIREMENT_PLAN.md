# Legacy Dashboard Retirement Plan

## Objective
Retire duplicate dashboard UIs and keep one operator-facing surface:

- Canonical operator site: `https://sapphirealpha.xyz`
- Canonical contracts: `/api/platform/status|metrics|autonomy|home-snapshot|logs|organization|readiness|projects`

## Current dependency map

- `sapphire-unified-frontend`:
  - Serves all operator pages
  - Aggregates platform contracts from canonical sources
- `sapphire-command-deck`:
  - Legacy standalone UI (no longer required by unified frontend runtime)
- `sapphire-log-viewer`:
  - Legacy standalone UI (no longer required by unified frontend runtime)
- `sapphire-health-dashboard`:
  - Legacy monitor UI (no longer embedded in unified frontend)

## Retirement sequence

1. **Now complete (UI layer)**
   - Removed iframe embeds for command deck, logs, health, and PM surfaces in unified frontend.
   - Unified frontend pages now load via platform contracts only.
2. **Parity migration (backend layer) — complete**
   - Trading metrics now sourced directly by unified backend from Firestore.
   - Logs now sourced directly by unified backend from Firestore.
3. **Service retirement**
   - Freeze old services (`command-deck`, `log-viewer`, `health-dashboard`, `dashboard`) to internal/admin only.
   - Current state: `command-deck`, `log-viewer`, and `dashboard` public invoker removed (auth required).
   - Remove domain links and public navigation references.
4. **Final prune**
   - Disable/decommission retired Cloud Run services after 14-day no-traffic observation.

## Exit criteria

- Unified frontend has no runtime dependency on legacy dashboard services.
- `/api/platform/metrics` and `/api/platform/logs` resolve directly from canonical data sources.
- Legacy dashboards receive zero production user traffic for 14 consecutive days.
