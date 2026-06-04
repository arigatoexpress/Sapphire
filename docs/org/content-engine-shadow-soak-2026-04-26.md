# Content-Engine Remote Shadow Soak

## Goal

Move `content-engine` from blocked to remote-shadow soak without changing the
local canonical runtime. The Mac LaunchAgent remains authoritative until the
documented soak gate passes and a later PR disables it with rollback notes.

## What Changed

- Remote workflow: `.github/workflows/content-engine.yml`
- Local routine shadowed: `com.sapphire.content-engine`
- Comparator: `scripts/ops/compare_content_artifacts.py`
- Uploaded artifact: `content-engine-<run_id>`

## Safety Posture

- The workflow runs `python -m lib.content`, which writes draft and ready files.
- It does not run `python -m lib.content --publish`.
- `SAPPHIRE_PUBLISH_LIVE=0` is set in the workflow.
- `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=0` is set in the workflow.
- Local content publishing side effects remain governed by the separate
  `com.sapphire.content-publisher` LaunchAgent and its explicit opt-ins.

## Comparator

Run after downloading a GitHub Actions artifact:

```bash
python3 scripts/ops/compare_content_artifacts.py \
  --local-root /Users/aribs/Code/Sapphire \
  --remote-root /path/to/downloaded/content-engine-artifact
```

The comparator checks:

- Matching report kinds.
- Matching platform coverage per report kind.
- Remote quality failures when the local rendering passed.
- Rendered artifact existence and size/hash drift.
- Source/tag/title drift as WARN unless strict mode is requested.

## Soak Gate

At least 7 scheduled daily cycles with:

- zero FAIL comparisons,
- no remote-only quality failures,
- matching report-kind/platform coverage,
- local LaunchAgent rollback documented before any disablement.

## Rollback

Revert the PR that adds `.github/workflows/content-engine.yml` and the
manifest stage change. The local LaunchAgent remains untouched.

## Soak Log

| Cycle | Date (UTC) | Trigger | Run ID | Verdict | FAIL | Missing | Notes |
|-------|------------|---------|--------|---------|-----:|--------:|-------|
| 1 | 2026-04-26T20:39Z | workflow_dispatch | [24966520333](https://github.com/arigatoexpress/Sapphire/actions/runs/24966520333) | WARN | 0 | 0 | Body length and rendered-file hash drift across all 4 kinds, all deltas under 50% — expected for first-cycle freshness skew. No remote-only quality failures. Report: `data/content/shadow-reports/content-shadow-comparison-20260426T204118Z.json`. |
| 2 | 2026-06-01T17:27Z | schedule | [26770799718](https://github.com/arigatoexpress/Sapphire/actions/runs/26770799718) | FAIL | 2 | 0 | Remote generated fresher market_pulse and weekly_crypto_brief drafts (2026-06-01 vs local 2026-04-17); body-length delta exceeds threshold on both kinds — local content is stale, not an engine regression. Report: `data/content/shadow-reports/content-shadow-comparison-20260602T130651Z.json`. |
| 3 | 2026-06-02T16:11Z | schedule | [26832583263](https://github.com/arigatoexpress/Sapphire/actions/runs/26832583263) | FAIL | 1 | 0 | Remote market_pulse is a fresh 2026-06-02 render (body +58%, hash mismatch, x.quality passes remotely but fails locally) while local canonical dates from 2026-04-17; 3 of 4 kinds fully match. |
| 4 | 2026-06-03T16:26Z | schedule | [26898363005](https://github.com/arigatoexpress/Sapphire/actions/runs/26898363005) | FAIL | 2 | 0 | ai_intel remote substack quality failed (evidence_coverage 0.47, argument_coherence 0.34 below thresholds); market_pulse body delta 58% over threshold — remote has fresh 2026-06-03 drafts while local canonical remains 2026-04-17. |
