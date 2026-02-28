# Frontend Module Migration Backlog

Date: 2026-02-28  
Canonical repo: `/Users/aribs/Sapphire`

## Objective
Consolidate all operator surfaces into one professional production frontend (`sapphirealpha.xyz`) using canonical platform contracts:
- `/api/platform/status`
- `/api/platform/metrics`
- `/api/platform/logs`
- `/api/platform/organization`
- `/api/platform/projects`
- `/api/platform/readiness`

## Ticket Queue (execution order)

### Phase FE-1: Information architecture + shared shell
1. `SAPPHIRE-FE-001` Sidebar IA refresh
- Replace current section naming with org-driven groups: Organization OS, Trading, Development, Research, Infrastructure.
- Acceptance: no clipping on desktop/mobile, clear active state, keyboard focus support.

2. `SAPPHIRE-FE-002` Unified visual system hardening
- Finalize glass tokens, type scale, spacing, card hierarchy, status color semantics.
- Acceptance: all pages consume the same base token set with no per-page overrides for core primitives.

3. `SAPPHIRE-FE-003` Platform API client normalization
- Ensure all pages use `platform-api.js` only (no direct cross-service fetches from templates).
- Acceptance: grep finds no ad-hoc fetches to non-platform endpoints in templates.

### Phase FE-2: Organization-first page migration
4. `SAPPHIRE-FE-010` PM Hub organization ingestion contract
- Normalize PM Hub `organization` payload to internal stable schema.
- Acceptance: schema guards + fallback defaults; no page crash on partial PM Hub payloads.

5. `SAPPHIRE-FE-011` Organization page redesign
- Use PM Hub organization as primary source; redesign org chart, lanes, and KPI cards for executive readability.
- Acceptance: page loads under 1.5s cached and under 3s uncached.

6. `SAPPHIRE-FE-012` Cross-department workload map
- Add module showing projects by department (Trading, Research, Development, Poker/Blackjackal).
- Acceptance: all active tracked projects render with owner + status + risk.

### Phase FE-3: Trading + operations modules
7. `SAPPHIRE-FE-020` Trading operations board
- Merge useful components from command deck + health + logs into one trading ops page.
- Acceptance: signal ingress state, publish counters, venue readiness, last 20 execution events.

8. `SAPPHIRE-FE-021` Live signal trace panel
- Add signal trace view: received -> enriched -> published -> consumed.
- Acceptance: click signal_id opens full event chain from logs contract.

9. `SAPPHIRE-FE-022` Production readiness dashboard polish
- Convert readiness page to gate-centric visualization with explicit blocker routing.
- Acceptance: each failed gate has action path + owner field.

### Phase FE-4: macOS operator client alignment
10. `SAPPHIRE-MAC-001` macOS app contract alignment
- Move macOS app data layer to `/api/platform/*` only.
- Acceptance: no direct calls to legacy service-specific endpoints.

11. `SAPPHIRE-MAC-002` UI parity with web operator shell
- Apply same nav taxonomy, badges, and health semantics as web.
- Acceptance: operator can switch web/macOS with near-zero context shift.

### Phase FE-5: Decommission duplicates
12. `SAPPHIRE-FE-030` Dashboard retirement matrix
- Map old services (`sapphire-dashboard`, `sapphire-command-deck`, `sapphire-health-dashboard`, `sapphire-log-viewer`) to replacement modules.
- Acceptance: explicit cutover date + rollback pointer per legacy surface.

13. `SAPPHIRE-FE-031` Legacy route deprecation
- Route old dashboards to unified equivalents or archive page.
- Acceptance: no orphan public UI endpoint without an owner.

## Current status (2026-02-28)
- ✅ Unified site online at `https://sapphirealpha.xyz`
- ✅ Platform contracts all 200
- ✅ Cross-env monitor green (`18/18`)
- ✅ Windows webhook + TV agent reachable
- ✅ E2E live signal publish validated from Windows webhook -> Pub/Sub -> platform logs

## Immediate next implementation batch
- Batch A: `SAPPHIRE-FE-001`, `SAPPHIRE-FE-002`, `SAPPHIRE-FE-003`
- Batch B: `SAPPHIRE-FE-010`, `SAPPHIRE-FE-011`
- Batch C: `SAPPHIRE-FE-020`, `SAPPHIRE-FE-021`
