# Sapphire Index

Fast map of canonical code paths, deployed runtime, and documentation entrypoints.

## Start Here
- `README.md`
- `AGENTS.md`
- `docs/INDEX.md`
- `OPERATIONS_RUNBOOK.md`

## Canonical Public Surface
- Domain: `https://sapphirealpha.xyz`
- Public API namespace: `/api/platform/*`
- Public site is read-only (`ENABLE_INTERNAL_JOBS=false` on frontend service).

## Deployed Runtime (project: `sapphire-479610`)

### Core services
- `sapphire-unified-frontend` (`services/unified-frontend/`)
- `sapphire-unified-jobs` (`services/unified-frontend/`, internal jobs runtime)
- `sapphire-gateway` (`services/api-gateway/`)
- `sapphire-alpha` (`services/alpha-engine/`)
- `sapphire-scout-sandbox` (`services/scout-sandbox/`)
- `agentic-pm-hub`

### Optional/support services
- `tho-agent`
- `blanga-bis-beta`
- `sapphire-telegram-bot`

### Venue services (cloud standby posture)
- `sapphire-lighter` (`services/bot-lighter/`) - cloud service deployed but edge execution is canonical.
- `sapphire-aster` (`services/bot-aster/`) - cloud service deployed but edge execution is canonical.

## Canonical Runtime Paths
- Frontend platform API + internal jobs: `services/unified-frontend/app.py`
- Gateway webhook ingest + signal routing: `services/api-gateway/src/main.py`
- Alpha strategy/control plane: `services/alpha-engine/src/main.py`
- Lighter execution bot: `services/bot-lighter/src/main.py`
- Aster execution bot: `services/bot-aster/src/main.py`

## Validation and Ops Gates
- `scripts/run_production_check.sh`
- `scripts/platform_contract_audit.sh`
- `scripts/frontend_visual_smoke.sh`
- `scripts/cleanup_scheduler_drift.sh`
- `scripts/run_strategy_validation_cycle.sh`

## Current Audit Baseline
- `docs/FULL_SYSTEM_EFFICIENCY_AUDIT_2026-03-07.md`
