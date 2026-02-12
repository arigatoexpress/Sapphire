# Sapphire Operations Runbook

This runbook is for operating Sapphire in the current cloud setup with a strict scope on the `arigatoexpress/Sapphire` repository.

## Production Services

- `sapphire-alpha` (control plane): `https://sapphire-alpha-267358751314.us-central1.run.app`
- `sapphire-aster` (venue bot): `https://sapphire-aster-267358751314.us-central1.run.app`
- `sapphire-lighter` (venue bot): `https://sapphire-lighter-267358751314.europe-west1.run.app`
- `sapphire-gateway` (OpenClaw gateway): `https://sapphire-gateway-267358751314.us-central1.run.app`
- `sapphire-github-webhook-relay` (support)
- `sapphirebook-web` (support frontend)

## Active Control Scope

Current alpha deployment only routes commands to:

- `ASTER`
- `LIGHTER`

This is enforced by the `ENABLED_VENUES=ASTER;LIGHTER` environment variable in `sapphire-alpha`.

Gateway access policy:

- `sapphire-gateway` has Cloud Run invoker IAM check enabled.
- Unauthenticated requests are denied (`403`), reducing public prompt surface.
- GitHub workflow `OpenClaw Hook Forwarder` uses WIF + OIDC bearer auth for webhook delivery.
  - Required repo secrets: `OPENCLAW_HOOK_URL`, `OPENCLAW_HOOKS_TOKEN`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`
  - Optional override: `OPENCLAW_HOOK_AUDIENCE` (defaults to scheme+host from `OPENCLAW_HOOK_URL`)

## Telegram Control Channel

Inbound commands are handled in webhook mode by:

- `POST /telegram/webhook` on `sapphire-alpha`
- webhook secret header: `X-Telegram-Bot-Api-Secret-Token`

Supported operator commands in Telegram:

- `/status`
- `/heartbeat`
- `/focus`
- `/promotion`
- `/kill`
- `/resume`
- `/approve <session_key> [note]`
- `/approve_all [note]` (approve all pending autonomy sessions)
- `/reject <session_key> [reason]`
- `/deallocate <venue>`
- `/allocate <venue> <percent>`
- `/steer <directive>`
- `/answer <response>` (heartbeat reply alias to steering)
- `@alpha` / `@all` command forms for manual overrides
- `@alpha steer <directive>` for owner direction updates

Web policy:

- Public frontend surfaces are telemetry/research only.
- Do not expose direct agent prompt or command controls in the web UI.
- All operator steering and agent instructions must run through Telegram webhook auth.

## Frontend Surfaces

- `SapphireBook`: agent coordination forum surface
- `SapphireTrade`: ASTER/LIGHTER runtime and operations telemetry
- `Sapphire Alpha`: strategy intelligence + TradingView workbench surface

## TradingView Signal Ingress

TradingView alerts can be sent to:

- `POST /tradingview/webhook` on `sapphire-alpha`
- secret (recommended): `X-Sapphire-Webhook-Secret` header
  - accepted fallback keys in payload: `secret`, `passphrase`, `token`

Supported TradingView actions:

- `heartbeat`, `status` (control telemetry)
- `kill`, `resume`, `deallocate`, `allocate` (risk controls)
- `buy`, `sell`, `close` (trade intents)
- `tv_watchlist_add`, `tv_watchlist_remove`, `tv_watchlist_replace`
- `tv_chart_set`, `tv_indicator_add`, `tv_indicator_remove`
- `tv_strategy_add`, `tv_strategy_remove`
- `tv_script_add`, `tv_script_remove`
- `tv_scan_assets`, `tv_ta`, `tv_status`, `tv_custom`

Safety default:

- `TRADINGVIEW_EXECUTION_ENABLED=false` means alerts are notify-only (dry-run).
- set `TRADINGVIEW_EXECUTION_ENABLED=true` only after paper validation.

Risk controls for TradingView ingress (env-configured):

- `TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS` (default `300`)
- `TRADINGVIEW_IDEMPOTENCY_MAX_KEYS` (default `2000`)
- `TRADINGVIEW_ENFORCE_STRATEGY_RULES` (`true` requires strategy labels and rule matches)
- `TRADINGVIEW_STRATEGY_RULES_JSON` (strategy -> venues/symbols/max_quantity policy)
- `TRADINGVIEW_AUTONOMY_ENABLED` (`true` enables OpenClaw dispatch for workspace actions)
- `TRADINGVIEW_AUTONOMY_ALLOW_MUTATIONS` (allow watchlist/chart/indicator writes)
- `TRADINGVIEW_AUTONOMY_HOOK_URL` (`/hooks/agent` endpoint for gateway dispatch)
- `TRADINGVIEW_AUTONOMY_HOOK_TOKEN` (OpenClaw hook token; use Secret Manager)
- `TRADINGVIEW_AUTONOMY_AGENT_ID` (default `sapphire`)
- `TRADINGVIEW_ALLOW_ALL_ASSETS` (`true` enables full asset universe mode)
- `TRADINGVIEW_COMMUNITY_ACCESS_ENABLED` (`true` enables community script actions)
- `SAPPHIRE_ALLOWED_REPOS` (default `arigatoexpress/Sapphire;Sapphire`; hard scope for autonomy dispatch)
- `SAPPHIRE_ALLOWED_GCP_PROJECTS` (default `sapphire-479610`; hard project scope for autonomy dispatch)
- `SAPPHIRE_BLOCKED_SCOPE_TERMS` (default includes `sapphireai`; blocks deprecated scope mentions in autonomy dispatch)
- `TRADINGVIEW_MAX_QUANTITY` (global cap, optional)
- `TRADINGVIEW_MAX_QUANTITY_ASTER` / `TRADINGVIEW_MAX_QUANTITY_LIGHTER` (venue caps, optional)
- `TRADINGVIEW_ALLOWED_SYMBOLS` (global allowlist, optional)
- `TRADINGVIEW_ALLOWED_SYMBOLS_ASTER` / `TRADINGVIEW_ALLOWED_SYMBOLS_LIGHTER` (venue allowlists, optional)

## Cloud Scheduler Jobs

Focused jobs in `us-central1`:

- `sapphire-alpha-health-6h` -> alpha `/health` every 6 hours
- `sapphire-aster-health-6h` -> aster `/health` every 6 hours (5 min offset)
- `sapphire-lighter-health-6h` -> lighter `/health` every 6 hours (10 min offset)
- `sapphire-gateway-health-6h` -> gateway authenticated root check every 6 hours (OIDC)
- `sapphire-alpha-heartbeat-30m` -> sends synthetic `/heartbeat` through alpha webhook every 30 minutes
- `sapphire-alpha-status-daily` -> sends synthetic `/status` update through alpha webhook daily at `14:15 UTC`
- `sapphire-alpha-strategy-gate-daily` -> sends `/promotion` through alpha webhook daily at `14:45 UTC`
- `sapphire-heartbeat-30m` -> Sapphire agent heartbeat via alpha `/tradingview/webhook`
- `obsidian-heartbeat-30m` -> Obsidian agent heartbeat via alpha `/tradingview/webhook`
- `emerald-heartbeat-30m` -> Emerald agent heartbeat via alpha `/tradingview/webhook`
- `sapphire-dep-audit-daily` -> daily dependency audit via alpha `/tradingview/webhook`
- `sapphire-security-scan-weekly` -> weekly security scan via alpha `/tradingview/webhook`

Idempotent job setup script:

```bash
./scripts/setup_scheduler_jobs.sh
./scripts/setup_clawdbot_jobs.sh
```

Scheduler auth model:

- `sapphire-aster-health-6h`, `sapphire-lighter-health-6h`, and `sapphire-gateway-health-6h` use OIDC tokens from `sapphire-main-sa@sapphire-479610.iam.gserviceaccount.com`.
- OpenClaw employee jobs (`sapphire-heartbeat-30m`, `obsidian-heartbeat-30m`, `emerald-heartbeat-30m`, `sapphire-dep-audit-daily`, `sapphire-security-scan-weekly`) route through `sapphire-alpha` `/tradingview/webhook` with `X-Sapphire-Webhook-Secret`, then dispatch to gateway.
- `sapphire-aster` and `sapphire-lighter` are authenticated-only Cloud Run services (`roles/run.invoker` limited to `sapphire-main-sa`).

Scope reconciliation (dry-run then apply):

```bash
./scripts/gcp_scope_reconcile.sh
./scripts/gcp_scope_reconcile.sh --strict
./scripts/gcp_scope_reconcile.sh --apply
./scripts/gcp_scope_reconcile.sh --apply --delete-services --strict
```

## Secret Readiness Check

Run:

```bash
./scripts/check_required_secrets.sh
./scripts/enable_full_autonomy.sh
./scripts/autonomy_readiness_check.sh
./scripts/frontend_contract_check.sh
./scripts/focus_guard.sh
./scripts/verify_focused_stack.sh
./scripts/holistic_ops_check.sh
```

## Web Frontend Deploy

Deploy the SapphireBook/SapphireTrade/Sapphire Alpha frontend to Cloud Run:

```bash
./scripts/deploy_sapphirebook_web.sh
```

This builds `sapphire-web` for `linux/amd64`, pushes to Artifact Registry, and deploys `sapphirebook-web`.

## Alpha Control Plane Deploy

Deploy Telegram/control-plane updates for `sapphire-alpha`:

```bash
./scripts/deploy_sapphire_alpha.sh
```

Full-autonomy env controls are applied by deploy defaults:

- `SAPPHIRE_FULL_AUTONOMY_ENABLED=true`
- `SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES=true`
- `SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES=true`
- `SAPPHIRE_AUTONOMY_DRY_RUN=false`
- `SAPPHIRE_AUTONOMY_REQUIRE_OWNER_APPROVAL=false` (auto-approve autonomy sessions)
- `SAPPHIRE_AUTONOMY_LOOP_SECONDS=900`

Execution safety controls:

- `TRADINGVIEW_EXECUTION_ENABLED=true` enables strategy/webhook trade dispatch (guarded by strategy + symbol + quantity limits).
- `INTERNAL_ARB_EXECUTION_ENABLED=false` keeps internal spread loop in observe-only mode unless explicitly enabled.

Expected result for current scope:

- `CONTROL_PLANE` ready
- `ASTER` ready
- `LIGHTER` ready

## Incident Commands

Immediate safety actions:

1. `/kill` in Telegram to halt and deallocate all enabled venues.
2. Verify:
   - `GET /health` for `sapphire-alpha`
   - run authenticated scheduler probes for `sapphire-aster-health-6h` and `sapphire-lighter-health-6h`
   - latest Cloud Run revision status is `Ready=True`
3. Resume only after issue triage:
   - `/resume`
   - optionally `/allocate <venue> <percent>`

## Quick Verification Commands

```bash
gcloud run services list --project sapphire-479610 --platform managed
gcloud scheduler jobs list --project sapphire-479610 --location us-central1
curl -sS https://sapphire-alpha-267358751314.us-central1.run.app/health
gcloud scheduler jobs run sapphire-aster-health-6h --project sapphire-479610 --location us-central1
gcloud scheduler jobs run sapphire-lighter-health-6h --project sapphire-479610 --location us-central1
./scripts/focus_guard.sh
```
