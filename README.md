# Sapphire

Autonomous trading organization and control plane for `arigatoexpress/Sapphire`.

## Mission
Run a focused, 24/7 trading operation that maximizes risk-adjusted return while preserving hard downside controls.

Profit model:

`Net PnL = (edge * trades * capital efficiency) - (fees + slippage + infra cost + tail losses)`

## Scope Lock
- Single codebase: `arigatoexpress/Sapphire`
- Active venues: `ASTER`, `LIGHTER`
- Active control services: `sapphire-alpha`, `sapphire-aster`, `sapphire-lighter`, `sapphire-gateway`
- Human governance path: Telegram heartbeat + command webhook

## Organization (Employees)
- `SAPPHIRE`: Security and code quality lead
- `OBSIDIAN`: CI/CD and deployment operations
- `EMERALD`: Continuous improvement and strategy governance

All three agents operate through OpenClaw with Sapphire-only skills in:
- `skills/security-audit`
- `skills/ci-cd`
- `skills/deploy`
- `skills/self-improve`
- `skills/code-review`
- `skills/dep-update`
- `skills/git-ops`

## Control Channels
- Telegram command ingress: `POST /telegram/webhook` on `sapphire-alpha`
- TradingView signal ingress: `POST /tradingview/webhook` on `sapphire-alpha`
- OpenClaw gateway control: `sapphire-gateway` (Cloud Run invoker IAM check enabled)

## Frontend Surfaces
- `SapphireBook`: internal agent forum feed
- `SapphireTrade`: ASTER/LIGHTER operations telemetry
- `Sapphire Alpha`: market-intelligence + TradingView workbench

Web UI is read-only for control actions. Agent prompting, approvals, and steering stay on the authenticated Telegram heartbeat channel.

## Daily Operating Commands
```bash
./scripts/check_required_secrets.sh
./scripts/autonomy_readiness_check.sh
./scripts/focus_guard.sh
./scripts/gcp_scope_reconcile.sh
./scripts/setup_clawdbot_jobs.sh
./scripts/verify_focused_stack.sh
```

## Authoritative Operating Docs
- `OPERATIONS_RUNBOOK.md`
- `MASTERPLAN.md`
- `LEARNINGS.md`
- `docs/SAPPHIRE_AUTONOMY_MASTER_PLAN.md`
- `docs/SAPPHIRE_ORGANIZATION.md`
- `docs/TRADINGVIEW_QUANT_WORKBENCH.md`

## Current Objective
Keep Sapphire fully autonomous, operationally tight, and explicitly aligned to the masterplan before expanding scope.
