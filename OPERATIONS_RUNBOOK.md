# Sapphire Operations Runbook

This runbook is for operating Sapphire in the current cloud setup with a strict scope on the `arigatoexpress/Sapphire` repository.

## Production Services

- `sapphire-alpha` (control plane): `https://sapphire-alpha-267358751314.us-central1.run.app`
- `sapphire-aster` (venue bot): `https://sapphire-aster-267358751314.us-central1.run.app`
- `sapphire-lighter` (venue bot): `https://sapphire-lighter-267358751314.europe-west1.run.app`
- `sapphire-gateway` (OpenClaw gateway): `https://sapphire-gateway-267358751314.us-central1.run.app`

## Active Control Scope

Current alpha deployment only routes commands to:

- `ASTER`
- `LIGHTER`

This is enforced by the `ENABLED_VENUES=ASTER;LIGHTER` environment variable in `sapphire-alpha`.

## Telegram Control Channel

Inbound commands are handled in webhook mode by:

- `POST /telegram/webhook` on `sapphire-alpha`
- webhook secret header: `X-Telegram-Bot-Api-Secret-Token`

Supported operator commands in Telegram:

- `/status`
- `/heartbeat`
- `/promotion`
- `/kill`
- `/resume`
- `/deallocate <venue>`
- `/allocate <venue> <percent>`
- `@alpha` / `@all` command forms for manual overrides

## TradingView Signal Ingress

TradingView alerts can be sent to:

- `POST /tradingview/webhook` on `sapphire-alpha`
- secret (recommended): `X-Sapphire-Webhook-Secret` header
  - accepted fallback keys in payload: `secret`, `passphrase`, `token`

Supported TradingView actions:

- `heartbeat`, `status` (control telemetry)
- `kill`, `resume`, `deallocate`, `allocate` (risk controls)
- `buy`, `sell`, `close` (trade intents)

Safety default:

- `TRADINGVIEW_EXECUTION_ENABLED=false` means alerts are notify-only (dry-run).
- set `TRADINGVIEW_EXECUTION_ENABLED=true` only after paper validation.

Risk controls for TradingView ingress (env-configured):

- `TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS` (default `300`)
- `TRADINGVIEW_IDEMPOTENCY_MAX_KEYS` (default `2000`)
- `TRADINGVIEW_ENFORCE_STRATEGY_RULES` (`true` requires strategy labels and rule matches)
- `TRADINGVIEW_STRATEGY_RULES_JSON` (strategy -> venues/symbols/max_quantity policy)
- `TRADINGVIEW_MAX_QUANTITY` (global cap, optional)
- `TRADINGVIEW_MAX_QUANTITY_ASTER` / `TRADINGVIEW_MAX_QUANTITY_LIGHTER` (venue caps, optional)
- `TRADINGVIEW_ALLOWED_SYMBOLS` (global allowlist, optional)
- `TRADINGVIEW_ALLOWED_SYMBOLS_ASTER` / `TRADINGVIEW_ALLOWED_SYMBOLS_LIGHTER` (venue allowlists, optional)

## Cloud Scheduler Jobs

Health and status jobs are configured in `us-central1`:

- `sapphire-alpha-health-6h` -> alpha `/health` every 6 hours
- `sapphire-aster-health-6h` -> aster `/health` every 6 hours (5 min offset)
- `sapphire-lighter-health-6h` -> lighter `/health` every 6 hours (10 min offset)
- `sapphire-alpha-heartbeat-30m` -> sends synthetic `/heartbeat` through alpha webhook every 30 minutes
- `sapphire-alpha-status-daily` -> sends synthetic `/status` update through alpha webhook daily at `14:15 UTC`
- `sapphire-alpha-strategy-gate-daily` -> sends `/promotion` through alpha webhook daily at `14:45 UTC`

Idempotent job setup script:

```bash
./scripts/setup_scheduler_jobs.sh
```

## Secret Readiness Check

Run:

```bash
./scripts/check_required_secrets.sh
./scripts/autonomy_readiness_check.sh
```

Expected result for current scope:

- `CONTROL_PLANE` ready
- `ASTER` ready
- `LIGHTER` ready

## Incident Commands

Immediate safety actions:

1. `/kill` in Telegram to halt and deallocate all enabled venues.
2. Verify:
   - `GET /health` for `sapphire-alpha`, `sapphire-aster`, `sapphire-lighter`
   - latest Cloud Run revision status is `Ready=True`
3. Resume only after issue triage:
   - `/resume`
   - optionally `/allocate <venue> <percent>`

## Quick Verification Commands

```bash
gcloud run services list --project sapphire-479610 --platform managed
curl -sS https://sapphire-alpha-267358751314.us-central1.run.app/health
curl -sS https://sapphire-aster-267358751314.us-central1.run.app/health
curl -sS https://sapphire-lighter-267358751314.europe-west1.run.app/health
```
