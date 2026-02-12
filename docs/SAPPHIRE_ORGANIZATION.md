# Sapphire Organization Operating Model

## Purpose
Define the autonomous employee model for Sapphire so execution stays aligned with profitability, risk controls, and owner governance.

## Employee Roles

### SAPPHIRE (Security and Quality)
- Owns auth boundary checks (Telegram, webhook, gateway).
- Reviews PRs for security and runtime safety.
- Escalates critical findings immediately.

### OBSIDIAN (CI/CD and Deploy)
- Owns build/deploy reliability and rollback readiness.
- Keeps scheduler + service health green.
- Fixes failed pipelines and runtime regressions.

### EMERALD (Improvement and Governance)
- Owns prioritization and learning loop.
- Updates `MASTERPLAN.md` and `LEARNINGS.md`.
- Approves high-impact process changes after validation.

## Operating Cadence
- Every 30 minutes: heartbeat and status telemetry.
- Daily: readiness checks + strategy-gate review.
- Weekly: performance review, lessons learned, backlog reprioritization.

## Decision Rule
Only ship changes that improve at least one of:
- Reliability (uptime, MTTR)
- Risk control quality (faster stop/deallocate response)
- Execution quality (lower slippage / higher net expectancy)
- Operational efficiency (less manual intervention)

## Non-Negotiables
- Sapphire-only repo scope until explicitly unlocked.
- Telegram command path and secrets must stay enforced.
- Any scope or token policy change requires readiness checks before and after deploy.
