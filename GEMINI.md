# Sapphire Gemini CLI Context

Gemini CLI is an auxiliary reviewer for Sapphire OS. Codex remains the primary
operator and Sapphire remains the command authority.

## Operating Rules

- Read `AGENTS.md` first and follow its safety boundaries.
- Treat all production-adjacent changes as PR work in a branch or worktree.
- Do not expose, request, summarize, or copy secret values.
- Do not enable real trading, money movement, Telegram sends, Gmail/Drive
  mutation, GCS/BigQuery writes, Foundry writes, workflow dispatches, billing
  changes, credit redemptions, API enablement, or LaunchAgent retargeting.
- Prefer read-only inventory, local dry-run artifacts, tests, and docs.
- Keep Google services as complements for analysis, evals, storage, and batch
  work; do not replace Sapphire's control tower.

## Useful Entry Points

```bash
python3 scripts/ops/google_production_test_readiness.py --no-external
python3 scripts/ops/google_benefits_inventory.py --no-external
python3 scripts/ops/gcp_ai_inventory.py --no-external
python3 scripts/ops/google_workspace_threat_hygiene.py --days 30
python3 scripts/ops/org_status.py --no-external --markdown
```

Use live read-only variants only when the operator explicitly wants current
local CLI/GCP metadata. Any write or paid model call needs a narrow live gate.
