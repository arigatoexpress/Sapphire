---
name: dep-update
description: Dependency updates with Sapphire-first risk controls
metadata: { "openclaw": { "emoji": "📦", "requires": { "bins": ["gh"] }, "always": true } }
---

# Dependency Updates (Sapphire Focus)

## Scope
- `Sapphire` (`arigatoexpress/Sapphire`) only

## Process
1. Identify outdated and vulnerable packages.
2. Apply smallest safe version bump.
3. Run relevant tests and operational scripts.
4. Create focused PR per dependency group.

## Required Validation
- `Sapphire` dependency updates affecting runtime must preserve:
  - `./scripts/check_required_secrets.sh`
  - `./scripts/autonomy_readiness_check.sh`
  - `OPERATIONS_RUNBOOK.md` command-path assumptions

## Guardrails
- Avoid multi-major upgrades in one PR.
- Do not auto-merge if auth, deploy, scheduler, or hooks behavior changes.
- Capture incompatibilities in `LEARNINGS.md`.
