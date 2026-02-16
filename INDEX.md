# Sapphire Index

Fast map of the active code paths and the deployed cloud stack.

## Start Here

- `README.md`
- `AGENTS.md`
- `docs/INDEX.md`
- `OPERATIONS_RUNBOOK.md`

## Deployed Stack (Production)

Cloud Run services (GCP project `sapphire-479610`):

- `sapphire-alpha`: engine + Telegram/TradingView webhooks + API (this repo: `services/alpha-engine/`)
- `sapphire-aster`: venue bot (this repo: `services/bot-aster/`)
- `sapphire-lighter`: venue bot (this repo: `services/bot-lighter/`)
- `sapphire-gateway`: GitHub webhook receiver (this repo: `services/api-gateway/`)
- `sapphire-github-webhook-relay`: GitHub webhook relay (this repo: `services/api-gateway/`)
- `openclaw-gateway`: AI agent gateway (separate deployment; internal ingress)
- `sapphire-control`: ops control plane + `/sapphire` dashboard (repo: `arigatoexpress/sapphire-control`)

Firebase Hosting:

- `https://sapphirealpha.xyz` serves `sapphire-web/`
- `https://sapphirealpha.xyz/sapphire` rewrites to Cloud Run `sapphire-control`

## Common Changes

- Telegram command routing: `services/alpha-engine/src/telegram_handlers.py`
- Webhook auth + proxy wedge: `services/alpha-engine/shared/health.py`
- Alpha control/status API handlers: `services/alpha-engine/src/api_handlers.py`
- Web UI build + hosting config: `sapphire-web/`
- Ops dashboard implementation: `arigatoexpress/sapphire-control` (see `extensions/sapphire-control/index.ts`)

## Local Checks

```bash
./scripts/ci_focused_gate.sh
```

