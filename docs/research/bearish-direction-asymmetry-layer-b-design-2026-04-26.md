# Bearish-Direction Asymmetry — Layer B Design Doc

**Date:** 2026-04-26
**Status:** Research only. No production code changes in this PR. Layer B remains gated on the §4 backtest.
**Owner:** Trading critical path (CODEOWNERS-gated)
**Predecessor:** [`docs/research/bearish-direction-asymmetry-2026-04-26.md`](./bearish-direction-asymmetry-2026-04-26.md)
**Related shipped layers:** Layer C (asymmetric threshold) — PR #209. Layer A (chain factors) — PR #230. Backtest harness — PR #212.

## Abstract

The bearish-direction asymmetry verified in PR #207 has Layers C and A
landed behind default-off env flags. Layer B remains: real
`direction="short"` emission across `RegimeAwareRSI`, `MultiTFMomentum`,
`CorrelationBreakout`, and `SapphireComposite` in
`lib/analytics/strategies.py`. Today four of those five strategies cannot
trade a bear view at all — `FundingRateContrarian` is the only emitter,
and it uses 3-day price momentum as a proxy for the funding rate rather
than the real on-chain surface that already exists in `lib/chain/`.

This document specifies, per-strategy, where new short branches would
fire, what evidence each requires, what risk rules apply on the short
side, and how the §4.5 CPCV harness in
`lib/analytics/backtest_harness.py` (PR #212) gates the rollout. The
rollout pattern mirrors Layer A: a single environment flag
(`SAPPHIRE_STRATEGIES_ENABLE_SHORT`) defaulting to `0`, opt-in only
after the backtest passes the §4.5 acceptance gate. No code in this PR.

## Section 10 — Layer B short-branch design

### 10.1 Background

The asymmetry was verified in PR #207
([`docs/research/bearish-direction-asymmetry-2026-04-26.md`](./bearish-direction-asymmetry-2026-04-26.md)).
Sections 1–9 of that document are the historical record and are
explicitly immutable in this change set. Recap of the layer status:

| Layer | What | Status | PR |
|---|---|---|---|
| C | Asymmetric `bull` / `bear` thresholds in `predict.py` | shipped, default-off | #209 |
| A | Chain factors (funding z-score, OI change) into `predict.py` | shipped, default-off | #230 |
| B | Real `direction="short"` emission across four strategies | **proposed (this doc)** | — |
| Harness | CPCV-grounded `lib.analytics.backtest_harness` § 4.5 gate | shipped, WARN until OHLCV staged | #212 |

The four strategies that need short branches:

1. `RegimeAwareRSI` — long/flat only ([`lib/analytics/strategies.py:174-227`](../../lib/analytics/strategies.py#L174-L227)).
2. `MultiTFMomentum` — bear branch returns `flat`, not `short` ([`lib/analytics/strategies.py:354-362`](../../lib/analytics/strategies.py#L354-L362)).
3. `CorrelationBreakout` — long/flat only ([`lib/analytics/strategies.py:285-313`](../../lib/analytics/strategies.py#L285-L313)).
4. `SapphireComposite` — long-only `Decision` ([`lib/analytics/strategies.py:469-474`](../../lib/analytics/strategies.py#L469-L474)).

`FundingRateContrarian` already emits `direction="short"` ([`lib/analytics/strategies.py:257-260`](../../lib/analytics/strategies.py#L257-L260))
and is documented in §10.2.5 for completeness — no behavioral change is
proposed for it.

### 10.2 Per-strategy short-branch design

Each subsection lists today's flat-returning branches with file:line
citations against `main` at branch time
(`4b10e2c9 Close out 2026-04-26 evening autonomous window with Layer A landing`),
proposes the new short branch, defines its evidence threshold and exit
rule, and explains the regime gate. Code sketches are illustrative
pseudocode, **not** diffs — implementation is deliberately deferred to a
separate PR.

#### 10.2.1 `RegimeAwareRSI`

**Today's flat-returning branches** ([`lib/analytics/strategies.py:203-226`](../../lib/analytics/strategies.py#L203-L226)):

- Line 211: returns `Decision(direction="flat")` when `regime == "RISK_OFF"` (early-return so the function never sees RSI in RISK_OFF).
- Line 225: returns `Decision(direction="flat")` when `rsi > 70.0` in RISK_ON or TRANSITION (exit-only signal).

**Proposed new short branch.** RSI overbought (`rsi > 70`) is the
mirror of the existing oversold long entry (`rsi < 30`). The current
code treats overbought as flat-only because the strategy was designed
long-biased. We change it to:

- **Trigger:** `regime == "RISK_OFF"` AND `rsi > strict_overbought_threshold`. Default `strict_overbought_threshold = 75.0` (mirror of the RISK_ON/TRANSITION oversold floor of 25 / 30 — symmetry on the high side).
- **Why RISK_OFF only:** the existing strategy already encodes "no new long entries in RISK_OFF" (line 211). The same signal that says "do not buy weakness" supports "consider shorting weakness" — but only when the macro tape itself is bearish. Firing shorts in RISK_ON would short into a confirmed up-trend, which dominates the §2 evidence base.
- **Stricter than long-side:** RISK_OFF is rare; combined with `rsi > 75` it is rarer still. The §3 base rate (positive drift) means a short needs more evidence than a long, hence 75 vs 30 (asymmetric thresholds inside the strategy mirror the §4.3 thresholds at the predictor layer).
- **Exit rule:** mirror the long exit. Today the long branch (line 222) takes profit at `+tp_pct` and stops at `-sl_pct`; the short branch does the inverse. In addition, exit if `regime` flips out of RISK_OFF (regime invalidation acts as a kill).
- **Regime gate:** RISK_OFF only, computed via `_detect_regime` at [`lib/analytics/strategies.py:190-201`](../../lib/analytics/strategies.py#L190-L201) using the same `regime_off_threshold` (BTC 20-day return ≤ −5%).

```python
# illustrative pseudocode — NOT a diff, do not commit
def on_bar(self, window, aux):
    ...
    regime = self._detect_regime(aux.get("btc") or window)
    if regime == "RISK_OFF":
        rsi = _rsi(closes, p.rsi_period)
        if rsi is not None and rsi > 75.0:
            return Decision(direction="short", size=0.4,
                            stop_pct=p.sl_pct * 0.7,  # tighter — see §10.3
                            tp_pct=p.tp_pct)
        return Decision(direction="flat")
    # RISK_ON / TRANSITION path unchanged
```

Notes on size: 0.4 vs the 0.5 long size — short side carries borrow
cost and asymmetric ruin risk (§10.3); we trade smaller until live
evidence accumulates.

#### 10.2.2 `MultiTFMomentum`

**Today's flat-returning branch** ([`lib/analytics/strategies.py:355-361`](../../lib/analytics/strategies.py#L355-L361)):

- Line 355 already computes a fully-formed bear condition: `rsi_fast > 65.0 and closes[-1] > sma20 * 1.02 and weekly_ret > 0.02`.
- Line 361: returns `Decision(direction="flat")` instead of acting on it. This is the single most direct mirror to long emission anywhere in the codebase — three timeframes already agree on bear, the strategy just refuses to trade it.

**Proposed new short branch.** Promote the existing `bear` boolean to
emit `direction="short"`.

- **Trigger:** unchanged — `rsi_fast > 65.0 AND close > 1.02 × sma20 AND 5-day return > +2%`. All three timeframes must agree, mirroring the long entry's "all three: short-term oversold, below daily MA, weekly pullback" rule.
- **Why this is the lowest-risk Layer B promotion:** the bear evaluation is already coded; we are toggling its output, not synthesising new logic. The §4 backtest can therefore isolate the lift of "bear branch shorts vs. bear branch is flat" cleanly per fold.
- **Exit rule:** mirror the long. SL at `entry × (1 + sl_pct)`, TP at `entry × (1 − tp_pct)`. Add a momentum-invalidation exit: if `rsi_fast < 50` mid-trade (i.e. fast oscillator no longer overbought), close at next bar's close.
- **Regime gate:** none added at the strategy level. The three-timeframe agreement (fast oscillator + daily MA + weekly return) is itself the regime check; layering a BTC-regime gate on top would suppress almost every Layer B short, defeating the test.

```python
# illustrative pseudocode — NOT a diff, do not commit
bull = rsi_fast < 40.0 and closes[-1] < sma20 and weekly_ret < 0.0
bear = rsi_fast > 65.0 and closes[-1] > sma20 * 1.02 and weekly_ret > 0.02

if bull:
    return Decision(direction="long", size=0.5,
                    stop_pct=p.sl_pct, tp_pct=p.tp_pct)
if bear:
    return Decision(direction="short", size=0.4,
                    stop_pct=p.sl_pct * 0.7, tp_pct=p.tp_pct)
return None
```

#### 10.2.3 `CorrelationBreakout`

**Today's flat-returning branches** ([`lib/analytics/strategies.py:306-313`](../../lib/analytics/strategies.py#L306-L313)):

- Line 312: returns `Decision(direction="flat")` when `corr < threshold` AND `rsi > 65.0` — currently treated as exit-only.
- Implicit flat: there is no bear branch when correlation is **high** (BTC tightly coupled to SPY) and RSI is overbought. Today the function returns `None` in that branch.

**Proposed new short branch.** A high-correlation environment with an
overbought RSI is the canonical "pile-on" pattern: BTC moving with SPY
both stretched. Two paths:

- **Path A (preferred):** Trigger when `corr > 0.65 AND rsi > 65.0`. The high-correlation gate explicitly separates this from the existing `corr < threshold` (decoupling) branch — it is the inverse setup. Size `0.5`. The §2 evidence in the original doc shows late-cycle SOL pile-ons coincided with high BTC↔SPY correlation; this is precisely the regime the strategy is missing.
- **Path B (rejected — see §10.7 Decision):** Promote the existing line-312 flat branch (`corr < threshold AND rsi > 65`) to a short. Decoupling + overbought is a weaker setup than high-correlation + overbought; firing here risks shorting an idiosyncratic move that the asset itself can carry through, which is exactly the failure mode the long branch (corr < threshold + RSI < 45) exploits in reverse.

**Trigger threshold.** `corr > 0.65` AND `rsi > 65`. The 0.65
correlation cutoff is symmetric with the existing 0.30 decoupling
threshold (rough 1−x mirror against a random ±0.5 walk). RSI 65 is the
weaker of the two bands the existing code already uses — symmetric with
the long entry RSI 45.

**Exit rule.** SL at `entry × (1 + sl_pct)`. TP at `entry × (1 − tp_pct)`.
Regime-invalidation exit: if `corr < 0.50` mid-trade, close at next
bar's close (the "pile-on" condition has resolved).

**Regime gate.** None at the strategy level — high correlation is the
regime gate.

```python
# illustrative pseudocode — NOT a diff, do not commit
corr = _pearson(sym_rets, spy_rets)
rsi = _rsi(closes, p.rsi_period)

if corr < p.corr_threshold:
    # existing decoupling path unchanged
    if rsi < 45.0:
        return Decision(direction="long", size=0.6, ...)
    if rsi > 65.0:
        return Decision(direction="flat")  # unchanged
elif corr > 0.65 and rsi > 65.0:
    return Decision(direction="short", size=0.5,
                    stop_pct=p.sl_pct * 0.7, tp_pct=p.tp_pct)
return None
```

#### 10.2.4 `SapphireComposite`

**Today's flat / no-op branches** ([`lib/analytics/strategies.py:466-474`](../../lib/analytics/strategies.py#L466-L474)):

- Line 466-467: returns `None` when `score < composite_threshold`.
- Line 469-474: only ever returns `direction="long"`. There is no short branch and no bear-side scoring path.

**Two design choices.** The composite scores 0–100 by summing five
positive components. To make it bear-aware we either:

- **Option α (constituent inheritance):** Refactor so the composite delegates direction to its constituents — if at least 3 of the 5 components currently agree on bear (mirror RSI > 70, mom_3d > funding_high, corr > 0.65, multi-TF bear, regime RISK_OFF), emit short. The composite becomes an ensemble vote rather than a unipolar score. Cleaner long-term.
- **Option β (parallel bear score, recommended for Layer B):** Add a `bear_score` accumulator that mirrors the existing `score` but flipped. Each component contributes its bear contribution; emit short when `bear_score > composite_threshold`. Long score and bear score are computed in parallel and the larger one wins (with a tie → flat). Smaller change surface, easier to backtest in isolation.

**Trigger (Option β).** `bear_score > p.composite_threshold` AND
`bear_score > score` (long score). Default `composite_threshold` is
55.0 ([`lib/analytics/strategies.py:122`](../../lib/analytics/strategies.py#L122))
— the same gate is reused on the bear side, so any bear short is at
least as well-evidenced as the long entries the strategy already takes.
Per-component bear contributions:

| Component | Bear contribution |
|---|---|
| Regime | RISK_OFF → +25, TRANSITION → +15 |
| RSI | `rsi > 70` → linear up to +25 (mirror of `rsi < 30`); `rsi < 30` → −5 (mirror penalty) |
| Funding proxy (3-day momentum) | `mom_3d > funding_high` → +20 (mirror); `mom_3d < funding_low` → −5 |
| Correlation | `corr > 0.65` → +15 (mirror of decoupling) |
| Multi-TF | fraction of TFs in bear configuration × 15 |

**Exit rule.** Mirror long. SL at `entry × (1 + sl_pct)`, TP at
`entry × (1 − tp_pct)`. Position size via `_kelly_size`
([`lib/analytics/strategies.py:387-393`](../../lib/analytics/strategies.py#L387-L393))
unchanged in formula; **but** clamp the upper bound to 0.30 (vs 0.50)
on the short side so that a Kelly-implied 0.50 long becomes 0.30 short
— same rationale as §10.3.

**Regime gate.** The regime contribution itself acts as the gate: a
RISK_ON market suppresses bear_score by 25 points (no contribution) and
keeps the bear branch from firing on positive-drift weeks.

```python
# illustrative pseudocode — NOT a diff, do not commit
score = 0.0      # bull score (existing)
bear_score = 0.0  # NEW

# Regime
if regime_mom <= p.regime_off_threshold: bear_score += 25.0
elif regime_mom < p.regime_on_threshold: bear_score += 15.0

# RSI
if rsi > 70.0: bear_score += min(25.0, (rsi - 70.0) * 25.0 / 20.0)

# ... funding, correlation, multi-TF mirrors ...

if max(score, bear_score) < p.composite_threshold:
    return None

if score > bear_score:
    return Decision(direction="long", size=self._kelly_size(), ...)
return Decision(direction="short", size=min(self._kelly_size(), 0.30), ...)
```

Whether to choose Option α or Option β is left as a §10.7 decision
point.

#### 10.2.5 `FundingRateContrarian` (already shorts — documented for completeness)

**Existing short branch** ([`lib/analytics/strategies.py:257-260`](../../lib/analytics/strategies.py#L257-L260)):

```python
if mom_3d > p.funding_high:
    # High simulated funding → crowded long → contrarian short
    return Decision(direction="short", size=0.4,
                    stop_pct=p.sl_pct, tp_pct=p.tp_pct)
```

- **Trigger:** 3-day price momentum > `funding_high` (default `+2.0%` per [`lib/analytics/strategies.py:108`](../../lib/analytics/strategies.py#L108)).
- **Threshold rationale:** the comment treats 3-day momentum as a proxy for funding rate; the original §1 of PR #207 flagged that the real funding surface (`lib.chain.intelligence._fetch_binance_funding`, `lib.chain.sources.HyperliquidClient.funding_history`) is unused here. **No change is proposed in Layer B** — replacing the proxy with the real surface is properly Layer A territory, and Layer A landed in PR #230. We reference the existing short emitter as the reference implementation: the new branches in §10.2.1–§10.2.4 follow the same Decision shape (`direction="short", size=0.4, stop_pct, tp_pct`).
- **Exit rule:** unchanged. SL/TP percentages are symmetric with the long branch in the same strategy, which is acceptable here because the strategy fades crowded positioning rather than trading trend — the asymmetric ruin argument in §10.3 applies less strongly.
- **Regime gate:** none. Funding is its own gate.

### 10.3 Risk rules for short positions

Long and short are not symmetric in price action or capital exposure.
Three rules apply on top of the per-strategy thresholds in §10.2.

1. **Stop sizing — short stops are tighter than long stops.** A short
   loses unboundedly on an upside breakout (price can double; long can
   only halve). Use `short_sl_pct = long_sl_pct × 0.7`. With the
   default `sl_pct = 0.05`, longs stop at −5%, shorts stop at +3.5%.
   The 0.7 factor approximates the historical 1.4× upside-move
   asymmetry observed in BTC/ETH/SOL daily OHLCV (mean-shift of the
   |+max| vs |−max| daily range distribution). Encode this in the
   `Decision` construction inside each new branch — not as a global
   override — so the strategy code path remains explicit and reviewable.
2. **Borrow cost assumption (paper trading).** Real perpetual shorts
   pay funding when `funding_rate > 0` (the dominant historical case).
   For the Layer B backtest, model a flat **−4 bps per day** holding
   cost on every open short position. This is rough — the real
   distribution is `~2–25 bps/day` at 8h cadence with fat upper tails —
   but a fixed conservative draw is sufficient to demonstrate that the
   strategy clears the §4 gates **after** borrow. The Sortino-on-shorts
   test will reject any strategy whose edge evaporates under realistic
   borrow.
3. **Hard cap on aggregate gross exposure.** Layer B introduces five
   strategies × three symbols capable of going short concurrently. Cap
   total notional at 1.0× bankroll across all open longs **plus** all
   open shorts (i.e. gross, not net). If the cap is hit, the
   `BacktestEngine.run` signal_fn drops the new entry rather than
   resizing — preserving the per-strategy size as the test variable.
   This rule lives in the engine wrapper, not in `strategies.py`; flag
   in the engine path during the implementation PR.

### 10.4 Backtest plan

The §4.5 acceptance gate from
[`lib/analytics/backtest_harness.py`](../../lib/analytics/backtest_harness.py)
(PR #212) is the single source of truth. Defaults at
[`lib/analytics/backtest_harness.py:86-89`](../../lib/analytics/backtest_harness.py#L86-L89):

| Constant | Value | Meaning |
|---|---:|---|
| `MIN_TRADES` | 30 | Insufficient evidence below this trade count across all CPCV folds. |
| `MIN_SORTINO` | 0.5 | Mean fold Sortino floor — must beat zero on a downside-aware metric. |
| `MIN_DSR` | 0.0 | Bailey & López de Prado deflated Sharpe must remain non-negative. |
| `MAX_DRAWDOWN_PCT` | 35.0 | Worst-fold drawdown ceiling. |

The harness exits PASS (0) when all four hold. WARN (10) on data gaps
(no CSV under `data/backtests/<symbol>/<timeframe>/`). FAIL (20) when
data is present but the gates fail.

**Exact invocation per strategy (run all four):**

```bash
python3 -m lib.analytics.backtest_harness \
    --strategy lib.analytics.strategies:RegimeAwareRSI \
    --start 2025-04-01 --end 2026-04-25 \
    --symbols BTC-USD,ETH-USD,SOL-USD

python3 -m lib.analytics.backtest_harness \
    --strategy lib.analytics.strategies:MultiTFMomentum \
    --start 2025-04-01 --end 2026-04-25 \
    --symbols BTC-USD,ETH-USD,SOL-USD

python3 -m lib.analytics.backtest_harness \
    --strategy lib.analytics.strategies:CorrelationBreakout \
    --start 2025-04-01 --end 2026-04-25 \
    --symbols BTC-USD,ETH-USD,SOL-USD

python3 -m lib.analytics.backtest_harness \
    --strategy lib.analytics.strategies:SapphireComposite \
    --start 2025-04-01 --end 2026-04-25 \
    --symbols BTC-USD,ETH-USD,SOL-USD
```

**Five metrics gated per strategy** (the four §4.5 constants plus a
direction-conditioned check the harness does not yet compute):

1. `total_trades >= 30` — across all CPCV folds. Below this we cannot reject H0.
2. `mean_sortino >= 0.5` — per-fold mean. `lib/analytics/backtest_harness.py:417-429` records the failing reason inline.
3. `deflated_sharpe >= 0.0` — DSR floor across the per-fold Sharpe distribution; reused via `lib.analytics.deflated_sharpe.deflated_sharpe_ratio`.
4. `max_drawdown_pct <= 35.0` — worst-fold drawdown ceiling.
5. **Bear-precision uplift (manual sanity check, mirrors §4.5 step 4):** of the bars where the strategy emits short, the fraction where the realized 24-hour forward close is below entry rises from `0.125` (the §2 baseline) to `≥ 0.40` on the holdout half. This is computed from `data/backtests/strategies/bearish_asymmetry/` artifacts in a follow-up script, not by the harness directly.

**Cross-strategy "do no harm" gate.** Long-side performance must not
regress. After Layer B, run the harness once more **without** the
`SAPPHIRE_STRATEGIES_ENABLE_SHORT` flag set; the resulting metrics must
match the pre-Layer-B baseline within ±1.0 σ on every fold (the long
path is unaltered, so any drift indicates an unintended side effect).
Treat any drift as a FAIL.

**Hard prerequisite.** As described in §4.5 of the original doc, the
harness today returns WARN with `reasons=["no historical data"]`
because `data/backtests/<symbol>/<timeframe>/*.csv` is empty. Layer B
cannot land until those CSVs are populated for BTC-USD, ETH-USD,
SOL-USD. Producing the CSVs is **not** in scope for the design doc PR;
it is the first task of the Layer B implementation PR (or a precursor
data-staging PR).

### 10.5 Rollout plan

Layer B follows Layer A's pattern exactly: **default-off, env-flag
gated, opt-in once the §4 backtest passes.** Three flag conventions to
pick from — recommend the first:

| Flag | Default | Effect |
|---|---|---|
| `SAPPHIRE_STRATEGIES_ENABLE_SHORT` (recommended) | `0` | All four new short branches respect this single flag. Set to `1` to enable strategy-side short emission across the board. |
| `SAPPHIRE_STRATEGIES_ENABLE_SHORT_<CLASS>` | `0` | Per-strategy gating — finer control but four flags vs one. Useful only if a single strategy fails §10.4 in isolation. |
| `SAPPHIRE_STRATEGIES_ENABLE_SHORT_PCT` | `0.0` | Phase-in by traffic percentage. Premature for Layer B — adopts only if the global flag passes and we want a dim-on instead of a hard cutover. |

**Flag parsing rule** (mirror Layer A at
[`plugins/claw-sapphire/tools/internal/predict.py:252-254`](../../plugins/claw-sapphire/tools/internal/predict.py#L252-L254)):
truthy values are `1`, `true`, `yes`, `on` (case-insensitive). Missing
or any other value treated as off. This keeps operator overrides
forgiving without surprising the production default.

**Operator opt-in path** (no code changes once shipped):

1. Layer B implementation PR lands (default-off; production-equivalent until flag set).
2. Operator stages OHLCV CSVs in `data/backtests/<symbol>/<timeframe>/`.
3. Operator runs `python3 -m lib.analytics.backtest_harness --strategy ...` for each of the four strategies.
4. All four return PASS (exit 0). Cross-strategy "do no harm" gate passes.
5. Operator sets `SAPPHIRE_STRATEGIES_ENABLE_SHORT=1` in the relevant LaunchAgent env file (likely `infra/launchagents/com.sapphire.signal-logger.plist` and any plist that drives `run_strategies`).
6. Operator restarts agents; run `lib/analytics/run_strategies.py` once to confirm shorts are emitted on a sample bar.
7. Roll back by unsetting the flag — no code revert needed (same property as Layer A's `SAPPHIRE_PREDICT_USE_CHAIN_FACTORS`).

**Telegram watchdog** (recommended add-on for the implementation PR):
emit a `priority:high` system event the first 24h after the flag goes
hot if no `direction="short"` decisions have fired in any strategy. The
existing `signal_generator` and `paper_trader` logs make this a one-
line tail check — a missed-fire silence is the dominant pre-rollout
failure mode.

### 10.6 Risks

1. **Over-fitting on bear samples.** The §2 evidence base in the
   original doc has only 8 scored bear calls, all SOL-dominated. The
   §10.2 thresholds (RSI 75 cutoff, `corr > 0.65`, `mom > +2%`) are
   chosen by mirror-symmetry against existing long thresholds rather
   than by fit, but the §10.4 harness still has six tunable knobs (one
   per strategy plus the two thresholds in §10.2.3) that could be
   accidentally optimized against the holdout. The DSR floor at
   `MIN_DSR >= 0` is the primary defense; if any of the four strategies
   passes the per-fold mean Sortino but fails DSR, treat it as
   evidence of overfitting and reduce the variant count rather than
   relaxing the gate.
2. **Asymmetric drawdown amplification.** With `gross ≤ 1.0×`
   (§10.3 rule 3), a fully loaded book of long (5 strategies × 3
   symbols × 0.5) plus short (4 strategies × 3 symbols × 0.4) is a
   net ≈ 0 hedge — but if all longs and all shorts move adversely
   simultaneously (regime flip with no concurrent direction agreement)
   the gross drawdown stacks. The 35% `MAX_DRAWDOWN_PCT` ceiling in the
   harness is the protection; if any fold breaches it, abort the layer.
   Crucially: paper-trade for ≥ 14 days under live market data after
   the flag goes hot but before any real-money rollout decision.
3. **Paper-vs-live divergence on short borrow rates.** §10.3 rule 2
   models a flat −4 bps/day. Real perpetual funding can spike to
   +25 bps/day during squeeze events; paper-trading numbers will
   overstate the edge. Two mitigations:
   (a) once the `data/backtests/<symbol>/<timeframe>/` CSVs include a
   `funding_8h_pct` column, swap the flat assumption for the realized
   per-bar cost in the engine wrapper;
   (b) before any live cutover, re-run the harness with the flat cost
   bumped to −10 bps/day and require the gate still passes (margin of
   safety).
4. **Kill-switch edge cases.** `lib/core/kill_switch.py` halts the
   trading critical path on a security event. After Layer B, the
   engine has open short positions in addition to longs. The current
   kill path closes positions; verify that "close" emits buy-to-close
   for `direction == "short"` rather than sell. If unsure, the
   implementation PR includes a unit test
   `test_kill_switch_closes_short_positions_with_buy_to_close` against
   the engine wrapper (mirroring the existing close logic at
   [`lib/analytics/strategies.py:537-538`](../../lib/analytics/strategies.py#L537-L538)
   which already maps `direction → action`).
5. **Backwards-compat in `BacktestEngine.run`.** The engine's
   `signal_fn` already understands `direction="short"` (
   [`lib/analytics/strategies.py:537-550`](../../lib/analytics/strategies.py#L537-L550))
   and translates SL/TP correctly via the `direction == "long"`
   ternary on lines 548–550. So feeding shorts into the engine is a
   no-op API change — but the existing `paper_trader.py` and
   `signal_logger` paths in `services/alpha/` may have not seen
   sustained short flow before. The original doc §5.6 flagged this;
   the implementation PR's test plan must include a happy-path round
   trip from `MultiTFMomentum.short → BacktestEngine.run → Trade
   record → signal_logger ingest`.

### 10.7 Decision required from human reviewer

Same A/B/C/D matrix style as PR #207 §7. The reviewer must pick one
before any implementation PR:

| Option | Description | Estimated effort | Reversible? |
|---|---|---|---|
| **(A) Full Layer B — all four strategies, single flag.** | Implement §10.2.1–§10.2.4 short branches. `SAPPHIRE_STRATEGIES_ENABLE_SHORT` global flag, default `0`. Land harness data first, run §10.4 gate, cut over once PASS. | 3–5 sessions plus harness data staging. | Yes — unset the flag. |
| **(B) Conservative gated path — `MultiTFMomentum` only first.** | Land §10.2.2 alone behind the flag (it is already-coded logic; the change is one return statement). Validate §10.4 for that strategy. Then iterate to §10.2.1, §10.2.3, §10.2.4 in separate PRs, each with its own backtest run. | 1 session for the first strategy; 1–2 per follow-up. | Yes per strategy. |
| **(C) Composite-only opt-in.** | Land §10.2.4 (`SapphireComposite`) Option β alone. Other three strategies stay long/flat. Composite as ensemble vote captures most of the bear evidence in one place; smaller surface area for the harness gate. | 2 sessions plus harness data. | Yes — unset the flag. |
| **(D) Reject Layer B — close out the asymmetry research with C and A only.** | Layers C (#209) and A (#230) are sufficient. Strategies stay long-biased; the short-side problem is left to a future redesign. The asymmetry headline persists but the predictor surface is improved. | 0 (just close out). | n/a. |

**Recommended path: (B).** Rationale:

- §10.2.2 (`MultiTFMomentum`) is the lowest-risk promotion: the bear evaluation is already coded (line 355) and just emits `flat`. Toggling the return statement is the smallest-possible code change for the largest available signal lift, and it isolates the §10.4 harness's verdict cleanly to the most diagnostic strategy.
- The original doc §1 attributed the bear miss specifically to `MultiTFMomentum` underweighting bear-confirming signals. Fixing it first directly tests that hypothesis.
- Each follow-up PR (§10.2.1, §10.2.3, §10.2.4) carries its own gate. If `MultiTFMomentum` short emission fails the §4 harness, we abort Layer B and revisit the design rather than carrying the failure into three more strategies.
- (A) is the desired end-state but the §10.6 risks compound when all four land at once with only 8 scored bear observations to anchor the design. (B) gives us four serial reads on the data instead of one parallel read.
- (D) loses the optionality for no upside; the harness gate already protects us from a bad cutover.

Reject (C) on Option-α/β grounds: the composite refactor introduces the
biggest single-PR surface, which is exactly the wrong place to start
when the §4 harness still has WARN status from a missing data set.

## References

- Original doc — [`docs/research/bearish-direction-asymmetry-2026-04-26.md`](./bearish-direction-asymmetry-2026-04-26.md)
- Layer A PR #230 (chain factors)
- Layer C PR #209 (asymmetric thresholds)
- Backtest harness PR #212 — [`lib/analytics/backtest_harness.py`](../../lib/analytics/backtest_harness.py)
- Strategy file under change — [`lib/analytics/strategies.py`](../../lib/analytics/strategies.py)
- Engine — [`lib/analytics/backtest_engine.py`](../../lib/analytics/backtest_engine.py),  [`lib/analytics/run_strategies.py`](../../lib/analytics/run_strategies.py)
- Branch SHA at design time: `4b10e2c9` (`Close out 2026-04-26 evening autonomous window with Layer A landing`).
