# Walk-Forward Backtests + Regime Decomposition 0.1.0

**Status:** initial release (Tranche 6 Lane 5).
**Owner:** sapphire.
**Modules:** `lib/analytics/walkforward/{__init__,engine,regime_decomp,deflated_sharpe}.py`,
`services/walkforward/build.py`, `plugins/claw-sapphire/tools/internal/walkforward.py`.
**Verification:** 111 tests across 4 files (40 engine + 32 regime + 25 deflated + 14 plugin),
ZERO modifications to upstream `lib/analytics/strategies.py`, `backtest.py`, `backtest_engine.py`,
`risk_engine.py`, or `deflated_sharpe.py`.

## Why this exists

Sapphire's strategy library has lived for months on a 27-combo grid sweep over the
**full** 90-day OHLCV window for each strategy class. The result is rigorously
in-sample-fit — every parameter combo has seen every bar. That's exactly the
multiple-comparisons trap the Bailey & López de Prado (2014) Deflated Sharpe Ratio
was invented to flag, and a paper by López de Prado in 2018 ("The 10 Reasons Most
Machine Learning Funds Fail") argues that walk-forward CV is the floor every
quant strategy should clear before being trusted with live capital.

Lane 5 lifts that floor for Sapphire:

1. **Walk-forward orchestrator** — slides train/test windows across the full bar
   series, picks the best param combo on each train slice, then evaluates it
   verbatim on the immediately-following, never-before-seen test slice.
   Per-window OOS metrics make in-sample/out-of-sample drift visible and
   computable.
2. **Regime decomposition** — joins per-bar OOS test returns to the cross-asset
   regime classifier (Tranche 4) and groups them into per-regime buckets.
   The output answers "where does this strategy actually make money — risk-on,
   risk-off, decorrelated, crisis, or uncertain?"
3. **Walk-forward Deflated Sharpe wrapper** — feeds the per-window Sharpes
   plus the *out-of-sample* observation count into the existing
   `lib.analytics.deflated_sharpe` module, producing a probability that the
   selected strategy is real (vs. lucky out of the trial set) calibrated
   against the *OOS* sample, not the in-sample artifact.

The whole layer is **additive**. Nothing in `lib/analytics/strategies.py` or its
backtest/risk/deflated-sharpe peers changed; this lane only consumes them.

## Public surface

### `lib.analytics.walkforward.engine`

```python
from lib.analytics.walkforward import (
    WalkforwardConfig,
    run_walkforward,
    walkforward_windows,
)

cfg = WalkforwardConfig(train_bars=90, test_bars=30, advance_bars=30)
result = run_walkforward(RegimeAwareRSI, bars, aux={"btc": btc, "spy": spy}, config=cfg)
```

`WalkforwardConfig` knobs:

| Field | Default | Meaning |
|---|---|---|
| `train_bars` | 90 | Bars in each train slice. **Required ≥ 60.** |
| `test_bars` | 30 | Bars in each test slice. **Required ≥ 20.** |
| `advance_bars` | `None` (= test_bars) | Step between successive train_starts. |
| `purge_bars` | 0 | Bars dropped between train_end and test_start. |
| `embargo_bars` | 0 | Bars trimmed from the next train slice's front when overlapping. |
| `selection_metric` | `"sortino"` | One of `sortino`, `sharpe`, `calmar`, `profit_factor`, `total_return`. |
| `bankroll` | 10_000.0 | Initial capital for the inner BacktestEngine. |
| `symbol` | `"?"` | Propagated to the inner engine. |
| `min_train_trades` | 1 | Combos with fewer in-sample trades are treated as -inf for selection. |

`run_walkforward(strategy_cls, bars, *, grid=None, aux=None, config=None) -> WalkforwardResult` —
the result carries:

* `n_windows`, `n_active_windows` (windows with ≥1 trade)
* `windows: list[WindowMetrics]` — per-window train_metric, chosen_params,
  test_sortino/sharpe/calmar/profit_factor/win_rate/max_dd, test_returns,
  test_start_ts/test_end_ts.
* `concatenated_test_returns` + `concatenated_test_timestamps` — the chronological
  OOS-bar return stream consumed by `regime_decomp` and `deflated_sharpe`.
* Aggregates (`mean_test_sortino`, `median_test_sortino`, `std_test_sortino`,
  `test_sortino_cv`, etc.). The CV is **the** at-a-glance overfitting warning —
  high CV means windows disagree wildly and the strategy is fragile.

### `lib.analytics.walkforward.regime_decomp`

```python
from lib.analytics.walkforward import decompose_by_regime, load_regime_labels

labels = load_regime_labels()  # walks data/cross_asset/<latest>/regimes.jsonl
decomp = decompose_by_regime(
    result.concatenated_test_returns,
    result.concatenated_test_timestamps,
    labels=labels,
)
```

The result carries `buckets: list[RegimeReturnsBucket]` with per-regime n_observations,
total/mean/median return, volatility, downside volatility, win_rate, max drawdown,
Sharpe, Sortino, and `pnl_share` (each bucket's share of total absolute PnL).
Plus `distribution`, `dominant_regime`, `n_labelled`/`n_unlabelled`,
and `overall_mean_return`/`overall_volatility`.

### `lib.analytics.walkforward.deflated_sharpe`

```python
from lib.analytics.walkforward import deflated_sharpe_for_walkforward

dsr = deflated_sharpe_for_walkforward(result, threshold=0.95)
print(dsr.passed, dsr.probability, dsr.deflated_sharpe)
```

The wrapper:

* Pulls `windows[*].test_sharpe` from the WalkforwardResult.
* Pulls `concatenated_test_returns` to derive `n_obs` (the OOS bar count, *not*
  the in-sample bar count — this is the key correction).
* Estimates skewness and kurtosis from the OOS returns via stdlib estimators
  (Pearson moments). Default Gaussian assumptions are *replaced* with empirical
  values, which makes the DSR honest in the presence of fat tails.
* Calls the existing `lib.analytics.deflated_sharpe.deflated_sharpe_ratio`
  unchanged. The base module is **read-only**.

## Window-advance policy

Default: `advance_by_test_window` (i.e., `advance_bars = test_bars`). This
produces a chain of strictly non-overlapping test slices that, concatenated,
cover the full bar series minus the warm-up. It is the most conservative
default — every OOS observation is independent of every other.

Two alternative modes are explicitly supported:

* **Rolling overlap** — `advance_bars < test_bars`. Successive test slices
  overlap by `test_bars - advance_bars`. Useful for small-bar series where you
  need more windows to drive a stable average. Increases dependence between
  OOS observations; treat aggregates with caution and increase
  `min_train_trades` to compensate.
* **Strided gaps** — `advance_bars > test_bars`. Skips bars between successive
  test slices. Useful for testing whether a strategy's OOS performance is
  stable across an entire calendar quarter or earnings cycle without each
  test slice cannibalising the next.

The window enumerator is pure (`walkforward_windows(n_bars, config)`); it
returns the full list of `WalkforwardWindow` objects without touching bars or
strategies, so callers can preview the schedule before committing to a run.

## Regime-label join semantics

The cross-asset regime feed (`data/cross_asset/<YYYY-MM-DD>/regimes.jsonl`)
emits **at most one regime row per snapshot**, typically once per day. Every
backtest test slice in turn produces one return per bar. The two streams must
be aligned without leaking labels backwards in time.

`attach_regime_labels(timestamps, labels, semantics=...)` supports three modes:

* **`forward_fill`** (default) — for each bar, inherit the most recent regime
  label *strictly before or equal to* the bar's date. Equivalent to "the
  regime classification active when the bar closed". Bars that occur before
  the first labelled date receive `default_label` (defaults to
  `regime_uncertain`).
* **`exact_match`** — only use a label if the bar's exact date is in the
  feed; otherwise return `default_label`. Conservative; useful when the
  regime feed is dense and you want to avoid imputation.
* **`nearest_prior`** — like `forward_fill`, but if no prior labelled date
  exists, fall through to the *next future* labelled date. Useful for
  test slices that begin before the regime feed's earliest entry; lets you
  use the available regime context rather than dropping the slice.

The default is `forward_fill` because it matches how a live operator would
read the regime — the latest call until a new one supersedes it.

## Deflated Sharpe degrees-of-freedom handling

The base `deflated_sharpe_ratio` function takes `n_obs` as the number of
observations used to compute each Sharpe, defaulting to 252 (one year of
daily bars). For a walk-forward, that default is wrong twice over:

1. **In-sample n is wrong** — using the full bar count over-counts independent
   observations and *under*-penalises multiple testing.
2. **Per-window n is also wrong** — each window has a different test length,
   so there is no single "n_obs per Sharpe" to use.

The wrapper takes the **concatenated OOS test-return count** as `n_obs`. That
count is well-defined (it is the number of test-period bars across all
windows), independent of which combo was selected on each window, and
correctly penalises walk-forwards that ran many short windows vs.
walk-forwards with fewer / longer windows. Operators who need a publication-
matching convention can pass `n_obs_override` explicitly.

The wrapper also computes empirical skewness and kurtosis from the OOS
returns and forwards them to `deflated_sharpe_ratio`. This matters because
the Bailey & López de Prado correction is sensitive to non-Gaussian moments;
default Gaussian assumptions over-estimate the probability of a real edge in
fat-tailed return streams.

## Build script — `services/walkforward/build.py`

Synthetic-OHLCV by default — fully deterministic, no network. Live mode is
gated on `--bars-source yfinance` (operator opt-in). Outputs:

```
data/backtests/walkforward/<YYYY-MM-DD>/
    RegimeAwareRSI.json
    FundingRateContrarian.json
    CorrelationBreakout.json
    MultiTFMomentum.json
    SapphireComposite.json
    manifest.json
```

Each per-strategy JSON carries one block per horizon (90 / 180 / 365 days by
default), and each block carries the full `WalkforwardResult.to_dict()`,
the regime decomposition for that walk-forward run, and the walk-forward DSR.

Operators run it manually:

```bash
python3 -m services.walkforward.build --strategies all --horizons 90,180,365
```

…or wire it into the existing `backtest-sweep` weekly scheduled task. No new
LaunchAgent is shipped in this lane — Lane 5 ends at the disk artifact.

## Plugin tool — `walkforward`

```bash
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/walkforward.py
echo '{"action":"run","strategy":"RegimeAwareRSI","n_bars":200}' | python3 plugins/claw-sapphire/tools/walkforward.py
echo '{"action":"decompose","strategy":"RegimeAwareRSI","n_bars":200,"labels":{"2025-01-01":"risk_on"}}' | python3 plugins/claw-sapphire/tools/walkforward.py
echo '{"action":"deflated","strategy":"RegimeAwareRSI","n_bars":200}' | python3 plugins/claw-sapphire/tools/walkforward.py
echo '{"action":"latest"}' | python3 plugins/claw-sapphire/tools/walkforward.py
```

Actions:

| Action | Inputs | Output |
|---|---|---|
| `status` | none | Caps + valid actions + known strategies. No I/O. |
| `run` | `strategy`, `n_bars`, `train`, `test`, `advance`, `metric`, `bankroll` | Full `WalkforwardResult.to_dict()`. |
| `decompose` | `run` keys + `labels` (optional dict, otherwise read from `data/cross_asset/`), `semantics`, `default_label` | Walk-forward result + regime decomposition. |
| `deflated` | `run` keys + `threshold` | Walk-forward result + walk-forward DSR. |
| `latest` | `output_root` (optional path) | Reads the most recent manifest.json under `data/backtests/walkforward/`. |

The tool is **internal** in `tool-registry.yaml` (not in `agent-manifest.yaml`)
and uses the same shim-at-top-level / impl-in-internal pattern as
`cross_asset_intel` and the rest of Sapphire's plugin tools.

## Test surface

- 40 engine tests — window enumeration (advance, purge, embargo, validation
  errors), grid enumeration, metric translation, equity-to-returns helpers,
  end-to-end run on synthetic OHLCV across all five strategy classes.
- 32 regime decomposition tests — date normalisation across formats, three
  semantic join modes (forward_fill / exact_match / nearest_prior), bucket
  metric edge cases (all wins, all losses, mixed), JSONL loader for
  file/directory/missing-dir/duplicate-date cases, plus the
  `decompose_walkforward_result` adapter.
- 25 deflated-Sharpe wrapper tests — moment estimators (skewness sign,
  kurtosis defaults, too-few-obs zero), `_coerce_sharpes` NaN/None drops,
  wrapper `n_obs` derivation, threshold override, single-window degeneracy,
  no-input degenerate-result, and a smoke test that the wrapper does not
  rebind any symbol on the base module.
- 14 plugin tool tests — every action (`status`/`run`/`decompose`/`deflated`/
  `latest`/unknown), inline label injection, malformed-JSON and non-object
  stdin handling, manifest file readback.

All tests use deterministic synthetic OHLCV — no live data, no fixtures from
`data/cross_asset/`, no fixtures from the canonical backtests tree.

## Caveats

- The walk-forward engine treats each (strategy, symbol, horizon) tuple as
  independent. Cross-symbol correlations are not modelled here; they are
  Lane 6's job.
- The deterministic synthetic OHLCV in the build script is intentionally
  simple. To produce production-grade backtests, run with
  `--bars-source yfinance` and the symbol of interest. The synthetic mode
  exists primarily for fast tests and CI.
- `services/walkforward/build.py` defaults to `BTC-USD` symbol so it can run
  out of the box. Multi-symbol fan-out is a follow-up.
- The DSR wrapper uses `lib.analytics.deflated_sharpe.deflated_sharpe_ratio`
  unchanged. If a future Lane sharpens the base estimator (e.g., better
  treatment of small-sample bias), the wrapper inherits that for free.
- Per-window equity-curve isolation depends on the inner `BacktestEngine.run`
  returning a complete equity curve (one entry per bar). PR #102 made that
  invariant; we rely on it. If a future change to `BacktestEngine.run` breaks
  the per-bar equity invariant, `_isolate_test_metrics` will degrade
  gracefully (returning zero metrics and an empty trade list), but the OOS
  rigour will silently fall.

## See also

- `docs/ops/walkforward-runbook.md` — operational runbook (how to invoke,
  read artifacts, integrate with the dashboard, debug zero-window results).
- `lib/analytics/cpcv.py` — the Combinatorial Purged CV cousin. Walk-forward
  and CPCV solve different problems: walk-forward enforces strict temporal
  ordering and treats each window as a single fit, while CPCV samples all
  C(N, k) combinations of disjoint group memberships. Both are valid; both
  are now available.
- `lib/cross_asset/regime_detector.py` — the source of regime labels.
- `lib/analytics/deflated_sharpe.py` — the underlying DSR estimator.
