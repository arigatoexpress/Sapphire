---
name: deploy
description: Sapphire cloud deployment operations for alpha and venue services (Cloud Run + Cloud DNS)
metadata: { "openclaw": { "emoji": "🚀", "requires": { "bins": ["gcloud"] }, "always": true } }
---

# Deploy (Sapphire Focus)

Use this skill only for Sapphire cloud services in project `sapphire-479610`.

## Scope
- Services:
  - `sapphire-alpha` (control plane)
  - `sapphire-aster` (venue bot)
  - `sapphire-lighter` (venue bot)
  - `sapphire-gateway` (OpenClaw runtime)
- Region: `us-central1`
- Registry: `northamerica-northeast1-docker.pkg.dev/sapphire-479610/sapphire-repo`
- Domain: `sapphirealpha.xyz`

## Standard Commands

### Gateway deploy
```bash
cd ~/Documents/Projects/AI\ Repo\ Manager/repos/Sapphire
./scripts/check_required_secrets.sh
./scripts/autonomy_readiness_check.sh
```

### Service verification
```bash
cd ~/Documents/Projects/AI\ Repo\ Manager/repos/Sapphire
gcloud run services list --project sapphire-479610 --platform managed
curl -sS https://sapphire-alpha-267358751314.us-central1.run.app/health
curl -sS https://sapphire-aster-267358751314.us-central1.run.app/health
curl -sS https://sapphire-lighter-267358751314.europe-west1.run.app/health
```

## Rollback
```bash
gcloud run revisions list --service sapphire-gateway --project sapphire-479610 --region us-central1
gcloud run services update-traffic sapphire-gateway --project sapphire-479610 --region us-central1 --to-revisions <previous-revision>=100
```

## Guardrails
1. Do not bypass verification scripts after deploy.
2. Keep deployment behavior script-driven; avoid ad-hoc command divergence.
3. For custom domain issues, sync DNS from domain mapping records and re-check cert state.
4. Preserve token-based control boundaries even when ingress must be invokable.
