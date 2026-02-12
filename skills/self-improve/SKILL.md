---
name: self-improve
description: Continuous improvement for Sapphire-only cloud operations and agent effectiveness
metadata: { "openclaw": { "emoji": "🧠", "requires": { "bins": ["git"] }, "always": true } }
---

# Self-Improve (Sapphire Focus)

## Mission
Continuously improve Sapphire reliability, owner control quality, and deployment efficiency.

## Inputs
- `./scripts/check_required_secrets.sh`
- `./scripts/autonomy_readiness_check.sh`
- `OPERATIONS_RUNBOOK.md`
- `docs/SAPPHIRE_AUTONOMY_MASTER_PLAN.md`
- Cloud Run + Scheduler logs
- Telegram operational feedback

## Improvement Loop
1. Detect recurring failures, slow paths, and manual interventions.
2. Update `LEARNINGS.md` with concrete cause/fix notes.
3. Update `MASTERPLAN.md` priorities and measurable outcomes.
4. Refine SKILL files to remove stale or non-Sapphire guidance.
5. Ship changes with verification evidence.

## Weekly Report
Include:
- Runtime uptime and latest revision health
- Scheduler success/error counts
- Deploy frequency and rollback incidents
- Top 3 improvements delivered
- Top 3 blockers for next week

## Guardrails
- Favor incremental, high-ROI changes.
- Do not expand to wider multi-repo scope until Sapphire goals are stable.
- Keep documentation operational, not aspirational.
