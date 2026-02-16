# Sapphire First-Principles Audit (2026-02-12)

Note (2026-02-16):
- The OpenClaw gateway service is now deployed as `openclaw-gateway` (not `sapphire-gateway`).
- The `/sapphire` ops control plane is served by `sapphire-control` (dashboard + directive state).
- The legacy `cloud_trader/` codebase referenced below has been archived under `archive/legacy/cloud_trader/`.

## Objective Function

Primary objective:
- Maximize risk-adjusted, repeatable trading PnL.

Hard constraints:
- Capital protection first.
- Single-owner governance via Telegram.
- Strict scope to Sapphire repo + sapphire-479610 GCP.
- Security controls must degrade safely under failure.

## Current Snapshot

- Control plane (`sapphire-alpha`) is live on Cloud Run and dispatching autonomy cycles.
- Execution venues (`sapphire-aster`, `sapphire-lighter`) are IAM-restricted to service-account invocation.
- OpenClaw gateway (`openclaw-gateway`) is IAM-restricted and internal-ingress.
- Frontend (Firebase Hosting `sapphirealpha.xyz`) is deployed with cache-busting + build stamps.
- VirusTotal integration is active with free-tier-safe defaults in code and runtime.

## Findings (Prioritized)

### P0 - Public control-plane surface exposes internal state and mutable actions

Evidence:
- `scripts/deploy_sapphire_alpha.sh` deploys with `--allow-unauthenticated`.
- `services/alpha-engine/shared/health.py` exposes control/status/log/forum/security endpoints without API auth middleware.

Risk:
- Anonymous callers can read operational internals and trigger non-trading mutations (forum, scout, VT scans).
- VT quota can be exhausted by repeated public scan requests.

### P0 - Autonomy defaults permit immediate self-approval for code/cloud changes

Evidence:
- `services/alpha-engine/src/main.py` defaults allow code + gcloud changes and disables owner approval by default.
- Startup dispatch immediately triggers a full autonomy cycle.

Risk:
- A bad instruction path can execute quickly without human checkpointing.

### P1 - Secret hygiene debt in legacy/shared code paths

Evidence:
- `archive/legacy/cloud_trader/cloud_trader/credentials.py` prints API key prefixes/lengths and has a default Jupiter key.
- `archive/legacy/cloud_trader/cloud_trader/jupiter_trader_unified.py` includes example credentials resembling real keys.

Risk:
- Increased chance of accidental secret disclosure and poor operational hygiene.

### P1 - Collaboration state durability is local-file based

Evidence:
- `services/alpha-engine/src/collaboration/forum.py` falls back to `/tmp/sapphire_forum_store.json` when state dir is unset.

Risk:
- Forum/autonomy context can be lost on container restart or revision roll.

### P2 - Product/ops divergence from streamlined architecture goal

Evidence:
- Large residual legacy surface still exists (`archive/legacy/`, monolith-era modules).
- Multiple TODO placeholders remain in execution-critical modules.

Risk:
- Maintenance load and ambiguity around which code paths are authoritative.

## Remediation Plan

### 0-72 hours (Stability + security baseline)

1. Protect mutable Alpha endpoints with an app-layer control token (`X-Sapphire-Control-Token`) and keep read-only endpoints public.
2. Move forum/autonomy durable state to managed storage (Firestore or Cloud SQL).
3. Keep DEX execution in `paper` by default and require explicit Telegram promotion command for stage changes.
4. Enforce VT free-tier limits in runtime (already implemented) and schedule scans conservatively.

### 1-2 weeks (Autonomy quality)

1. Add policy engine for autonomy actions:
   - Allowed command classes, deny-list, and max-change budget per cycle.
2. Persist autonomy session lifecycle to durable store with audit timestamps.
3. Add canary checks before enabling live dispatch (venue health, latency, spread quality, drawdown gate).

### 2-6 weeks (World-class operating model)

1. Split control-plane APIs:
   - Public read model (dashboard)
   - Private mutation model (Telegram + signed automation jobs)
2. Build formal promotion gate with measurable thresholds:
   - Fill quality, slippage, win-rate confidence intervals, max drawdown.
3. Add unified execution ledger and PnL attribution per strategy/venue/agent.
4. Archive or remove deprecated assets and legacy integrations from deploy path.

## VT Free-Tier Mode (Applied)

- `upload_if_missing_default=false`
- `max_requests_per_minute=4`
- `max_requests_per_day=500`
- `max_skills_per_scan=4`

This mode is implemented in deploy defaults, wiring scripts, backend scanner logic, and frontend/Telegram scan defaults.
