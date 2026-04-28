# Intel Quality Studies Runbook

## Purpose

Use this runbook when reviewing whether Sapphire's regime labels or
Hyperliquid counterparty leaderboards are stable enough for downstream
intelligence weighting experiments.

This is an offline study. Do not use it as a live trading gate, execution
signal, or automatic parameter update.

## Inputs

Regime study:

- Preferred: `data/cross_asset/<date>/regimes.jsonl`
- Also accepted: JSON arrays or objects with top-level `label` and
  `confidence`, or nested `{"regime": {...}}`.

Counterparty study:

- Preferred: locally persisted counterparty snapshots containing `leaderboard`.
- Also accepted: JSONL rows grouped by `snapshot_id`, `generated_at`, or
  `timestamp`, with public `address` and optional `rank`, PnL, and Sharpe
  fields.

Never generate inputs by making a live Hyperliquid call from this runbook. Use
existing local artifacts or synthetic fixtures.

## Commands

Regime stability:

```bash
/usr/local/bin/python3 scripts/ops/intel_quality_studies.py regime-stability \
  --input data/cross_asset/2026-04-28/regimes.jsonl
```

Counterparty leaderboard stability:

```bash
/usr/local/bin/python3 scripts/ops/intel_quality_studies.py counterparty-stability \
  --input data/counterparty/2026-04-28/counterparty_leaderboards.jsonl \
  --top-n 20
```

Write a report:

```bash
/usr/local/bin/python3 scripts/ops/intel_quality_studies.py counterparty-stability \
  --input fixtures/counterparty_leaderboards.json \
  --top-n 10 \
  --output data/intel_quality/counterparty-stability.json
```

## How To Read Regime Results

- `stability_score >= 0.76`: stable enough for bounded offline experiments.
- `0.55 <= stability_score < 0.76`: mixed; keep as context.
- `< 0.55`: unstable; review smoothing and artifact quality.
- `suggested_global_regime_weight` is an offline candidate value, not a runtime
  config change.
- `regime_uncertain` is capped. A high uncertainty rate should lower narrative
  confidence and block automatic upweighting.

Recommended operator read:

1. Check `observations`.
2. Check `transition_rate` and `one_sample_flip_rate`.
3. Check whether `regime_uncertain` is material.
4. Review `runs` to see whether transitions are persistent or flickery.
5. Only then consider the suggested weights for backtests or narrative
   confidence experiments.

## How To Read Counterparty Results

- High `mean_adjacent_jaccard` means the top-N cohort is stable.
- High `mean_rank_spearman` means common traders preserve their relative rank.
- High `mean_churn_rate` means the leaderboard is rotating too quickly for
  trader-specific claims.
- `stable_watchlist` candidates are public addresses with enough appearances
  and low rank volatility under the selected thresholds.

Recommended operator read:

1. Check `snapshots >= 2`.
2. Check `mean_churn_rate`.
3. If churn is high, use cohort-level language only.
4. If churn is low and stable candidates exist, use public-address watchlists as
   corroborating context only.
5. Do not copy trades, infer identity, or call private endpoints.

## Verification

Focused tests:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_intel_quality_studies.py -q
```

Touched-file lint:

```bash
ruff check lib/intel/quality_studies.py \
  scripts/ops/intel_quality_studies.py \
  tests/unit/test_intel_quality_studies.py
```

Compile check:

```bash
/usr/local/bin/python3 -m compileall \
  lib/intel/quality_studies.py \
  scripts/ops/intel_quality_studies.py
```

## Safety Notes

- This runbook intentionally avoids `SAPPHIRE_HYPERLIQUID_LIVE`.
- Reports are local study artifacts.
- Any promotion from suggested weights to runtime behavior must be a separate
  PR with backtest evidence, rollback notes, and explicit non-execution scope.
