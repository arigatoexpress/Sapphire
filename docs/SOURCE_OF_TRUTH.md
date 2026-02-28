# Sapphire Source Of Truth Policy

## Canonical production repository

- **Canonical repo:** `/Users/aribs/Sapphire`
- **Canonical GCP project:** `sapphire-479610`
- **Canonical production domain:** `https://sapphirealpha.xyz`

All production code changes, deployments, and release notes must originate from this repository.

## Mirrors and experimental clones

The following are treated as non-canonical unless explicitly promoted:

- `/Users/aribs/Documents/Organized/Codex Projects/github/Sapphire`
- `/Users/aribs/sapphire-dashboard`
- `/Users/aribs/sapphire-unified-frontend`
- `/Users/aribs/sapphire-trading-infra`

Policy:

1. No direct production deploys from non-canonical repositories.
2. If work is done in a mirror, port it into `/Users/aribs/Sapphire` before deployment.
3. Mark archived/experimental repos clearly and keep them out of daily release flow.

## Operational controls

1. Release check must include `pwd` verification before deploy scripts run.
2. Scheduler, IAM, and Cloud Run updates are logged in `docs/` runbooks in this repo.
3. Each production deploy references commit SHA from this repo.

## Immediate cutover tasks

- [x] Move unified frontend code into `services/unified-frontend/` in this repo.
- [x] Pause stale Cloud Scheduler jobs targeting missing services.
- [x] Update deployment scripts to enforce canonical repo path checks.
- [ ] Archive or label non-canonical repos as `experimental`.
- [ ] Add CI guard to block deploy workflow if repository path is non-canonical.
- [ ] Move remaining Cloud Run services off default compute runtime SA where feasible.
