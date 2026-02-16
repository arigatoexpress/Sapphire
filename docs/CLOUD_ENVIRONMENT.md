# Cloud Environment (Production)

This is the human/agent map of the live deployment for GCP project `sapphire-479610`.

## Regions

- Primary: `us-central1`
- Secondary: `europe-west1` (Lighter venue bot)

## Cloud Run Services

`us-central1`:

- `sapphire-alpha`: public ingress; Telegram/TradingView webhook + API surface (source: `services/alpha-engine/`)
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

Core secrets used by the active stack include:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- `SAPPHIRE_CONTROL_API_TOKEN`
- `OPENCLAW_GATEWAY_TOKEN`
- `ANTHROPIC_API_KEY`

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
