# Production Test and Run Strategy

Date: 2026-02-28  
Project: Sapphire Autonomous Organization Platform

## 1) Test Matrix (by environment)

### Cloud (GCP / Cloud Run)
- Contract tests: `/api/platform/{status,metrics,autonomy,home-snapshot,logs,organization,readiness,projects}`.
- Service health tests: cloud run readiness + response latency.
- Secret binding checks for runtime dependencies.
- Domain routing checks (`sapphirealpha.xyz`, `dashboard`, `gateway`, `pm`).

### Windows (TradingView + webhook)
- Webhook listener health (`:9090`)
- TV Agent health (`:8081`)
- Signal ingress test (payload -> webhook ack -> event logged)

### Pi Fleet (execution + monitoring)
- rari1/rari2 API reachability tests.
- Execution dry-run trade path.
- Monitoring feed + log shipping checks.

### macOS (operator + dev control)
- Operator app contract sync to `/api/platform/*`.
- Local command tooling check (deploy scripts, health scripts).
- Fallback admin operations if Windows/Pi degraded.

## 2) Readiness Gates (must be green for production)
1. `ContractGate`: all `/api/platform/*` schemas valid.
2. `HealthGate`: cloud services healthy; critical node endpoints reachable.
3. `SecurityGate`: sandbox enforcement on SCOUT + token auth active.
4. `IAMGate`: no non-breakglass owner/editor overreach.
5. `OpsGate`: scheduler drift removed; only live targets enabled.
6. `E2EGate`: alert -> ingest -> enrich -> route -> execution/log flow verified.

## 3) E2E Scenario Suite
- **Scenario E2E-01**: TradingView webhook event accepted and logged.
- **Scenario E2E-02**: AI enrichment path marks proceed/hold with trace id.
- **Scenario E2E-03**: Dispatch to execution venue succeeds (or safe-blocked with reason).
- **Scenario E2E-04**: SCOUT outbound dispatch routes through sandbox and is audited.
- **Scenario E2E-05**: Unified frontend renders status/metrics/logs/readiness from canonical contracts.
- **Scenario E2E-06**: Autonomy Lab renders control + learning + experiment backlog from `/api/platform/autonomy`.

### Single-command validator
- Canonical runner: `./scripts/run_e2e_signal_validation.sh`
- What it validates in sequence:
  - platform readiness gate (`/api/platform/readiness`)
  - Windows webhook + TV agent health (`:9090`, `:8081`)
  - live signal publish to Pub/Sub via Windows webhook
  - signal trace in unified frontend log contract (`/api/platform/logs`)

## 4) Release Procedure
1. Deploy sandbox updates.
2. Deploy backend (`alpha-engine`, gateway) with compatibility tests.
3. Deploy unified frontend from canonical repo.
4. Run smoke + E2E checks.
5. Shift traffic / confirm domain.
6. Monitor first 30 minutes with alerting enabled.

## 5) Rollback Procedure
1. Roll back Cloud Run traffic to prior healthy revision.
2. Disable mutable controls if contract mismatch detected.
3. Re-enable last known stable scheduler set.
4. Publish incident note + corrective follow-up ticket set.

## 6) Prune / Redundancy Rules
- Keep only one user-facing operator frontend in production.
- Retire duplicate dashboard UIs once feature parity is confirmed.
- Keep canary services only with explicit owner and expiry date.
- Remove orphan scheduler jobs and secrets not referenced by active services.

## 7) Weekly Hygiene (production)
- IAM diff audit.
- Scheduler target audit.
- Secret rotation status.
- Frontend contract drift check.
- Environment connectivity report (Cloud + Windows + Pi + macOS).
