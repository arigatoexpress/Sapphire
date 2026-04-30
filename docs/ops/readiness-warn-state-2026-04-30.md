# Production Readiness Sweep — WARN State Audit (2026-04-30)

This is a one-shot audit of the WARN rows that
`scripts/ops/production_readiness_sweep.py` currently emits, classifying each
as **A) by-design / time-locked**, **B) stale config**, or **C) real failure**.

The goal is to make every WARN explicit so future operators do not re-run the
same investigation each cycle.

## Method

1. Ran the sweep on a clean main checkout (pre-audit).
2. Extracted all rows with `WARN` status.
3. For each, traced the origin (probe function + decision logic) and confirmed
   whether the WARN is intentional, stale, or real.
4. Class A items: added a block comment in the sweep above the relevant
   `probe_*` function explaining WHY the WARN is by design and what would flip
   it to PASS.
5. Class B/C items: would have been fixed inline (B) or filed as a GitHub issue
   (C). None were found this cycle.

## Baseline sweep (pre-audit)

```
- Checks: 51 pass, 5 warn, 0 fail, 0 skip
```

## WARN classification table

| # | Category | Check | Class | Action | Notes |
|---|---|---|---|---|---|
| 1 | org | `satellite_merge_posture` | A | Annotated above `probe_satellite_merge_posture` in `scripts/ops/production_readiness_sweep.py` | All 6 satellites set `allow_auto_merge=false` deliberately. The autonomy playbook (`docs/handoffs/codex-megaprompt-tranche-*` + `CLAUDE.md` "Cloud Routines") prescribes explicit admin-squash-merge over GitHub auto-merge. Critical settings (squash, delete-branch, runner gate) are PASS. Would only flip to PASS by enabling org-wide auto-merge — which would weaken the posture. |
| 2 | routines | `backtest-weekly` | A | Annotated above `probe_routines` in sweep; runbook already covers it (`docs/ops/backtest-weekly-runbook.md` + `docs/org/backtest-weekly-shadow-soak-2026-04-26.md`) | Soak gate started 2026-04-26, requires 4 scheduled weekly cycles. Cutover ≈ 2026-05-24. Memory: `project_remote_shadow_soak_gate.md`. |
| 3 | routines | `threat-refresh` | A | Annotated above `probe_routines`; soak doc `docs/org/threat-refresh-shadow-soak-2026-04-26.md` | 24 scheduled cycles required (~4 days). Will flip to PASS when scheduled-success counter ≥ 24 with zero FAIL comparisons. |
| 4 | routines | `content-engine` | A | Annotated above `probe_routines`; soak doc `docs/org/content-engine-shadow-soak-2026-04-26.md` | 7 scheduled daily cycles required, zero FAIL comparisons. Latest scheduled run 2026-04-29T13:44:52Z. |
| 5 | gcp | `gate_gemini_api_or_vertex_live_calls` | A | Annotated above `probe_google_readiness` in sweep | This gate is hard-coded `manual_gate` in `google_production_test_readiness.py` and the matrix runbook `docs/ops/production-readiness-matrix-runbook.md` formalizes this as expected. The sweep maps `manual_gate -> WARN` deliberately so operators see the surface. Flipping this would require removing the manual-gate guardrail, which would weaken safety. Leave as WARN. |

## Verdict

All 5 baseline WARNs are **Class A — by design**. Zero stale config (Class B),
zero real failures (Class C). No GitHub issues filed this cycle.

The sweep already had no comment near the three `probe_*` functions that
generated these WARNs; that gap is now closed in this PR by adding a block
comment above each (`probe_satellite_merge_posture`, `probe_routines`,
`probe_google_readiness`). Each comment explains:

- Why the WARN is by design,
- What would flip it to PASS,
- Where the cross-reference lives (runbook, soak doc, memory ref),
- The condition or target date for re-evaluation.

## Post-change sweep

After the annotation edits, the sweep was re-run:

```
- Checks: 50 pass, 6 warn, 0 fail, 0 skip
```

The WARN delta vs baseline is one transient row:

```
| repo | canonical_checkout_clean | WARN | ## main...origin/main; dirty entries=1 |
```

This is the sweep correctly reporting that `scripts/ops/production_readiness_sweep.py`
was modified by this audit but not yet committed. After this PR commits the
annotations, that row returns to PASS and the WARN count reverts to the
baseline of 5.

```
| org | satellite_merge_posture | WARN | ... |
| routines | backtest-weekly | WARN | gate=collecting; latest=workflow_dispatch/success 2026-04-28T00:14:28Z |
| routines | threat-refresh | WARN | gate=collecting; latest=schedule/success 2026-04-29T22:11:05Z |
| routines | content-engine | WARN | gate=collecting; latest=schedule/success 2026-04-29T13:44:52Z |
| gcp | gate_gemini_api_or_vertex_live_calls | WARN | manual_gate: No API key presence, token budget, model call, or Vertex job was invoked by this harness. |
```

## Re-evaluation hook

Re-run this audit after any of the following:

- `infra/org-repos.yaml > soak_tracking.required_scheduled_successes` is met
  for any soaking routine (gate flips to `ready_for_artifact_review`,
  routine-level WARN auto-clears to PASS).
- The autonomy playbook changes the auto-merge policy (would clear the
  satellite posture WARN).
- `google_production_test_readiness.py` removes the `manual_gate` for live
  Gemini/Vertex invocation (would clear the GCP gate WARN — should only
  happen if Sapphire formally moves to budget-capped always-on AI services).
- A new WARN appears that is not in this table.
