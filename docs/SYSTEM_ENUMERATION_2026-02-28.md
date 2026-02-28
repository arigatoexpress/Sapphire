# System Enumeration (2026-02-28)

## Canonical environment
- Source-of-truth repo: `/Users/aribs/Sapphire`
- GCP project: `sapphire-479610`
- Production domain: `https://sapphirealpha.xyz`
- Domain route target: `sapphire-unified-frontend`

## Cloud Run services (us-central1)
- `agentic-pm-hub`
- `agentic-pm-hub-postgres-canary`
- `agentic-pm-hub-sqlite-canary`
- `blanga-bis-beta`
- `sapphire-alpha`
- `sapphire-command-deck`
- `sapphire-dashboard`
- `sapphire-gateway`
- `sapphire-health-dashboard`
- `sapphire-log-viewer`
- `sapphire-scout-sandbox`
- `sapphire-telegram-bot`
- `sapphire-unified-frontend` (latest ready: `00012-zjm`, 100% traffic, runtime SA: `sapphirev3@sapphire-479610.iam.gserviceaccount.com`)
- `tho-agent`

Latest production revisions (post-cutover):
- `sapphire-alpha`: `sapphire-alpha-00011-pc2` (100%)
- `sapphire-scout-sandbox`: `sapphire-scout-sandbox-00004-cln` (100%)
- `sapphire-unified-frontend`: `sapphire-unified-frontend-00012-zjm` (100%)

Legacy dashboard exposure:
- `sapphire-command-deck`: internal/auth required
- `sapphire-log-viewer`: internal/auth required
- `sapphire-dashboard`: internal/auth required
- Public operator entrypoint: `https://sapphirealpha.xyz` only

## Scheduler jobs (active)
- `agentic-pm-hub-autonomy-15m`
- `agentic-pm-hub-assistant-checkin-30m`
- `bis-automation-job`
- `weekly-self-improvement`
- `sapphire-gateway-health-6h`

Stale scheduler drift jobs were previously removed.

## IAM posture snapshot
- Project Owner: `user:aristotlespec@gmail.com` (breakglass)
- `roles/editor`: no broad editor binding currently present
- Build/deploy SA: `sapphirev3@sapphire-479610.iam.gserviceaccount.com`
  - Granted scoped deploy/build roles + storage/logging roles needed for Cloud Build pipeline

## Platform contract status (prod domain)
All canonical contracts return `200` with auth:
- `/api/platform/status`
- `/api/platform/metrics`
- `/api/platform/logs`
- `/api/platform/organization`
- `/api/platform/readiness`
- `/api/platform/projects`

Readiness gate snapshot:
- `A_contracts`: pass `6/6`
- `B_cloud`: pass `6/6`
- `C_edge`: pass `4/4` (critical edge services only)
- `overall_ok`: `true`
- `blockers`: `0`

## Unified frontend routes (prod domain)
All return `200` with auth:
- `/`
- `/trading`
- `/command-deck`
- `/system-health`
- `/logs`
- `/projects`
- `/organization`
- `/production-readiness`
- `/infrastructure`

## Cross-environment health summary
From monitor run (`unified_health_monitor.py --check`):
- Overall: `17/18 healthy`
- Healthy:
  - Pi services (`rari1`, `rari2`) APIs/monitoring reachable
  - Windows webhook (`100.71.10.48:9090`) healthy
  - Cloud services healthy (including unified frontend)
  - Firestore healthy
- Unhealthy:
  - `windows_tv_agent` timeout
  - Classified as non-critical for production readiness gate

## Important interpretation note
- Unified frontend’s cloud-local node probes (`/api/platform/status`) report Pi/Windows as `unreachable_from_cloud` because Cloud Run cannot directly reach private Tailscale IP space.
- Fleet truth for edge nodes should come from monitor snapshots (`system_status/current`) rather than direct Cloud Run node probes.

## macOS operator client status
Path: `/Users/aribs/Documents/Organized/Codex Projects/macos/PMCommanderApp`
- Build status: `swift build` successful after migration changes
- Updated to:
  - unified platform web routes for operator tabs
  - platform basic-auth settings + keychain password handling
  - rebranded window title (`Sapphire Operator Client`)
