# Sapphire: Agentic Navigation Guide

This repo is a multi-service monorepo (Cloud Run backends + web frontend + infra + OpenClaw skills).

## Start Here
- `INDEX.md` (stack map + common changes)
- `README.md` (scope lock + control channels)
- `docs/INDEX.md` (doc map)
- `OPERATIONS_RUNBOOK.md` (deploy/ops)

## Quick Commands
- Alpha engine deps: `python -m pip install -r services/alpha-engine/requirements.txt`
- Focused repo gate (CI mirror): `./scripts/ci_focused_gate.sh`
- Frontend dev: `cd sapphire-web && npm ci && npm run dev`

## Where Things Live
- Engine + Telegram/TradingView ingress: `services/alpha-engine/src/`
- Venue bots: `services/bot-aster/src/`, `services/bot-lighter/src/`
- Cloud Run services (each deployable): `services/*/src/` (+ service-local `requirements.txt`)
- Shared service code: `services/shared/`
- Web UI (Vite/Vue): `sapphire-web/`
- Infra: `terraform/`
- Operator scripts (deploy, wiring, verification): `scripts/`
- Standalone operator utilities: `tools/`
- OpenClaw skills (Sapphire-only): `skills/`
- Ops dashboard + `/sapphire` namespace: `arigatoexpress/sapphire-control` (separate repo)
- Archived historical assets (not on the active path): `archive/`

## Guardrails (Keep Agents Honest)
- Stay within the repo’s **Scope Lock** (ASTER/LIGHTER; control via Telegram).
- Prefer editing code on the active path; avoid `archive/` unless explicitly required.
- If you change execution, dispatch, or auth paths, add/extend tests in `tests/`.
- Never print secrets; treat env vars and GCP Secret Manager as the only secret sources.
