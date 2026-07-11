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
| 2 | 2026-07-08T13:23Z | schedule | [28946029490](https://github.com/arigatoexpress/Sapphire/actions/runs/28946029490) | FAIL | 2 | 0 | Body length drift in market_pulse (58%, exceeds FAIL threshold) and remote substack quality failure in ai_intel (local passed, remote failed). Report: `data/content/shadow-reports/content-shadow-comparison-20260709T130900Z.json`. |
| 3 | 2026-07-09T14:24Z | schedule | [29025208596](https://github.com/arigatoexpress/Sapphire/actions/runs/29025208596) | FAIL | 1 | 0 | market_pulse body length delta ratio 0.58 (local 128 chars vs remote 308 chars) exceeds the 0.5 FAIL threshold; X platform quality and rendered-file drift also present. |
| 4 | 2026-07-11T13:07Z | schedule | [29153184200](https://github.com/arigatoexpress/Sapphire/actions/runs/29153184200) | FAIL | 1 | 0 | market_pulse body length delta 0.58 (128 vs 308 chars) exceeds 0.50 FAIL threshold; remote x render passed while local did not. Report: `data/content/shadow-reports/content-shadow-comparison-20260711T130722Z.json`. |
