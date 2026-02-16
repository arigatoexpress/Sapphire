# Cloud Environment (Production)

This is the human/agent map of the live deployment for GCP project `sapphire-479610`.

## Regions

- Primary: `us-central1`
- Secondary: `europe-west1` (Lighter venue bot)

## Cloud Run Services

`us-central1`:

- `sapphire-alpha`: public ingress; Telegram webhook + API surface (source: `services/alpha-engine/`)
  - note: TradingView webhook ingress is currently disabled (no `/tradingview/webhook` route deployed)
- `sapphire-control`: public ingress; ops dashboard + `/sapphire` namespace (source: `arigatoexpress/sapphire-control`)
- `openclaw-gateway`: internal ingress; AI agent gateway (separate deployment)
- `sapphire-aster`: public ingress; Cloud Run invoker IAM restricted (source: `services/bot-aster/`)
- `sapphire-gateway`: public ingress; Cloud Run invoker IAM restricted (source: `services/api-gateway/`)
- `sapphire-github-webhook-relay`: public ingress; Cloud Run invoker IAM restricted (source: `services/api-gateway/`)
- `sapphirebook-web`: internal ingress; currently not on the primary path

`europe-west1`:

- `sapphire-lighter`: public ingress; Cloud Run invoker IAM restricted (source: `services/bot-lighter/`)

## Firebase Hosting

- `https://sapphirealpha.xyz` serves `sapphire-web/` (static Vite build)
- `/sapphire/**` is rewritten to Cloud Run service `sapphire-control` (dashboard + API)

## Secrets (GCP Secret Manager)

Do not store plaintext secrets in Cloud Run env vars or git.

Core secrets used by the active stack (see `./scripts/check_required_secrets.sh`):

CONTROL_PLANE:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SAPPHIRE_TELEGRAM_WEBHOOK_SECRET`
- `SAPPHIRE_CONTROL_API_TOKEN`
- `OPENCLAW_GATEWAY_TOKEN`

VENUES:

- `ASTER_API_KEY`
- `ASTER_SECRET_KEY`
- `LIGHTER_API_KEY_0`
- `LIGHTER_API_PUBLIC_KEY_0`

Optional (enables extra integrations, fallback still works when absent):

- `SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL`
- `SAPPHIRE_SCOUT_EXTERNAL_POST_URL`
- `SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN`
- `VIRUSTOTAL_API_KEY`

TradingView (disabled path):

- `TRADINGVIEW_WEBHOOK_SECRET` (only required if re-enabling `/tradingview/webhook`)

Note: Cloud Run environment variable names do not always match Secret Manager secret IDs.
Example: `sapphire-alpha` reads `TELEGRAM_WEBHOOK_SECRET` from an env var, which is typically bound
to the Secret Manager entry `SAPPHIRE_TELEGRAM_WEBHOOK_SECRET`.

## Source-Of-Truth Commands

List Cloud Run services:

```bash
gcloud run services list --region us-central1 --project sapphire-479610 \
  --format='table(metadata.name,metadata.annotations["run.googleapis.com/ingress"],status.url)'
```

Show invoker IAM for a service:

```bash
gcloud run services get-iam-policy sapphire-alpha --region us-central1 --project sapphire-479610
```

List Cloud Scheduler jobs:

```bash
gcloud scheduler jobs list --location us-central1 --project sapphire-479610
```

## Infra-as-Code Status

`terraform/` exists, but the live environment may include manual changes. Treat Terraform as reference unless/until it is actively applied and kept in sync.
