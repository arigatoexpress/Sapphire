---
name: code-review
description: Sapphire-focused PR review for security, reliability, and cloud runtime safety
metadata: { "openclaw": { "emoji": "👁️", "requires": { "bins": ["gh"] }, "always": true } }
---

# Code Review (Sapphire Focus)

## Priority Review Areas
1. Auth/token handling (`hooks`, `gateway`, Telegram allowlists)
2. Cloud Run and scheduler reliability
3. Deployment script correctness and rollback safety
4. Domain mapping and DNS correctness for `sapphirealpha.xyz`

## Review Checklist
- Security: no secret leaks, no weakened auth boundaries
- Reliability: no regressions in verification/drill paths
- Operability: scripts remain idempotent and macOS-safe
- Scope: changes stay aligned with Sapphire-only focus

## Approve When
- Tests/scripts required for touched area pass.
- No high-severity security or runtime risks.
- Rollback path is clear for deploy-affecting changes.

## Request Changes When
- Scheduler or hook auth can fail silently.
- Deploy scripts deviate from repo source-of-truth workflow.
- Changes expand scope beyond Sapphire before current objectives are stable.
