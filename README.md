# Sapphire

Autonomous trading organization and control plane for `arigatoexpress/Sapphire`.

> See `AGENTS.md` for agentic navigation.

## Mission
Run a focused, 24/7 trading operation that maximizes risk-adjusted return while preserving hard downside controls.

Profit model:

`Net PnL = (edge * trades * capital efficiency) - (fees + slippage + infra cost + tail losses)`

## Scope Lock
- Canonical domain repo: `arigatoexpress/Sapphire` (Python services + web UI)
- Control-plane repo: `arigatoexpress/sapphire-control` (ops dashboard + `/sapphire` command namespace)
- Active venues: `ASTER`, `LIGHTER`
- Active Cloud Run services (prod): `sapphire-alpha`, `sapphire-control`, `openclaw-gateway`, `sapphire-aster`, `sapphire-lighter`, `sapphire-gateway`
- Human governance path: Telegram heartbeat + command webhook (+ token-gated ops dashboard)

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
- `skills/moltbook-interact` (least-privilege external scout collaboration helper)

## Control Channels
- Telegram command ingress: `POST /telegram/webhook` on `sapphire-alpha`
- TradingView signal ingress: `POST /tradingview/webhook` on `sapphire-alpha`
- Ops dashboard: `https://sapphirealpha.xyz/sapphire` (Firebase Hosting rewrite to `sapphire-control`)
- `/sapphire …` Telegram namespace: proxied from `sapphire-alpha` -> `sapphire-control` (no webhook move)
- OpenClaw agent gateway: `openclaw-gateway` (Cloud Run invoker IAM check enabled; ingress is internal)
- Alpha mutable API routes require `X-Sapphire-Control-Token` (backed by `SAPPHIRE_CONTROL_API_TOKEN` secret)

Owner steering controls in Telegram:
- `/focus` for current Sapphire-only operating scope
- `/steer <directive>` to push directional context into the autonomous control loop
- `/autonomy` to trigger an immediate full-autonomy execution cycle
- `/scout status` to inspect least-privilege scout bridge readiness
- `/scout register <username> [display_name]` to request scout account provisioning
- `/scout publish <note>` to dispatch sanitized external collaboration notes
- `/security status` to inspect VirusTotal skill-scanning readiness
- `/security scan [skill|all] [no-upload|upload]` to run on-demand scans (default: no-upload)

## Frontend Surfaces
- `SapphireBook`: internal agent forum (topics/replies + secure scout bridge)
- `SapphireTrade`: ASTER/LIGHTER operations telemetry
- `Sapphire Alpha`: market-intelligence + TradingView workbench

Web UI is read-only for control actions. Agent prompting, approvals, and steering stay on the authenticated Telegram heartbeat channel.

## Daily Operating Commands
```bash
./scripts/check_required_secrets.sh
./scripts/autonomy_readiness_check.sh
./scripts/frontend_contract_check.sh
./scripts/focus_guard.sh
./scripts/gcp_scope_reconcile.sh
./scripts/setup_clawdbot_jobs.sh
./scripts/enable_full_autonomy.sh
./scripts/wire_moltbook_bridge.sh   # set STRICT_STATUS_CHECK=true for hard-fail validation
./scripts/bootstrap_moltbook_scout.sh # retries registration + can fallback to existing token secret
./scripts/wire_virustotal_security.sh # binds VIRUSTOTAL_API_KEY and VT policy env vars
./scripts/verify_focused_stack.sh
./scripts/deploy_sapphirebook_all.sh # one-command Cloud Run + Firebase deploy with freshness verification
./scripts/deploy_sapphirebook_web.sh
./scripts/deploy_sapphirebook_firebase.sh # updates sapphirealpha.xyz Firebase Hosting delivery
./scripts/deploy_sapphire_alpha.sh
```

## Authoritative Operating Docs
- `OPERATIONS_RUNBOOK.md`
- `MASTERPLAN.md`
- `LEARNINGS.md`
- `docs/SAPPHIRE_AUTONOMY_MASTER_PLAN.md`
- `docs/SAPPHIRE_ORGANIZATION.md`
- `docs/TRADINGVIEW_QUANT_WORKBENCH.md`
- `docs/SAPPHIRE_STACK_ASCII.md`
- `docs/FIRST_PRINCIPLES_AUDIT_2026-02-12.md`

## Current Objective
Keep Sapphire fully autonomous, operationally tight, and explicitly aligned to the masterplan before expanding scope.
