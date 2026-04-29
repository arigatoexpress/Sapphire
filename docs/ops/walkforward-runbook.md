# Walk-Forward Runbook

**Owner:** sapphire.
**Companion product doc:** `docs/products/walkforward-and-regime-0.1.0.md`.
**Modules touched:** `lib/analytics/walkforward/`, `services/walkforward/build.py`,
`plugins/claw-sapphire/tools/walkforward.py`, `infra/tool-registry.yaml`.
**Prerequisite knowledge:** Sapphire strategy library
(`lib/analytics/strategies.py`), the cross-asset regime feed
(`data/cross_asset/<date>/regimes.jsonl`), and the existing Deflated Sharpe
implementation (`lib/analytics/deflated_sharpe.py`). All three are read-only
inputs to the walk-forward layer.

## When to run this

Operators run a walk-forward sweep:

1. **Before promoting a parameter set to live capital.** The full grid sweep
   in `lib.analytics.run_strategies` is in-sample by construction; walk-forward
   is the OOS sanity check.
2. **After a regime classifier change.** If
   `lib/cross_asset/regime_detector.py` thresholds move, the regime
   decomposition changes even if the strategies don't — re-run to refresh
   the per-regime PnL attribution.
3. **Weekly, automated.** The existing `backtest-sweep` scheduled task
   already runs the full grid sweep. Lane 5 adds the walk-forward / regime /
   DSR layer; the operator may extend the scheduled task to also invoke
   `services.walkforward.build` if the rolling horizon coverage matters
   week to week.

## How to invoke — three paths

### Path A: command-line build script (default)

```bash
python3 -m services.walkforward.build \
    --strategies all \
    --symbol BTC-USD \
    --horizons 90,180,365 \
    --train 90 --test 30 --advance 30 \
    --bars-source synthetic \
    --selection-metric sortino \
    --bankroll 10000
```

Outputs land under `data/backtests/walkforward/<YYYY-MM-DD>/`:

```
data/backtests/walkforward/2026-04-29/
    RegimeAwareRSI.json
    FundingRateContrarian.json
    CorrelationBreakout.json
    MultiTFMomentum.json
    SapphireComposite.json
    manifest.json
```

The default `--bars-source synthetic` produces deterministic OHLCV from
stdlib trig functions. To run against real bars, switch to
`--bars-source yfinance`. That requires `yfinance` to be installed and
network egress to Yahoo's data endpoints; it is **not** the default, by
design — most operators run synthetic for fast feedback and reserve
yfinance for production sweeps.

### Path B: in-process via the Python API

```python
from lib.analytics.backtest_engine import fetch_ohlcv
from lib.analytics.walkforward import (
    WalkforwardConfig,
    decompose_by_regime,
    deflated_sharpe_for_walkforward,
    load_regime_labels,
    run_walkforward,
)
from lib.analytics.strategies import RegimeAwareRSI

bars = fetch_ohlcv("BTC-USD", days=365)
btc = fetch_ohlcv("BTC-USD", days=365)
spy = fetch_ohlcv("SPY", days=365)

cfg = WalkforwardConfig(train_bars=90, test_bars=30, advance_bars=30, symbol="BTC-USD")
result = run_walkforward(RegimeAwareRSI, bars, aux={"btc": btc, "spy": spy}, config=cfg)

labels = load_regime_labels()
decomp = decompose_by_regime(
    result.concatenated_test_returns,
    result.concatenated_test_timestamps,
    labels=labels,
)

dsr = deflated_sharpe_for_walkforward(result, threshold=0.95)
print(f"OOS mean Sortino: {result.mean_test_sortino}, sortino_cv: {result.test_sortino_cv}")
print(f"DSR passed: {dsr.passed}, probability: {dsr.probability}")
print(f"Dominant regime: {decomp.dominant_regime}")
```

### Path C: plugin tool (operator UX)

Two-line invocation through hermes / Telegram / a manual stdin pipe:

```bash
echo '{"action":"run","strategy":"RegimeAwareRSI","n_bars":365,"train":90,"test":30}' \
    | python3 plugins/claw-sapphire/tools/walkforward.py | jq .

echo '{"action":"decompose","strategy":"SapphireComposite","n_bars":500,"labels":{"2025-01-01":"risk_on","2025-04-01":"risk_off"}}' \
    | python3 plugins/claw-sapphire/tools/walkforward.py | jq .

echo '{"action":"latest"}' \
    | python3 plugins/claw-sapphire/tools/walkforward.py | jq .
```

The plugin tool uses the deterministic synthetic OHLCV under the hood and is
intended for quick what-if probing — operators can sweep `train`, `test`,
`advance`, and `metric` without committing to a full sweep + artifact write.
For production artifacts, prefer Path A.

## Reading the artifact

Each per-strategy JSON has the shape:

```json
{
  "version": "0.1.0",
  "generated_at": "...",
  "strategy_cls": "RegimeAwareRSI",
  "symbol": "BTC-USD",
  "param_grid": {...},
  "horizons": [
    {
      "horizon_days": 90,
      "config": {...},
      "result": {
        "n_windows": 3,
        "n_active_windows": 2,
        "mean_test_sortino": 1.2,
        "test_sortino_cv": 0.45,
        "windows": [...],
        "concatenated_test_returns": [...],
        "concatenated_test_timestamps": [...]
      },
      "regime_decomposition": {
        "buckets": [
          {"label": "risk_on_correlated", "n_observations": 40, "total_return": 0.08, "sharpe": 1.1, "pnl_share": 0.65, ...},
          {"label": "risk_off_flight_to_dollar", "n_observations": 12, "total_return": -0.02, "sharpe": -0.4, "pnl_share": 0.18, ...}
        ],
        "distribution": {"risk_on_correlated": 0.62, "risk_off_flight_to_dollar": 0.19, "regime_uncertain": 0.19},
        "dominant_regime": "risk_on_correlated",
        "n_labelled": 52,
        "n_unlabelled": 8
      },
      "deflated_sharpe": {
        "passed": false,
        "probability": 0.41,
        "deflated_sharpe": -0.23,
        "n_windows": 3,
        "n_obs_oos": 60,
        "skewness": -0.18,
        "kurtosis": 3.4,
        ...
      }
    },
    { "horizon_days": 180, ...},
    { "horizon_days": 365, ...}
  ]
}
```

### What to look at first

1. **`test_sortino_cv` per horizon.** A value above ~1.0 means windows
   disagree wildly — the strategy is fragile, and a single train slice
   produces a parameter that doesn't generalise. Investigate before trusting
   the mean.
2. **`deflated_sharpe.passed` and `probability` per horizon.** The DSR is
   deliberately conservative; a `passed=true` at 0.95 threshold is a
   high bar, especially given the small `n_obs_oos` typical of crypto
   sweeps. If `probability < 0.50`, treat the strategy as on-par with
   the trial-set noise floor.
3. **Regime `dominant_regime` + per-bucket `pnl_share`.** If 80% of PnL
   comes from one regime, the strategy is regime-dependent. That is fine
   if the live deployment has a regime gate; otherwise it is a deployment
   risk.
4. **Per-window `chosen_params` drift.** If the engine picks a different
   `(rsi_period, sl_pct, tp_pct)` on each window, the train slice is
   over-fitting to local conditions and the OOS test slice will lag.

## Common pitfalls

### "Zero windows" returned

Cause: not enough bars for the configured `train_bars + test_bars + purge_bars`.
Fix: shrink the config (`train=60, test=20`) or pass more bars.
Debug: call `walkforward_windows(len(bars), cfg)` directly to see the
window list before running the full backtest.

### "All windows have zero trades"

Cause: the strategy didn't fire on the train slices either, so the engine
fell back to a default combo and the test slice produced no trades. This is
common with `RegimeAwareRSI` on a quiet market segment — the regime gate
blocks all entries.
Fix: increase `n_bars` to span more regime variety, or relax
`min_train_trades=0` to allow no-trade combos to be selected (which then
still produce zero on test, but the result is honest about it).
Debug: drop `min_train_trades` to 0 and inspect `windows[*].train_trades` —
if every combo has zero on the train slice, the strategy itself isn't
firing on this data.

### "DSR `probability` is suspiciously low"

Cause: small `n_obs_oos` (typical for short walk-forwards) inflates the
correction term in the BLP formula, pushing the deflated Sharpe down.
Fix: increase `train_bars` + `test_bars` to lengthen the OOS sample, or
set `n_obs_override` to a publication-matching value if you are comparing
against a published strategy.
Debug: print `dsr.n_obs_oos` and `dsr.skewness`/`dsr.kurtosis` — if
`n_obs_oos` is below ~50 the DSR is in degenerate territory; the
`probability` should be treated as advisory rather than gating.

### "Regime decomposition shows mostly `regime_uncertain`"

Cause: the cross-asset regime feed at `data/cross_asset/<date>/regimes.jsonl`
is empty, sparse, or absent. `load_regime_labels()` walks newest-first and
stops at the first non-empty `regimes.jsonl`. If the latest one has no
labelled rows (or none in the date range of the walk-forward), the join
falls back to `default_label = "regime_uncertain"`.
Fix: run `python3 -m services.cross_asset.run` to refresh the regime feed,
or pass an inline `labels` dict to `decompose_by_regime` for ad-hoc
analysis.
Debug: `len(load_regime_labels())` — should be > 0; if 0, the feed is
empty.

### "Tests pass locally, fail in CI"

Cause: the engine and regime modules are pure stdlib; flakes here are
almost always import order or path issues. The new test files use the
same `ROOT = Path(__file__).resolve().parents[2]` pattern as the existing
analytics tests; ensure `tests/conftest.py` is intact (the gotchas note in
`CLAUDE.md` warns against touching it).
Fix: run `make test` locally to mirror CI, then bisect on the failing
test name.

## Integration touch points

- **Dashboard `/performance` page** — consumes the latest
  `data/backtests/walkforward/<date>/manifest.json` through the read-only
  `/api/walkforward-results` endpoint. The page surfaces the best OOS
  horizon per strategy, mean test Sortino, DSR pass/fail, DSR probability,
  Sortino CV, dominant regime, and active-vs-total walk-forward windows.
  If no manifest exists yet, the endpoint returns HTTP 200 with
  `status=no_data` and the table renders the empty-state message instead of
  failing the dashboard.
- **Telegram morning brief** — does not consume walk-forward. Same boundary
  rationale.
- **Tool registry CI** — `infra/tool-registry.yaml` was extended with a
  `walkforward` entry. Run `make registry` to validate the registry shape
  invariants (every `.py` listed, every shim points at a real file, etc.)
  exactly as for the rest of the plugin tools.

## Failure modes vs. recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| `ValueError: train_bars must be ≥ 60` | Config too aggressive | Bump train/test back to spec floor |
| `ValueError: returns and timestamps must be the same length` | `concatenated_test_returns` and `concatenated_test_timestamps` drifted; usually a custom test-isolation function | Ensure each test slice produces a parallel `(returns, timestamps)` pair; the default `_isolate_test_metrics` does this |
| Plugin tool returns `error: unknown strategy 'Foo'` | Strategy class name typo or new class not registered in `STRATEGY_REGISTRY` | The registry rebuilds from `lib.analytics.strategies.ALL_STRATEGIES` at import — add new classes there, never to the build script |
| `data/backtests/walkforward/<date>/<strategy>.json` is missing | The build block raised mid-run; check the manifest's `artifacts` list and stderr for the strategy name | Re-run with `--strategies <name>` only, plus `--quiet` removed for verbose output |
| `decompose_by_regime` returns `n_labelled=0` | Regime feed missing or no overlap with the test-period dates | Run `python3 -m services.cross_asset.run` first; or pass an inline `labels` dict |

## What this does **not** do

- **Does not run live trades.** The whole layer is read-only over OHLCV.
- **Does not call any LLM.** No Telegram messages, no Hermes invocations,
  no Kimi / Gemini / Claude. Pure stdlib + analytics modules.
- **Does not modify** `lib/analytics/strategies.py`, `backtest.py`,
  `backtest_engine.py`, `risk_engine.py`, or `deflated_sharpe.py`. Those
  are read-only inputs to this lane. Tested explicitly via
  `test_deflated_does_not_mutate_base_module`.
- **Does not own a LaunchAgent.** Operators schedule the build step
  themselves, or extend the existing `backtest-sweep` scheduled task.
- **Does not touch the dashboard.** A future Lane wires the artifacts in.

## Verification (six-command block)

Mirror the verification used to land this lane:

```bash
cd ~/Code/_worktrees/sapphire-walkforward
python3 -m ruff check lib/analytics/walkforward/ services/walkforward/ \
    plugins/claw-sapphire/tools/walkforward.py \
    plugins/claw-sapphire/tools/internal/walkforward.py \
    tests/unit/test_walkforward_engine.py \
    tests/unit/test_walkforward_regime_decomp.py \
    tests/unit/test_walkforward_deflated_sharpe.py \
    plugins/claw-sapphire/tests/test_walkforward.py
python3 -m pytest tests/unit/test_walkforward_engine.py \
    tests/unit/test_walkforward_regime_decomp.py \
    tests/unit/test_walkforward_deflated_sharpe.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_walkforward.py -q
python3 scripts/validate_tool_registry.py
python3 -m services.walkforward.build --strategies RegimeAwareRSI \
    --horizons 90 --train 60 --test 20 --bars-source synthetic --quiet
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/walkforward.py
python3 -m pytest tests/unit/test_dashboard_walkforward_results.py -q
```

All seven should pass with zero failures, and the build step should write a
`data/backtests/walkforward/<today>/RegimeAwareRSI.json`.

## Roll-back

The lane is purely additive. To revert:

```bash
git revert <commit-sha>
```

…or delete the new files (`lib/analytics/walkforward/`,
`services/walkforward/`, `plugins/claw-sapphire/tools/walkforward.py`,
`plugins/claw-sapphire/tools/internal/walkforward.py`,
the four test files, the two doc files) and remove the `walkforward`
entry from `infra/tool-registry.yaml`. Nothing in the upstream
`lib/analytics/` modules changed, so revert is safe at any time.

## See also

- `docs/products/walkforward-and-regime-0.1.0.md` — design doc for this lane.
- `docs/handoffs/codex-megaprompt-tranche-5-compound-edge-2026-04-29.md` —
  prior tranche (compound-edge sweep) for context on the strategies being
  tested here.
- `docs/handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md` — the
  cross-asset regime classifier this lane consumes.
- `lib/analytics/cpcv.py` — the Combinatorial Purged CV cousin (read-only
  reference; lane 5 mirrors its purge/embargo concepts).
