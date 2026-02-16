# Contributing to Sapphire

This repository is an ops-focused monorepo for Sapphire's Cloud Run services, Firebase-hosted web UI, and OpenClaw skills.

## Start Here

- `AGENTS.md` (fast navigation)
- `README.md` (scope lock + control channels)
- `docs/INDEX.md` (doc map)
- `OPERATIONS_RUNBOOK.md` (deploy/ops)

## Active Paths (What We Actually Run)

- Alpha engine (Telegram + TradingView ingress): `services/alpha-engine/`
- Venue bots: `services/bot-aster/`, `services/bot-lighter/`
- Web UI (Vite/Vue; Firebase Hosting): `sapphire-web/`
- OpenClaw skills (used by `openclaw-gateway`): `skills/`

Note: the `/sapphire` ops dashboard is served by `arigatoexpress/sapphire-control` (separate repo).

## Local Checks

Run the same focused gate that CI runs:

```bash
./scripts/ci_focused_gate.sh
```

Frontend dev loop:

```bash
cd sapphire-web
npm ci
npm run dev
```

## Pull Requests

- Keep changes small and scoped to the active paths above.
- If you change auth/dispatch/control flows, add or extend tests under `tests/unit/`.
- Do not commit secrets. Production secrets live in GCP Secret Manager.

