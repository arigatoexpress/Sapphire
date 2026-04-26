# Bearish-Direction Prediction Asymmetry — Research Design Doc

**Date:** 2026-04-26
**Status:** Layer A and Layer C shipped behind default-off env flags. Layer B (strategy short emission) remains proposed.
**Owner:** Trading critical path (CODEOWNERS-gated)
**Decision history:** Layer C (asymmetric threshold) selected on 2026-04-26 — see Section 8. Layer A (chain factors into `predict.py`) shipped 2026-04-26 — see Section 9.

## Section 8. Decision and Layer C delivery

The reviewer chose **Option B** in Section 7 — ship Layer C (asymmetric threshold) behind a feature flag, defer Layers A and B until a CPCV-grounded backtest harness exists.

What landed:

- `plugins/claw-sapphire/tools/internal/predict.py` exposes `classify_direction(net, *, bull_threshold, bear_threshold)` as a pure function, plus `_resolve_threshold(env_var, default)` that reads two env vars:
  - `SAPPHIRE_PREDICT_BULL_THRESHOLD` (default `1.5`)
  - `SAPPHIRE_PREDICT_BEAR_THRESHOLD` (default `1.5`)
- Default behavior is unchanged: thresholds are symmetric ±1.5, identical to the legacy inline rule. The flag is opt-in.
- Operator playbook: setting `SAPPHIRE_PREDICT_BEAR_THRESHOLD=2.5` in the LaunchAgent env raises the bar so an MA-down-only signal (net ≈ -2.0, the dominant false-bear pattern in §2.2) classifies as neutral instead of bearish. Setting it ≥ 3.0 requires at least two bear factors.
- 15 unit tests in `plugins/claw-sapphire/tests/test_predict.py` cover: default-symmetric behavior, asymmetric-threshold suppression of MA-only false bears, env parsing fallbacks (unset / blank / non-numeric / non-positive / valid).

What is **not** in this delivery (still proposed in §4):

- Layer A — chain factors (funding rate, OI) into `predict.py`.
- Layer B — real `direction="short"` emission across `RegimeAwareRSI`, `MultiTFMomentum`, `CorrelationBreakout`, `SapphireComposite`. The trading critical path remains long/flat-only on these strategies.

Subsequent delivery (PR scaffolding the harness, no critical-path changes):

- `lib/analytics/backtest_harness.py` exposes `HarnessConfig`, `run_harness`,
  and a CLI matching the §4.5 gate. Acceptance defaults are conservative
  (`total_trades >= 30`, `mean_sortino >= 0.5`, `deflated_sharpe >= 0`,
  `max_drawdown_pct <= 35.0`). The harness reads CSV from
  `data/backtests/<symbol>/<timeframe>/*.csv`; those files are **not** in the
  repo, so the harness exits WARN (10) until they are populated. See §4.5 for
  the data gap discussion.

Operator default for the production LaunchAgent has **not** been changed. The flag is staged; the historical accuracy snapshot still applies until the operator opts in.

## 1. Background

The README rewrite in PR #203 (commit `9d223b4b`) surfaced a sharp asymmetry in the
live forward-tested 6-factor TA prediction snapshot:

| Direction | Scored | Correct | Accuracy |
|---|---:|---:|---:|
| Bullish | 19 | 14 | 73.7 % |
| Neutral | 9 | 7 | 77.8 % |
| **Bearish** | **8** | **1** | **12.5 %** |
| Overall | 36 | 22 | 61.1 % |

Per-symbol breakdown: BTC 83.3 % (10/12), ETH 50.0 % (6/12), SOL 50.0 % (6/12).

The README rewrite (`README.md:259-267`) attributes the bear-direction miss to
`MultiTFMomentum` underweighting bear-confirming on-chain signals (funding rate,
open interest). This document verifies that hypothesis against the raw data and
proposes a concrete, testable fix.

## 2. Evidence

### 2.1 Statistical significance

Wilson 95% confidence intervals on the raw rates (`scipy`-free closed form):

| Direction | $\hat{p}$ | 95 % Wilson CI | $n$ |
|---|---:|---:|---:|
| Bear  | 0.125 | [0.0224, 0.4709] | 8  |
| Bull  | 0.737 | [0.5121, 0.8819] | 19 |
| Neutral | 0.778 | [0.4526, 0.9368] | 9 |

Two-sample comparison (bear vs. bull):

- **Two-proportion z-test:** $z = -2.922$, two-sided $p = 0.0035$.
- **Fisher's exact (small-$n$ robust):** two-sided $p = 0.0085$.

Both reject $H_0: p_\text{bear} = p_\text{bull}$ at $\alpha = 0.05$. The bear
miss is not noise — it is a real, statistically significant asymmetry, even at
$n = 8$. (CI is wide; we lack power to discriminate $12.5\%$ from, say, $25\%$,
but we can rule out bear performing as well as bull.)

### 2.2 Per-call inspection

All eight scored bear calls in `data/trading_predictions.jsonl`:

| ts | sym | RSI | MA | MACD | BB | sig $\uparrow$/$\downarrow$ | net | move from entry | correct |
|---|---|---:|---|---|---|---:|---|---:|---|
| 2026-04-07 02:58 | SOL | 41.7 | bearish | none | lower_half | 1/3 | _none_ | +0.09 % | F |
| 2026-04-09 02:14 | BTC | _none_ | _none_ | _none_ | _none_ | _none_ | _none_ | +1.41 % | F |
| 2026-04-09 02:14 | ETH | _none_ | _none_ | _none_ | _none_ | _none_ | _none_ | +1.38 % | F |
| 2026-04-09 02:14 | SOL | _none_ | _none_ | _none_ | _none_ | _none_ | _none_ | +2.03 % | F |
| 2026-04-09 20:51 | SOL | 45.8 | bearish | none | upper_half | **3/1** | **bullish** | -1.14 % | T |
| 2026-04-09 23:50 | SOL | 43.6 | bearish | none | lower_half | 2/2 | neutral | +1.13 % | F |
| 2026-04-10 12:55 | SOL | 52.9 | bearish | none | upper_half | **4/1** | **bullish** | +0.89 % | F |
| 2026-04-11 23:39 | SOL | 56.9 | bearish | none | upper_half | **4/1** | **bullish** | +0.02 % | F |

(The three rows with `_none_` features are legacy `momentum-only`
predictions written before the multi-factor predictor landed — they are scored
but they do not carry the post-refactor TA fields.)

Three observations dominate:

1. **6 of 8 bears were on SOL.** No bear was issued on BTC after the legacy
   batch, and ETH had only one. The asymmetry is essentially a SOL story
   layered on top of a small-sample issue.
2. **Three of five full-feature bear calls had $\text{signals\_bullish} >
   \text{signals\_bearish}$ in the underlying ensemble (4/1, 4/1, 3/1)** — the
   TA scanner that fed the predictor was net-bullish, but `predict.py` flipped
   to bearish anyway. This happens because the
   [`predict.py:60-138`](../../plugins/claw-sapphire/tools/internal/predict.py#L60-L138)
   factor weights give `MA↓` a 2.0 weight (vs. 0.5–1.5 for the other
   single-component bear factors), so a bearish 7/20 SMA cross plus a high
   `volume_ratio > 1.5` pulls $\text{net} \le -2.0$ even when RSI / MACD / BB
   are all neutral or bullish.
3. **Average move-from-entry for bears was around $+0.7\%$** (range: $+0.02\%$
   to $+2.03\%$, with one $-1.14\%$ winner). The bears were not catastrophically
   wrong — they were marginally wrong in a market with persistent mild positive
   drift. A scoring rule that asks "did price go down at all?" punishes any
   non-negative move regardless of magnitude.

### 2.3 Pipeline citations

| Concern | File | Lines |
|---|---|---:|
| Scorer (this is what computes the snapshot) | `lib/analytics/prediction_accuracy.py` | 44–88 |
| Bear scoring rule (`current < entry`, no tolerance) | `plugins/claw-sapphire/tools/internal/predict.py` | 262–276 |
| 6-factor decision rule (where bear gets fired) | `plugins/claw-sapphire/tools/internal/predict.py` | 60–138 |
| Threshold (symmetric `±1.5`) | `plugins/claw-sapphire/tools/internal/predict.py` | 127–133 |
| TA `net_signal` (8 components, no funding/OI) | `plugins/claw-sapphire/lib/technical_analysis.py` | 254–299 |
| `MultiTFMomentum` bear branch returns `flat`, not `short` | `lib/analytics/strategies.py` | 337–362 |
| `FundingRateContrarian` (only strategy that shorts) — uses 3-day price as funding _proxy_, not actual funding | `lib/analytics/strategies.py` | 233–266 |
| `SapphireComposite` long-only (no bear emission at all) | `lib/analytics/strategies.py` | 369–474 |
| `RegimeAwareRSI` long/flat only | `lib/analytics/strategies.py` | 174–227 |
| `CorrelationBreakout` long/flat only | `lib/analytics/strategies.py` | 272–313 |
| GMM regime classifier (does not gate by direction) | `lib/analytics/regime.py` | 149–245 |
| Funding-rate fetch exists | `lib/chain/intelligence.py` | 150–164 (Binance), `lib/chain/sources.py` 367–433 (Hyperliquid funding + OI) |
| Forecast aggregator consensus rules | `lib/analytics/forecast.py` | 152–212 |

The funding/OI surfaces (`_fetch_binance_funding`, `HyperliquidClient.meta_and_asset_ctxs`,
`HyperliquidClient.funding_history`) **do exist** but are consumed only by
`market_sentiment.py` and `lib/chain/intelligence.py` — the prediction path in
`predict.py` and the strategy path in `strategies.py` ignore them entirely.

## 3. Hypothesis (ranked by evidence)

### H1 — Bear is a structural under-coverage problem in the prediction stack (strong)

The README hypothesis is directionally correct but understates the scope. It is
not just `MultiTFMomentum`; **four of five** strategies in `lib/analytics/strategies.py`
have no `short` branch at all, and `MultiTFMomentum`'s bear case explicitly
returns `Decision(direction="flat")` rather than `direction="short"`
(`strategies.py:361`). The only short emitter is `FundingRateContrarian`, and
it uses 3-day price momentum as a _proxy_ for funding rather than the real
funding-rate surface that is already available in `lib/chain/intelligence.py:150`
and `lib/chain/sources.py:367`. So when the predictor calls `bearish`, no
downstream strategy is even capable of trading that view in confirmation —
which means the only signal in the loop is `predict.py`'s own naive heuristic.

**Evidence weight:** High. Direct from code inspection, not statistical inference.

### H2 — Bear calls fire on counter-trend exhaustion alone, with no momentum-context veto (strong)

The 6-factor scorer in `predict.py:60-138` triggers `bearish` whenever
$\text{bull\_score} - \text{bear\_score} < -1.5$. Looking at the five
full-feature bear calls, the dominant negative contribution is **always** `MA↓`
(weight 2.0) coming from a 7/20 SMA cross — a slow lagging indicator. RSI was
in the 41–57 range across all five (neither oversold nor overbought),
MACD cross was `none` for all five, and BB position was lower or upper half
(no `above_upper`/`below_lower` extreme). So the bear was effectively a
single-factor call dressed up as multi-factor. A volume ratio above 1.5 amplifies
this with another $+0.5$ to whichever side is leading (`predict.py:108-113`),
which is why the late-cycle SOL bears collected even more bear weight without
any genuine momentum confirmation.

**Evidence weight:** High. Three of five bears fired with `net_signal == bullish`
in the underlying TA scanner — the predictor disagreed with its own ensemble.

### H3 — Macro drift means the symmetric ±1.5 threshold is mis-calibrated (medium)

Bull accuracy 73.7 % combined with neutral accuracy 77.8 % suggests the model
has a positive drift baked into its base rate; the underlying market over the
window was in a mild up-regime. Under positive drift, a bear call needs
strictly more evidence to be correct than a bull call needs. The current
$\pm 1.5$ threshold (`predict.py:127-133`) is symmetric. An asymmetric threshold
(say bear requires $\text{net} \le -2.5$ rather than $\le -1.5$) would
mechanically suppress the marginal bears that collectively scored $+0.02\%$,
$+0.09\%$, $+0.89\%$, $+1.13\%$, $+1.38\%$, $+1.41\%$, $+2.03\%$ — none of those
moves was big enough to overcome drift, but all were inside the current bear
gate.

**Evidence weight:** Medium. The fix is mechanical and easy, but it doesn't
address the root cause (lack of bear-confirming chain signal); it just makes
the predictor reluctant to fire bears at all. That is a defensible band-aid
while H1 / H2 are designed properly.

### H4 — Sample size is too small to act on aggressively (medium-low)

$n = 8$ scored bears is a tiny sample. The Wilson CI is $[0.022, 0.471]$ — the
true bear hit-rate could plausibly be 47 % rather than 12.5 %. However, two
independent significance tests reject equality with bull at $\alpha = 0.05$,
so the asymmetry is not just sampling noise: even the upper end of the bear CI
sits below the lower end of the bull CI ($0.471 < 0.512$). What we _cannot_ do
yet is point-estimate the post-fix bear hit-rate with any precision, which is
why the proposed fix in §4 is gated on a backtest, not on a live cutover.

**Evidence weight:** Medium-low. The asymmetry is real; the magnitude is
imprecise.

### H5 — GMM regime classifier biases the conditional (rejected)

The GMM classifier in `lib/analytics/regime.py` is only consumed by the
`SignalEnhancer` integration path (`get_regime` cache). It is **not** wired
into `predict.py` or the strategies' bear/short branches at all. So it cannot
be the source of the asymmetry; the asymmetry exists upstream of any regime
gating.

**Evidence weight:** Rejected — code inspection rules this out.

## 4. Proposed Fix (sketch only — no code in this PR)

The fix is staged in three layers, each independently testable. All changes
are inside CODEOWNERS-gated trading critical path; none of them ship without
backtest evidence.

### 4.1 Layer A — wire chain funding/OI into the predictor (addresses H1, H2)

Add a sixth factor to `action_predict()` in `predict.py` that consumes the
existing chain helpers:

```python
# plugins/claw-sapphire/tools/internal/predict.py — sketch, do not commit
from lib.chain.intelligence import _fetch_binance_funding
from lib.chain.sources import HyperliquidClient

# inside action_predict(), after the existing 6 factors:
binance_sym = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}.get(sym)
funding_pct_8h = _fetch_binance_funding(binance_sym) if binance_sym else None
hl_ctx = _hl_ctx_cached().get(sym)  # 5-min cache wrapper around HyperliquidClient

if funding_pct_8h is not None:
    if funding_pct_8h > 0.05:        # crowded long → bear-confirming
        bear_score += 1.0
        factors.append(f"Fund{funding_pct_8h:+.3f}%")
    elif funding_pct_8h < -0.02:     # crowded short → bull-confirming
        bull_score += 1.0
        factors.append(f"Fund{funding_pct_8h:+.3f}%")

if hl_ctx and hl_ctx.open_interest > 0 and hl_ctx.prev_day_px:
    oi_change_pct = ...  # need 24h-prior OI; persist via /data/chain/funding_oi.jsonl
    if oi_change_pct > 5 and funding_pct_8h and funding_pct_8h > 0:
        bear_score += 0.5  # rising OI + positive funding = late-cycle long crowding
```

Persist a daily snapshot at `data/chain/funding_oi.jsonl` so OI-change can be
computed without needing live history every call. A separate backfill script
under `scripts/research/` populates this.

### 4.2 Layer B — make bear branches in `strategies.py` actually short (addresses H1)

Update `MultiTFMomentum.on_bar` (`lib/analytics/strategies.py:354-362`) so the
bear branch emits `Decision(direction="short", ...)` instead of `flat`. Same
treatment for `RegimeAwareRSI` (add a stricter bear branch under `RISK_OFF`)
and `CorrelationBreakout` (a high-correlation + RSI > 65 short). Each of these
gets its own backtest before any of them lands — Sortino must beat the
long-only baseline on at least two of the three majors, with no strategy worse
than $-1\sigma$ on Calmar.

### 4.3 Layer C — asymmetric threshold (addresses H3)

Make the `predict.py:127-133` threshold asymmetric and parametric:

```python
BULL_THRESHOLD = float(os.environ.get("PREDICT_BULL_THRESHOLD", "1.5"))
BEAR_THRESHOLD = float(os.environ.get("PREDICT_BEAR_THRESHOLD", "2.5"))

if net > BULL_THRESHOLD:
    direction = "bullish"
elif net < -BEAR_THRESHOLD:
    direction = "bearish"
else:
    direction = "neutral"
```

Default $2.5$ for bears was chosen so all five marginal bears in §2.2
($\text{net} \in \{-2.0, -2.0, -2.5, -2.5, -2.5\}$) would have either flipped
to neutral or stayed marginal. Note the boundary case at exactly $-2.5$: with
a strict inequality `<`, those calls become neutral. Worth confirming during
review whether we want strict or non-strict.

### 4.4 Test scaffolding

New unit tests (no production code yet — these go in alongside Layer A):

- `tests/unit/test_predict_chain_factors.py`
  - `test_high_funding_adds_bear_score` — funding $0.08\%$ → bear factor $+1.0$
  - `test_negative_funding_adds_bull_score` — funding $-0.05\%$ → bull factor $+1.0$
  - `test_funding_unavailable_does_not_crash` — `_fetch_binance_funding` returns `None`
  - `test_oi_change_rising_amplifies_bear` — OI up $+8\%$ + funding $+0.06\%$ → extra bear $+0.5$
  - `test_chain_factors_are_pure_when_disabled` — `PREDICT_DISABLE_CHAIN=1` skips fetches
- `tests/unit/test_predict_thresholds.py`
  - `test_default_thresholds_match_legacy_for_bull`
  - `test_bear_requires_higher_evidence`
  - `test_threshold_env_overrides_take_effect`
- `tests/unit/test_strategies_short_emission.py`
  - `test_multi_tf_bear_branch_emits_short`
  - `test_regime_aware_rsi_bear_branch_emits_short_in_risk_off`
  - `test_correlation_breakout_emits_short_when_correlated_overbought`

Layer A tests must pass with `_fetch_binance_funding` monkeypatched (no live
HTTP) and with the existing `tests/conftest.py` fixtures unchanged.

### 4.5 Backtest plan

Before any Layer lands, run the strategy sweep and the predictor offline through
the CPCV-grounded harness at [`lib/analytics/backtest_harness.py`](../../lib/analytics/backtest_harness.py).

1. **Window:** 2025-04-01 → 2026-04-25 (one year, includes both up- and
   down-leg regimes; longer than the 90-day default in `lib/analytics/run_strategies.py`).
2. **Tooling:** the harness composes the existing `cpcv_splits`, `BacktestEngine`,
   and `deflated_sharpe_ratio` primitives — it does not duplicate them. Invoke
   per-strategy via:

   ```bash
   python3 -m lib.analytics.backtest_harness \
       --strategy lib.analytics.strategies:RegimeAwareRSI \
       --start 2025-04-01 --end 2026-04-25 \
       --symbols BTC-USD,ETH-USD,SOL-USD
   ```

   Exit codes follow the same `0 / 10 / 20` (PASS / WARN / FAIL) contract as
   `scripts/ops/compare_*_artifacts.py`. The pre/post Layer-A comparison is one
   harness run before and after the chain-factor branch, persisted to
   `data/backtests/strategies/bearish_asymmetry/`.
3. **Universe:** BTC, ETH, SOL on daily bars (same as current sweep).
4. **Metrics & acceptance gates** (all must hold for the change to merge — these
   are the conservative §4.5 thresholds the harness encodes):
   - `total_trades >= 30` across all CPCV folds (insufficient evidence below this).
   - `mean_sortino >= 0.5` — the §3 baseline says the system has positive drift,
     so we require the strategy to actually beat zero on a downside-aware metric.
   - `deflated_sharpe >= 0` — the Bailey & López de Prado 2014 multiple-testing
     deflation must remain non-negative; `lib/analytics/deflated_sharpe.py` does
     the work.
   - `max_drawdown_pct <= 35.0` — worst-fold drawdown ceiling.
   - Bearish-direction precision (TP / (TP+FP)) goes from $0.125$ to $\ge 0.40$
     on the holdout half of the window. The harness does not currently compute
     direction-conditioned precision; this is the manual sanity check the
     reviewer runs alongside the harness output.
   - Bull-direction precision degrades by $\le 5$ percentage points (stays
     $\ge 0.687$). This is the "do no harm" gate.
5. **Walk-forward / CPCV validation:** the harness uses
   `cpcv_n_groups=6, cpcv_test_size=2, cpcv_embargo=0.02` by default
   (15 splits per symbol, 2 % embargo). Reject if the bear-precision uplift
   fails to replicate on $\ge 70\%$ of folds.
6. **Data gap (honestly stated):** the harness reads OHLCV from
   `data/backtests/<symbol>/<timeframe>/*.csv`. Those files do not exist in the
   repo today — the trading critical path uses live yfinance via
   `lib.analytics.backtest_engine.fetch_ohlcv`, which is non-deterministic in
   CI. When the harness cannot find data for any requested symbol it returns a
   `HarnessResult` with `acceptance.passes_section_4_5 == False` and
   `reasons=["no historical data"]`, and the CLI exits **WARN (10)** rather
   than FAIL. Populating `data/backtests/<symbol>/<timeframe>/*.csv` with the
   §4.5 reference window (one daily-bars CSV per BTC/ETH/SOL ticker) is a
   prerequisite for any Layer A or B PR to actually trip the gate; the
   bootstrap script for that snapshot is **not** in this PR.

If H1 / H2 fail the backtest gate but H3 (the threshold change) passes alone,
ship only H3 as a defensive measure and reopen the doc.

## 5. Risks

1. **Over-correction.** Tightening the bear gate too far (Layer C with a $-3.0$
   threshold, say) leaves the model unable to call bear at all. The risk is
   not zero hits — it's a missed regime change when the macro drift inverts.
   Mitigation: ensure the parameter is env-overridable, log every gate decision,
   add a watchdog tool that alerts if no bear/short signal has fired in $> N$
   days while the backtest baseline expected one.
2. **False bear amplification from funding alone.** Funding rate spikes are
   noisy intraday. Adding a $+1.0$ bear factor for $\text{funding} > 0.05\%$
   could mechanically flip neutral into bear. Mitigation: require funding to
   be above threshold for $\ge 24h$ (rolling window) before counting; reuse
   the cache layer in `lib/chain/sources.py:50-65`.
3. **Liquidity / SOL fragility.** All but one of the bear misses were SOL.
   SOL has thinner perpetual liquidity than BTC/ETH, so funding signal there
   is noisier. Consider a per-symbol weight on the funding factor (BTC $1.0$,
   ETH $0.7$, SOL $0.4$) until we have enough samples to calibrate per-asset.
4. **Backtest over-fitting.** Both the symmetric-to-asymmetric threshold and
   the chain factor weights are tunable. With $n = 8$ bear observations the
   risk of fitting noise is high. The CPCV + DSR gate in §4.5 is the primary
   defense; if either fails the proposal goes back to research.
5. **Chain-fetch latency in the production path.** `_fetch_binance_funding` is
   stdlib `urllib` with a 6 s timeout. Failures should _not_ block prediction;
   the test `test_funding_unavailable_does_not_crash` enforces this. Wire the
   factor as additive only — never gate the entire prediction on chain
   availability.
6. **Strategy `short` emission interacts with paper-trading sizing.** The
   `paper_trader.py` and signal logger pipelines were written assuming
   long-biased flow. Adding short emissions from `MultiTFMomentum` /
   `RegimeAwareRSI` / `CorrelationBreakout` could surface latent bugs in stop /
   take-profit math (`backtest_engine.py` formulas in `BacktestEngine.run`,
   `strategies.py:548-550`). This is in scope for Layer B's test plan.

## 6. Alternatives considered (and rejected)

- **Drop bear predictions entirely.** Cleanest; but loses information when
  the regime actually inverts. Rejected because users / Telegram subscribers
  rely on directional output, and the fix is straightforward.
- **Lower the scorer's tolerance.** `predict.py:268-273` uses a strict
  `current < entry` for bear-correctness. We could add a tolerance band
  (e.g. correct if `current < entry * 1.005`). Rejected because it is a
  reporting workaround, not a model fix — accuracy on paper goes up, real PnL
  on a paper short would still be flat.
- **Replace the 6-factor scorer with the GMM regime classifier.** Bigger
  surface area; orthogonal to the asymmetry. Track in a separate doc.

## 7. Decision required from human reviewer

The reviewer needs to choose one of the following paths before any code lands:

1. **(A) Full stack — Layer A + B + C, gated by §4.5 backtest.** Highest
   ceiling, longest path to land. Implement chain factors, fix strategy
   bear branches, switch to asymmetric threshold. Estimated 3 – 5 working
   sessions plus backtest cycles.
2. **(B) Defensive band-aid — Layer C only.** Asymmetric threshold ships
   immediately behind a feature flag (`PREDICT_BEAR_THRESHOLD`). Mechanical;
   accuracy headline numbers go up by suppressing marginal bears. Does not
   address H1 / H2 root cause. Estimated 1 session.
3. **(C) Research only — formalize the doc, schedule the backtest, don't ship
   yet.** Build the chain-factor backtest harness in `lib/analytics/run_strategies.py`
   without touching production scoring. Re-decide between (A) and (B) once the
   numbers are in.
4. **(D) Reject — accept the bear miss as a feature of a long-biased system.**
   Drop bear-direction from the README scorecard rather than try to fix it.

This PR adds only this design doc — Sections 1 – 6 above. No production code
is modified.

## 8. References (commits, PRs, snapshots)

- README rewrite that surfaced the asymmetry — PR #203, commit `9d223b4b`,
  see [`README.md:248-267`](../../README.md#L248-L267).
- Snapshot data: `data/trading_predictions.jsonl`, generated 2026-04-26
  via `lib/analytics/prediction_accuracy.report()`.
- Codepaths cited (line ranges):
  - [`lib/analytics/prediction_accuracy.py:44-88`](../../lib/analytics/prediction_accuracy.py#L44-L88)
  - [`lib/analytics/forecast.py:152-212`](../../lib/analytics/forecast.py#L152-L212)
  - [`lib/analytics/strategies.py:174-227`](../../lib/analytics/strategies.py#L174-L227),
    [`233-266`](../../lib/analytics/strategies.py#L233-L266),
    [`272-313`](../../lib/analytics/strategies.py#L272-L313),
    [`337-362`](../../lib/analytics/strategies.py#L337-L362),
    [`369-474`](../../lib/analytics/strategies.py#L369-L474)
  - [`lib/analytics/regime.py:149-245`](../../lib/analytics/regime.py#L149-L245)
  - [`lib/chain/intelligence.py:150-164`](../../lib/chain/intelligence.py#L150-L164)
  - [`lib/chain/sources.py:367-433`](../../lib/chain/sources.py#L367-L433)
  - [`plugins/claw-sapphire/tools/internal/predict.py:49-189`](../../plugins/claw-sapphire/tools/internal/predict.py#L49-L189),
    [`262-276`](../../plugins/claw-sapphire/tools/internal/predict.py#L262-L276)
  - [`plugins/claw-sapphire/tools/internal/signal_generator.py:66-225`](../../plugins/claw-sapphire/tools/internal/signal_generator.py#L66-L225)
  - [`plugins/claw-sapphire/lib/technical_analysis.py:254-299`](../../plugins/claw-sapphire/lib/technical_analysis.py#L254-L299)
- Statistical methods used: Wilson score interval (Wilson 1927); two-proportion
  z-test; Fisher's exact test (closed-form, hypergeometric tail).

## Section 9 — Layer A delivery

Layer A (chain factors into `predict.py`) shipped on 2026-04-26 behind a
default-off env flag. The §4.5 backtest harness landed in PR #212 and
remains the gate for any operator-side rollout — until the harness has
`data/backtests/<symbol>/<timeframe>/*.csv` populated, the production default
(`SAPPHIRE_PREDICT_USE_CHAIN_FACTORS` unset, equivalent to `0`) keeps the
legacy six-factor scoring exactly as it was. **The production default is
unchanged.**

### What landed

- Pure function `chain_factor_deltas(symbol, *, funding_z, oi_change_pct)` in
  `plugins/claw-sapphire/tools/internal/predict.py`. Returns
  `(bull_delta, bear_delta, factors)` — no IO, no network, no exceptions in
  any input shape. Used both directly in `action_predict` and exposed for
  unit testing.
- Best-effort adapter `_read_chain_features(symbol)` in the same file. Reads
  `data/intelligence/latest/chain.json` (the artifact written every 15 min
  by `services.pipeline.chain_refresh`), tolerates three plausible schemas
  (`funding.perps[]`, top-level `perps[]`, `per_symbol[<sym>]`), returns
  `(None, None)` on any error path. Stdlib only — no pandas/numpy.
- New env flag `SAPPHIRE_PREDICT_USE_CHAIN_FACTORS`. Default `0` (off).
  Accepted truthy values: `1`, `true`, `yes`, `on` (case-insensitive). When
  on, `action_predict` reads `(funding_z, oi_change_pct)` for each symbol
  via the adapter and applies the deltas to `bull_score` / `bear_score`
  **before** the threshold classification. When the adapter returns
  `(None, None)` for a symbol — missing file, malformed JSON, symbol not
  present, non-numeric values — the deltas are not applied and that
  symbol's record is bit-for-bit identical to the legacy path.
- Reasoning string carries `FundZ{z:+.1f}↑/↓` and `OI{pct:+.1f}%↑/↓` labels
  per applied factor so post-hoc inspection of `data/trading_predictions.jsonl`
  can attribute each call to its inputs.

### Env var contract

| Env var | Default | When set | Effect |
|---|---|---|---|
| `SAPPHIRE_PREDICT_USE_CHAIN_FACTORS` | unset (= `0`) | `1`/`true`/`yes`/`on` | Enables the chain-factor read path in `action_predict`. |
| `SAPPHIRE_PREDICT_BULL_THRESHOLD` | `1.5` | float > 0 | Layer C bull cutoff. Unchanged. |
| `SAPPHIRE_PREDICT_BEAR_THRESHOLD` | `1.5` | float > 0 | Layer C bear cutoff. Unchanged. |

Operators opt in by setting the chain-factor flag in the LaunchAgent env
**after** the §4.5 reference data is in place. Roll back by unsetting the
flag — no code revert needed.

### Factor delta table

Every chain factor contributes at most `0.5` so two factors at full extension
sum to `1.0`, well below the `1.5` legacy threshold. A single factor cannot
single-handedly flip a direction.

| Factor | Trigger | Effect | Cap |
|---|---|---|---|
| Funding z-score (crowded longs) | `funding_z > +1.5` | `bear_delta += 0.5` | `0.5` |
| Funding z-score (crowded shorts) | `funding_z < -1.5` | `bull_delta += 0.5` | `0.5` |
| Funding z-score (noise band) | `|funding_z| <= 1.5` | (none) | — |
| OI 24h change (amplifies bear) | `oi_change_pct > +5.0` AND bear context dominates | `bear_delta += 0.5` | `0.5` |
| OI 24h change (amplifies bull) | `oi_change_pct > +5.0` AND bull context dominates | `bull_delta += 0.5` | `0.5` |
| OI 24h change (no lean) | bull and bear deltas equal (incl. both zero) | (none) | — |

OI is amplification-only, by design: a 5% OI expansion only matters in the
context of an existing funding lean, mirroring the §4.1 sketch.

### Data file the adapter reads

`data/intelligence/latest/chain.json` — the chain refresh artifact. Schema
is intentionally tolerant; the adapter probes (in order):

1. `funding.perps[]` — list of `{coin, funding_z, oi_change_pct, ...}`
   (the shape `services.pipeline.chain_refresh.run` is most likely to emit;
   `coin` matched case-insensitively).
2. `perps[]` — same shape, top-level.
3. `per_symbol[<SYM>]` — `{funding_z, oi_change_pct}` keyed dict (forward-
   compat shape if a future refresh writes per-symbol entries directly).

If a candidate uses `funding_zscore` instead of `funding_z`, or
`open_interest_change_pct` instead of `oi_change_pct`, both are accepted.

### Production default unchanged

With `SAPPHIRE_PREDICT_USE_CHAIN_FACTORS` unset or set to `0`, `predict.py`
produces the same record (modulo the call timestamp) as the legacy six-factor
code path. The unit test suite at
`plugins/claw-sapphire/tests/test_chain_factors.py` includes an end-to-end
equivalence check (`test_action_predict_baseline_record_matches_with_and_without_flag`)
that runs `action_predict` twice — once with the flag unset, once with the
flag set but the adapter patched to return `(None, None)` — and asserts the
two records are identical. The §4.5 backtest harness gate still applies
before any operator-side rollout.

### Layer A test coverage

24 tests in `plugins/claw-sapphire/tests/test_chain_factors.py`:

- `chain_factor_deltas` — directional symmetry, threshold boundaries, OI
  amplification rules, hard caps, both-`None` short-circuit (10 tests).
- `_read_chain_features` — missing file, malformed JSON, symbol absent,
  primary schema, future schema, empty file, non-JSON-shape, non-numeric
  values (8 tests).
- `action_predict` env-flag wiring — flag unset (adapter must not be
  called), flag on with patched features (deltas applied), flag on with
  empty adapter (legacy record), flag on with one-sided adapter return
  (no deltas), flag explicitly `0`, end-to-end baseline equivalence
  (6 tests).
