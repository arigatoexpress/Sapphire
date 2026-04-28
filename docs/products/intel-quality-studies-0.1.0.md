# Intel Quality Studies 0.1.0

## What This Is

Intel Quality Studies 0.1.0 is an offline study layer for two Sapphire
intelligence surfaces:

- Cross-asset regime labels from `data/cross_asset/<date>/regimes.jsonl`.
- Public Hyperliquid counterparty leaderboards from local counterparty artifacts
  or synthetic JSON/JSONL fixtures.

The surface is deliberately post-run and read-only. It answers:

- Are cross-asset regime labels persistent enough to justify bounded regime
  weight tuning experiments?
- Is the public counterparty leaderboard stable enough to use trader-level
  watchlists, or should Sapphire use only cohort-level aggregate language?

It does not call Hyperliquid, fetch market data, publish events, send Telegram
messages, or touch the trading critical path.

## Surface

- Pure analyzer: `lib/intel/quality_studies.py`
- CLI wrapper: `scripts/ops/intel_quality_studies.py`
- Focused tests: `tests/unit/test_intel_quality_studies.py`

The analyzer accepts ordinary Python dictionaries. The CLI accepts `.json` and
`.jsonl` files and prints or writes a JSON report.

## Regime Stability Metrics

The regime study normalizes rows with either top-level `label`/`confidence`
fields or nested `{"regime": {...}}` payloads.

Key fields:

- `observations`: usable regime rows.
- `label_counts`: frequency by regime label.
- `transition_rate`: transitions divided by possible transitions.
- `one_sample_flip_rate`: fraction of runs where a non-uncertain label appears
  for only one sample.
- `uncertainty_rate`: share of `regime_uncertain` rows.
- `mean_confidence`: average detector confidence.
- `persistence_score`: bounded score from average run length.
- `stability_score`: composite score from confidence, persistence, uncertainty,
  and flicker.
- `suggested_global_regime_weight`: offline tuning suggestion in `[0.25, 1.20]`.
- `per_label_weights`: bounded per-label suggestions with interpretation text.

Interpretation:

- `stable`: labels are persistent enough for bounded offline tuning studies.
- `mixed`: use the labels as context, but do not upweight them alone.
- `unstable`: favor smoothing, longer windows, or review-only usage.
- `insufficient_data`: collect more artifacts before interpreting.

The weight fields are not execution parameters. They are candidate values for
offline backtests, narrative confidence calibration, or future correlator
experiments.

## Counterparty Leaderboard Stability Metrics

The counterparty study normalizes local leaderboard snapshots. It accepts:

- JSON snapshots containing `leaderboard`, `traders`, or `rankings`.
- JSONL rows grouped by `snapshot_id`, `generated_at`, or `timestamp`.

Key fields:

- `snapshots`: usable leaderboard snapshots.
- `mean_adjacent_jaccard`: average overlap between adjacent top-N cohorts.
- `mean_rank_spearman`: rank-order stability for traders appearing in adjacent
  snapshots.
- `mean_churn_rate`: `1 - jaccard`.
- `leaderboard_stability_score`: composite score from overlap, rank stability,
  and stable watchlist retention.
- `stable_watchlist`: public addresses that meet the appearance-rate and
  rank-volatility thresholds.
- `trader_stability`: per-address appearance rate, average rank, rank stdev,
  latest rank, and latest quality score.

Interpretation:

- Stable watchlist candidates can be named in internal analysis by public
  address, but still only as corroborating context.
- High churn means the surface should be described as a cohort signal, not a
  trader-specific reputation signal.
- A stable leaderboard does not mean copy trading is safe. Public accounts can
  be hedged elsewhere, split across venues, or intentionally noisy.

## Safety Contract

- Offline only.
- No live Hyperliquid calls.
- No private or authenticated exchange data.
- No wallet keys.
- No event publishing.
- No order generation.
- No position sizing changes.
- No mutation of upstream artifacts.

This surface sits above Tranche 4 counterparty and cross-asset artifacts. It
measures quality after artifacts exist; it does not change artifact generation.

## Example Commands

```bash
/usr/local/bin/python3 scripts/ops/intel_quality_studies.py regime-stability \
  --input data/cross_asset/2026-04-28/regimes.jsonl

/usr/local/bin/python3 scripts/ops/intel_quality_studies.py counterparty-stability \
  --input data/counterparty/2026-04-28/leaderboards.jsonl \
  --top-n 20 \
  --output data/intel_quality/counterparty-stability-2026-04-28.json
```

## Future Work

- Join regime stability with event-impact performance by label.
- Compare counterparty leaderboard stability against realized follow-through of
  `counterparty.smart_money.move` artifacts.
- Add an optional markdown renderer once operators agree on the canonical table
  layout.
