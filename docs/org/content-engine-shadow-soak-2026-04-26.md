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
| 9 | 2026-07-22T13:15Z | schedule | [29923103756](https://github.com/arigatoexpress/Sapphire/actions/runs/29923103756) | FAIL | 2 | 2 | Log-derived comparison (artifact download unavailable via session token): ai_intel substack quality fails (evidence_coverage_low, argument_coherence_low, persistent from cycle 2); market_pulse body-length delta 58%; missing=2 reflects incomplete reconstruction — security_digest and weekly_crypto_brief absent from log output, likely present on runner per cycles 4–8 pattern. |
| 10 | 2026-07-28T13:24Z | schedule | [30363360256](https://github.com/arigatoexpress/Sapphire/actions/runs/30363360256) | FAIL | 1 | 0 | market_pulse body-length delta 58% (remote 308 chars vs local 128 chars); x quality diverges (local too_short, remote data_density_low + evidence_coverage_low). Report: `data/content/shadow-reports/content-shadow-comparison-20260729T130930Z.json`. |
| 11 | 2026-07-29T13:30Z | schedule | [30456345297](https://github.com/arigatoexpress/Sapphire/actions/runs/30456345297) | FAIL | 2 | 0 | ai_intel file and body drift across all platforms (remote 2026-07-29 vs local stale 2026-04-17 render) and market_pulse body-length delta 58% (remote 308 chars vs local 128 chars); x quality diverges (local too_short, remote data_density_low + evidence_coverage_low) — persistent pattern from prior cycles. Report: `data/content/shadow-reports/content-shadow-comparison-20260730T131025Z.json`. |
| 12 | 2026-08-05T13:29Z | schedule | [31010450134](https://github.com/arigatoexpress/Sapphire/actions/runs/31010450134) | FAIL | 2 | 0 | Log-derived comparison (artifact download unavailable): ai_intel substack remote quality fails (evidence_coverage_low, argument_coherence_low, persistent from cycle 2); market_pulse body-length delta 58% (remote 302 chars vs local 128 chars) and x quality diverges (local too_short, remote data_density_low + evidence_coverage_low). |
