# Sapphire Autonomy Master Plan

## Mission
Build a robust, profitable, 24/7 autonomous trading organization on GCP where `sapphire-alpha` controls only the active Sapphire venues (`ASTER`, `LIGHTER`) with deterministic risk controls and human override via Telegram.

## First-Principles Operating Model

Profitability comes from this equation:

`Net PnL = (edge per trade * trade count * capital efficiency) - (fees + slippage + infra cost + tail risk losses)`

Design implications:

1. Increase real edge, not just signal volume.
2. Protect downside with hard kill/deallocate controls.
3. Keep infrastructure simple and observable.
4. Automate routine operations, escalate only exceptions.

## Current Baseline (as of 2026-02-12)

- Cloud Run production services are active for `sapphire-alpha`, `sapphire-aster`, `sapphire-lighter`, and gateway services.
- Telegram control channel is live via `POST /telegram/webhook` on `sapphire-alpha`.
- Scheduler jobs already cover core health checks and periodic status events.
- Control scope is enforced through `ENABLED_VENUES=ASTER;LIGHTER`.

## Target Autonomous State

### Level A: Operational Autonomy (must-have)

- Continuous health verification (service + strategy + broker connectivity).
- Automatic heartbeat and status reporting to Telegram.
- Automatic deallocation and cooldown on repeated venue failures.
- Deterministic incident playbooks (`/kill`, `/resume`, `/deallocate`, `/allocate`).

### Level B: Trading Autonomy (must-have)

- Venue-specific execution with per-venue capital budgets.
- Loss limits and hard stop logic enforced in code, not manual memory.
- Execution verification and post-trade reconciliation.

### Level C: Learning Autonomy (should-have)

- Daily model/strategy recap with regime-shift checks.
- Weekly strategy ranking and allocation rebalance proposals.
- Promotion gates requiring paper-trade pass before live enablement.

## 30-Day Tactical Plan

### Week 1: Reliability Hardening

- Run daily readiness checks using scripts in this repo.
- Enforce secret completeness for control plane + venues.
- Validate scheduler and webhook continuity.
- Freeze deprecated surfaces and retired venue paths from production deploys.

### Week 2: Risk and Capital Controls

- Introduce explicit per-venue max exposure and per-signal size caps.
- Add daily max drawdown and max consecutive-loss auto-halt.
- Add incident drill automation (`kill -> verify -> resume`) in non-prod.

### Week 3: Signal Quality and Allocation

- Benchmark each strategy by net expectancy and drawdown-adjusted return.
- Shift allocation by live Sharpe proxy and execution quality.
- Keep low-confidence strategies in paper mode.

### Week 4: Autonomous Governance

- Automate weekly performance packet to Telegram.
- Automate config consistency checks (env vars, secrets, scheduler, endpoints).
- Add go/no-go checklist for every production rollout.

## KPIs and SLOs

Operational SLOs:

- Service uptime: `>= 99.5%` for alpha and active bots.
- Heartbeat freshness: every `<= 30 minutes`.
- MTTD for bot failure: `<= 10 minutes`.
- MTTR for restart/recovery: `<= 30 minutes`.

Trading KPIs:

- Positive 30-day expectancy per active venue.
- Daily max drawdown within configured loss budget.
- Fill quality vs expected slippage baseline.
- Infra cost as a percent of gross trading PnL.

## Governance Rules

- Production command path remains Telegram + webhook only.
- New signals are dry-run first; live execution requires explicit toggle.
- No additional repo control scope until Sapphire-only autonomy is stable for 30 consecutive days.
- Every automation must have a rollback path.

## Execution Backlog (Ordered)

1. Complete daily autonomy readiness checks and alert on failures.
2. Add hard risk limits in execution path (not just advisory logs).
3. Integrate TradingView workbench in dry-run mode, then promote to live after validation.
4. Add weekly strategy allocation recommender with audit trail.
5. Add monthly disaster-recovery simulation and incident postmortem template.
