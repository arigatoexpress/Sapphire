---
name: security-audit
description: Sapphire security audit and remediation for runtime, hooks, scheduler, and repo hygiene
metadata: { "openclaw": { "emoji": "🛡️", "requires": { "bins": ["git", "gh"] }, "always": true } }
---

# Security Audit (Sapphire Focus)

## Scope
- `Sapphire` (`arigatoexpress/Sapphire`) only
- Cloud ingress, hooks, scheduler, secrets, and deployment config

## Audit Steps
1. Secret and config hygiene.
```bash
git -C {repo_path} grep -rn --no-color -E '(ghp_[A-Za-z0-9]{36}|AIza[0-9A-Za-z\-_]{20,}|-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----)' -- ':!*.md' ':!*.lock'
```
2. Verify hook and gateway auth boundaries in config.
3. Verify scheduler latest run statuses are healthy.
4. Verify deploy scripts keep security-critical defaults intentional.

## Required Checks
- No raw secrets committed.
- Hook endpoints require valid hook token.
- Telegram allowlists are present and explicit.
- Runtime checks (`verify-autonomy`) show no scheduler permission failures.

## Guardrails
- Treat auth regressions as HIGH severity.
- Any token/channel policy change requires follow-up readiness check (`autonomy_readiness_check.sh`).
