---
name: ci-cd
description: Sapphire CI/CD monitoring and remediation for arigatoexpress/Sapphire
metadata: { "openclaw": { "emoji": "⚙️", "requires": { "bins": ["gh"] }, "always": true } }
---

# CI/CD (Sapphire Focus)

## Scope
- `arigatoexpress/Sapphire`

## Workflow
1. Check latest runs.
```bash
gh run list --repo arigatoexpress/Sapphire --limit 10
```
2. Inspect failures.
```bash
gh run view <run-id> --repo arigatoexpress/Sapphire --log-failed
```
3. Create targeted fix branch and PR.
4. Re-run workflows after merge.

## Failure Priorities
1. Deploy/runtime failures in `Sapphire`
2. Security-test and build failures in `Sapphire`
3. Non-critical lint/style failures

## Guardrails
- Keep fix PRs small and single-cause.
- If two fix attempts fail, escalate via Telegram heartbeat prompt.
- Always record root cause in commit/PR body.
