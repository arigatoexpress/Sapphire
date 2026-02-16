# Frontend Delivery Audit (2026-02-12)

Note (2026-02-16):
- `https://sapphirealpha.xyz/sapphire` now rewrites to Cloud Run service `sapphire-control` (ops dashboard).
- `sapphirebook-web` is internal-ingress and treated as an optional preview surface; Firebase Hosting is the primary operator URL.

## Objective
Explain why the frontend appeared unchanged/deprecated and define a deterministic fix.

## Findings
1. Dual delivery paths are active:
- Cloud Run service: `sapphirebook-web` (`https://sapphirebook-web-s77j6bxyra-uc.a.run.app`)
- Custom domain: `https://sapphirealpha.xyz` served by Firebase Hosting/CDN

2. The two paths served different frontend bundles during verification:
- Cloud Run index asset: `index-BSV9-Ku4.js`
- Domain index asset: `index-CQHZAQdK.js`

3. Resulting symptom:
- Deploying only Cloud Run updates `run.app` but leaves `sapphirealpha.xyz` stale.
- This creates the exact “frontend looks unchanged” behavior.

## Root Cause
Operational split-brain in frontend deployment workflow: Cloud Run deploy existed, but no standard Firebase Hosting deploy step for the production domain.

## Implemented Fixes
1. Added unified domain deploy script:
- `scripts/deploy_sapphirebook_firebase.sh`
- Builds `sapphire-web` with build stamps and deploys Firebase Hosting.

2. Documented dual-path deployment requirement in:
- `OPERATIONS_RUNBOOK.md`
- `README.md`

3. Upgraded SapphireBook UI to a live operations overview:
- Architecture pulse panel
- Real-time venue telemetry cards with mini sparklines
- KPI strip (uptime, PnL, win rate, autonomy counters)
- Live event stream from alpha system logs
- Existing collaboration forum retained

## Operational Standard Going Forward
When shipping frontend updates, run both:
1. `./scripts/deploy_sapphirebook_web.sh`
2. `./scripts/deploy_sapphirebook_firebase.sh`

Then verify both endpoints return the same current asset fingerprint.
