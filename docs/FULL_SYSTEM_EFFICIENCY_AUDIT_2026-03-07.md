# Full System Efficiency Audit (2026-03-07)

## Scope
- Repo: `/Users/aribs/Sapphire`
- Runtime: GCP project `sapphire-479610` + edge nodes (`rari1`, `rari2`)
- Objective: identify inefficiencies, failures, underutilization, redundancy, technical debt, and consolidation actions to reach a streamlined world-class public technical system.

## Evidence Snapshot
- `scripts/run_production_check.sh`: **PASS**
  - Contracts: `19/19`
  - Cloud services: `6/6`
  - Edge checks: `2/2` (optional Windows degraded noted)
- Cloud Run services: `11`
- Scheduler jobs: `10` enabled (no stale jobs in allowlist drift audit)
- 24h Cloud Run activity:
  - **No request/app logs**: `sapphire-aster`, `sapphire-lighter`
  - Active: all other listed services
- Edge runtime:
  - `rari1`: `lighter-trading`, `openclaw-agent`, `sapphire-research-web`
  - `rari2`: `lighter-trading`, `lighter-overnight-explorer`, `kimi-claw`, TV web worker, monitoring
- Code complexity hotspots:
  - `services/unified-frontend/app.py`: `6891` lines
  - `services/bot-lighter/src/main.py`: `6464` lines
  - `services/alpha-engine/src/main.py`: `3432` lines
  - `services/api-gateway/src/main.py`: `1902` lines
- Repo state:
  - Tracked files: `909`
  - Dirty tree: large active change surface (tracked + untracked)
  - Top-level markdown docs outside `docs/`: `20`

## Findings (Ranked)

### P0 - Architecture / Runtime
1. **Execution authority split is still too implicit**
- Cloud venue services (`sapphire-lighter`, `sapphire-aster`) are deployed but idle, while edge bots execute.
- This creates operator ambiguity and rollback risk during incidents.
- Impact: wrong-path debugging, accidental reactivation risk, policy drift.

2. **PnL truth layer remains incomplete**
- Production snapshot shows high trade counts while aggregated PnL fields remain `0`.
- Impact: cannot confidently optimize, promote, or size strategies by true net performance.

### P1 - Reliability / Maintainability
3. **Critical monolith files are oversized and multi-responsibility**
- `unified-frontend/app.py` and `bot-lighter/src/main.py` are effectively orchestration monoliths.
- Impact: regression risk, review difficulty, slow delivery, brittle on-call debugging.

4. **Legacy compatibility surface remains in hot paths**
- Deprecated alias routes and legacy-normalization logic are still active in runtime code.
- Impact: larger attack/test surface and slower deprecation completion.

5. **Control-plane overlap is under-consolidated**
- PM/ops, strategy, and execution decisions are spread across multiple services and edge agents.
- Impact: duplicated logic and inconsistent state interpretation.

### P2 - Governance / Documentation
6. **Documentation topology is fragmented**
- `docs/INDEX.md` and root `INDEX.md` had drift/staleness issues.
- High number of root status/handoff markdown files reduces source-of-truth clarity.

7. **Experiment lifecycle governance is present but not fully closed-loop**
- Promotion pipeline exists, but still needs strict economic attribution and demotion automation.
- Impact: strategies can linger without statistically strong evidence.

### P3 - Underutilization
8. **Tooling underuse**
- `tools/flowise` and `tools/shannon` exist but are not deeply integrated into operator loops.
- Opportunity: formalize these as bounded lanes (visual orchestration + pre-deploy security gates).

## Consolidation Blueprint (Target State)

### 1) Runtime Planes (explicit ownership)
- **Execution plane (authoritative):** `rari2` edge bots only.
- **Cloud control/data plane:** gateway, unified frontend/jobs, alpha/PM intelligence and policy.
- **Public plane:** read-only unified frontend only.

### 2) Service Rationalization
- Keep (core): `sapphire-unified-frontend`, `sapphire-unified-jobs`, `sapphire-gateway`, `sapphire-alpha`, `sapphire-scout-sandbox`, `agentic-pm-hub`.
- Keep (optional/business): `tho-agent`, `blanga-bis-beta`, `sapphire-telegram-bot` (if still used).
- Move to explicit standby profile:
  - `sapphire-lighter`, `sapphire-aster` (if edge is canonical execution).

### 3) Codebase Refactor Boundaries
- Split `unified-frontend/app.py` into:
  - `routes/platform_read.py`
  - `services/strategy_ops.py`
  - `services/librarian_context.py`
  - `jobs/internal_jobs.py`
  - `integrations/upstreams.py`
- Split `bot-lighter/src/main.py` into:
  - `execution/submitter.py`
  - `risk/go_nogo.py`
  - `policy/sizing.py`
  - `io/pubsub_adapter.py`
  - `notify/telegram_digest.py`

### 4) Data Contract Unification
- Create canonical outcome table/schema (single source for EV + PnL):
  - `signal_id`, `lane`, `symbol`, `entry/exit`, `fees`, `slippage`, `latency`, `reason_code`, `net_pnl_after_fees`.
- All dashboards, digests, and promotion gates should consume this only.

## Immediate Action Plan (Ordered)

### Phase 1 (48 hours) - Control and clarity
1. Publish an explicit **Execution Authority Policy**:
   - edge=`authoritative`, cloud venue services=`standby`.
2. Set standby labels/annotations on idle cloud venue services and remove from active runbooks.
3. Add one operator endpoint: `/api/platform/go-no-go-brief` (single decision + blockers + actions).

### Phase 2 (3-5 days) - Economic truth
1. Complete PnL attribution plumbing so production summary is non-zero and explainable.
2. Enforce fee/slippage-aware EV scoring as the only lane ranking output.
3. Add auto-demotion rules tied to reject-tax + EV error + drawdown.

### Phase 3 (1-2 weeks) - Refactor and debt burn-down
1. Begin modular split of `unified-frontend/app.py` and `bot-lighter/src/main.py`.
2. Remove deprecated alias routes after a fixed sunset window and migration log.
3. Archive stale root status docs into `docs/archive/` with one canonical status doc retained.

### Phase 4 (2-3 weeks) - World-class operating loop
1. Weekly scorecard -> promote/hold/block decisions generated automatically.
2. Security gate: Shannon run required on high-risk PRs (already scaffolded workflow).
3. Flowise lane for visual strategy review and operator postmortems.

## KPIs for “Pristine State”
- `fill_rate >= 85%` on allowed live lanes.
- `reject_tax <= 25%` rolling 24h.
- `net_pnl_after_fees` non-zero and attributable per lane.
- `expected_value_error <= 20%` on promoted lanes.
- Deprecated route usage: `0` after sunset.
- Monolith reduction:
  - `unified-frontend/app.py` < 3000 lines
  - `bot-lighter/src/main.py` < 3000 lines

## Risks if left as-is
- Continued split-brain between deployed-vs-active execution paths.
- Strategy selection based on incomplete economics.
- Slow incident response due to oversized runtime files and duplicated control logic.
- Public-facing credibility risk from stale or conflicting docs.

## Conclusion
The platform is operationally stable and increasingly disciplined, but not yet structurally streamlined. The highest-leverage next move is to finalize execution authority + economic truth, then burn down monolith and legacy surfaces with strict deprecation gates.
