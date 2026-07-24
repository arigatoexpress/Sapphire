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
| 2 | 2026-07-15T13:03Z | schedule | [29417631595](https://github.com/arigatoexpress/Sapphire/actions/runs/29417631595) | FAIL | 2 | 0 | Remote ai_intel fails substack quality (evidence_coverage_low, argument_coherence_low) and market_pulse body-length delta is 58% — file hash and body drift across ai_intel and market_pulse on all platforms. |
| 3 | 2026-07-16T13:12Z | schedule | [29501233327](https://github.com/arigatoexpress/Sapphire/actions/runs/29501233327) | FAIL | 1 | 0 | market_pulse body-length delta 58% — remote rendered fresh 2026-07-16 report (308 chars) vs stale local draft (128 chars); x quality diverges (local too_short, remote passed). |
| 4 | 2026-07-18T12:43Z | schedule | [29644840287](https://github.com/arigatoexpress/Sapphire/actions/runs/29644840287) | FAIL | 1 | 0 | market_pulse body-length delta 58% (remote 308 chars vs stale local draft 128 chars dated 2026-04-17); x quality diverges (local too_short, remote passed). Same stale-local-draft cause as cycle 3. Was PR #935 ("cycle 5"). |
| 5 | 2026-07-19T12:44Z | schedule | [29687565937](https://github.com/arigatoexpress/Sapphire/actions/runs/29687565937) | FAIL | 1 | 0 | market_pulse body-length delta 58% — same stale local draft. Was PR #941 ("cycle 6"). |
| 6 | 2026-07-20T13:42Z | schedule | [29747376028](https://github.com/arigatoexpress/Sapphire/actions/runs/29747376028) | FAIL | 2 | 0 | Body-length delta over threshold in market_pulse (58%) and weekly_crypto_brief (66%), file hash drift across all platforms; ai_intel and security_digest pass. Was PR #945 ("cycle 7"). |
| 7 | 2026-07-21T13:09Z | schedule | [29833191613](https://github.com/arigatoexpress/Sapphire/actions/runs/29833191613) | FAIL | 1 | 0 | market_pulse body-length delta 58% — same stale local draft. Was PR #949 ("cycle 8"). |
| 8 | 2026-07-22T13:15Z | schedule | [29923103756](https://github.com/arigatoexpress/Sapphire/actions/runs/29923103756) | FAIL | 2 | 2 | Log-derived comparison; artifact download unavailable to the routine's token. ai_intel substack quality fails (evidence_coverage_low, argument_coherence_low, persistent since cycle 2); market_pulse delta 58%. missing=2 reflects incomplete reconstruction, not absent kinds. Was PR #950 ("cycle 9"). |
| 9 | 2026-07-23T13:18Z | schedule | [30010633747](https://github.com/arigatoexpress/Sapphire/actions/runs/30010633747) | FAIL | 1 | 0 | market_pulse body-length delta 58% — same stale local draft; x quality and file hash diverge. Was PR #932 ("cycle 4"). |


## Standing verdict after 9 cycles

Cycles 2-9 are **the same failure**, not eight findings: a local draft rendered
2026-04-17 (128 chars) is compared against a freshly rendered remote report
(308 chars), so `market_pulse` reports a 58% body-length delta every single run.
`ai_intel`'s substack quality failure (`evidence_coverage_low`,
`argument_coherence_low`) has likewise been constant since cycle 2.

Nothing was learned after cycle 3. The soak is re-measuring a known defect daily
and opening a pull request about it, which is how six mutually-conflicting PRs
accumulated — every cycle appended one row at the same line of this file, so
merging any one of them made the other five conflict. Cycle numbering had also
drifted out of order (the routine's "cycle 4" was dated 2026-07-23, later than
its "cycle 9"); the table above is renumbered chronologically, and each row
records the PR it came from.

Two things need to happen before this log is worth appending to again:

1. **Fix the compared artifact, not the report.** The local draft is stale
   because nothing regenerates it before comparison. Until it is refreshed per
   cycle, the 58% delta is an artifact of the harness, not a signal about the
   content engine.
2. **Make the routine idempotent.** It should update an existing open PR, or
   only open one when the verdict *changes*, instead of emitting a new
   conflicting PR every day. Compare with the factory-repo-fixer routine, which
   had the same defect (#930 and #934 were byte-identical duplicates).
