---
name: git-ops
description: Git operations for Sapphire-focused repos and controlled release flow
metadata: { "openclaw": { "emoji": "🔀", "requires": { "bins": ["git", "gh"] }, "always": true } }
---

# Git Ops (Sapphire Focus)

## Active Repo Set
- `Sapphire` (`arigatoexpress/Sapphire`) — only active repo during scope lock

## Branching
- Branch format: `{agent-id}/{purpose}`
- Default branches:
  - `Sapphire`: `main`

## Commit Policy
- Prefixes: `feat:`, `fix:`, `chore:`, `security:`
- Always include trailer:
```text
Co-Authored-By: <agent-name> @ Sapphire Inc <sapphire@kadima.digital>
```

## PR Policy
- Explain cloud/runtime impact and rollback path.
- Link validation evidence (runtime/autonomy/drill output where applicable).
- Prefer squash merge.

## Guardrails
- No force push to default branches.
- Keep all changes scoped to `arigatoexpress/Sapphire` until scope lock is lifted.
