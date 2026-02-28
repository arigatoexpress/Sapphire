# Frontend Consolidation Backlog (Exact Tickets)

Scope: consolidate dashboards into one professional operator site and align all clients (web + macOS) to canonical platform contracts.

## Progress Update (2026-02-28)

Completed:
- **FE-201**: Unified templates now consume only `/api/platform/*` via shared client module.
- **FE-202**: Added shared `platformApi` client (`services/unified-frontend/static/js/platform-api.js`).
- **FE-301**: Command Deck page now renders native pipeline/readiness/events modules (no iframe embed).
- **FE-302**: System Health page now renders native readiness + service matrices (no iframe embed).
- **FE-303**: Logs page now renders native filtered stream from platform contracts (no iframe embed).
- **FE-401**: Organization model rendered from `/api/platform/organization` payload.
- **FE-402**: Production Readiness page tied to `/api/platform/readiness`.
- **FE-501 (partial)**: macOS client now targets unified platform routes for operator web modules and supports platform basic auth settings.
- **FE-502 (partial)**: macOS app window/settings rebranded to Sapphire Operator Client.

Remaining focus:
- **FE-304**: Backend-level retirement of legacy service dependencies (`command-deck`, `log-viewer`) after data-source parity.
- **FE-403**: Rich environment dependency graph and runbook linking.
- **FE-503**: Full native macOS parity for status/metrics/logs/readiness modules.
- **FE-601..FE-604**: Contract tests, Playwright smokes, correlation IDs, release/rollback automation.

## Epic FE-100: Information Architecture + Brand Unification
- **FE-101**: Replace legacy nav with org-first IA (Organization, Trading, Research, Development, Infra, Security, Readiness).
  - Acceptance: unified nav available on all pages; no dead links.
- **FE-102**: Rebrand copy across unified frontend to "Sapphire Operator Platform".
  - Acceptance: old dashboard naming removed from top-level UI.
- **FE-103**: Define shared design tokens (spacing, color, typography, component states).
  - Acceptance: token file consumed by all templates/components.

## Epic FE-200: Platform Contract Migration
- **FE-201**: Migrate all page data loaders to `/api/platform/*` only.
  - Acceptance: grep check shows no usage of deprecated API routes in templates.
- **FE-202**: Add platform contract client module (`platformApi`) with typed response guards.
  - Acceptance: all fetches go through one client.
- **FE-203**: Add resilience states (loading, empty, degraded, error) for every page module.
  - Acceptance: no blank modules when backend degraded.

## Epic FE-300: Dashboard Feature Merge + Retirement
- **FE-301**: Merge command deck signal controls into unified `/command-deck` module.
  - Acceptance: no dependency on separate command deck UI for core actions.
- **FE-302**: Merge health dashboard widgets into unified `/system-health`.
  - Acceptance: service matrix + node matrix + last check timestamp available.
- **FE-303**: Merge log viewer filtering into unified `/logs`.
  - Acceptance: severity/source/time filters and pagination work.
- **FE-304**: Decommission duplicated UI services after parity.
  - Acceptance: retirement list approved and removed from active user navigation.

## Epic FE-400: Organization + Operations Views
- **FE-401**: Build Organization page from canonical model (Autonomous PM, Trading/Research, Development, Gaming, Infra).
  - Acceptance: org map rendered from `/api/platform/organization` payload.
- **FE-402**: Build Readiness page tied to `/api/platform/readiness` gates.
  - Acceptance: pass/fail gates with blocker details and timestamps.
- **FE-403**: Build Environment page (Cloud, Pi, Windows, macOS) with connectivity and ownership.
  - Acceptance: each environment shows health, dependency edges, and runbooks.

## Epic FE-500: macOS Operator Client Alignment
- **FE-501**: Create platform API client in macOS app for `/api/platform/*` contracts.
  - Acceptance: no direct legacy endpoint dependencies.
- **FE-502**: Rebrand PMCommander to Sapphire Operator Client.
  - Acceptance: app title/icons/menu copy updated.
- **FE-503**: Add operator modules parity (status, metrics, logs, readiness, organization).
  - Acceptance: feature parity doc signed off.

## Epic FE-600: Quality, Testing, and Release
- **FE-601**: Add contract tests for all platform endpoints (schema snapshots).
  - Acceptance: CI fails on contract drift.
- **FE-602**: Add Playwright smoke tests for critical user journeys.
  - Acceptance: login, status load, logs load, readiness load green.
- **FE-603**: Add observability for frontend fetch failures.
  - Acceptance: backend + frontend correlation id visible in logs.
- **FE-604**: Release checklist + rollback doc for unified frontend.
  - Acceptance: one-command rollback documented and tested.

## Suggested Execution Order
1. FE-201, FE-202, FE-203
2. FE-301, FE-302, FE-303
3. FE-401, FE-402, FE-403
4. FE-501, FE-502, FE-503
5. FE-601, FE-602, FE-603, FE-604
