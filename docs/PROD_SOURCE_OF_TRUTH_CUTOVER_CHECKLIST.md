# Production Source-of-Truth Cutover Checklist

Owner repo: `/Users/aribs/Sapphire`  
GCP project: `sapphire-479610`

## Phase A: Freeze Drift
1. Freeze production writes from non-canonical repos.
2. Pause or delete scheduler jobs targeting retired services.
3. Record current Cloud Run inventory and domain mappings snapshot.
4. Lock deployment scripts to canonical repo only.

## Phase B: Canonical Contracts
1. Confirm platform API contracts exist and return stable schema:
   - `GET /api/platform/status`
   - `GET /api/platform/metrics`
   - `GET /api/platform/autonomy`
   - `GET /api/platform/home-snapshot`
   - `GET /api/platform/logs`
   - `GET /api/platform/organization`
   - `GET /api/platform/readiness`
   - `GET /api/platform/projects`
2. Deprecate legacy API routes by wrapping or redirecting to platform routes.
3. Add contract smoke test script in CI (schema + required fields).

## Phase C: Frontend Consolidation
1. Deploy unified frontend from canonical repo path only:
   - `/Users/aribs/Sapphire/services/unified-frontend`
2. Point `sapphirealpha.xyz` to unified frontend service.
3. Move embedded dashboard capabilities into unified pages, then retire duplicate services.

## Phase D: Runtime Security
1. Enforce SCOUT outbound through sandbox only (`SAPPHIRE_SCOUT_SANDBOX_ENFORCE=true`).
2. Bind required secrets:
   - `SAPPHIRE_SCOUT_SANDBOX_TOKEN`
   - `SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL` (if used)
   - `SAPPHIRE_SCOUT_EXTERNAL_POST_URL` (if used)
3. Run IAM least-privilege pass with rollback snapshot.

## Phase E: Validation + Go/No-Go
1. Run cross-environment health checks (Cloud + Pi + Windows).
2. Run production readiness gate (`/api/platform/readiness`) until green.
3. Execute E2E dispatch test:
   - command ingress -> gateway -> alpha-engine -> execution/logging path.
4. Sign-off checklist:
   - API contracts green
   - telemetry/logging green
   - no stale scheduler jobs
   - no owner/editor sprawl outside breakglass

## Rollback Plan
1. Preserve previous Cloud Run revision tags before each deploy.
2. Keep domain mapping unchanged during app-level rollbacks.
3. Roll back by traffic shift to previous stable revision.
4. Re-enable paused scheduler jobs only if their target service is restored.
