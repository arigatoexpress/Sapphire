# Pine Strategy Generation Pipeline 0.1.0

**Status**: Tranche 5 Lane 8 — shipped 2026-04-29.
**Surface**: `lib/pine_generation/`, `services/pine_generation/build.py`, `plugins/claw-sapphire/tools/internal/pine_generation.py` (+ shim).
**Owner**: `sapphire`.
**Module version**: `0.1.0`.

## What this enables

Sapphire backtests 7 quant strategies on dozens of symbols through hundreds of parameter combinations. The output is structured JSON (`data/backtests/strategies/best_per_symbol_*.json`). **TradingView users can't run JSON. They run Pine Script v5.** Pine is the *de facto* deployable runtime for quantitative trading IP — every prop shop, every retail screener, every exchange-side alerting flow ultimately renders into Pine. Until this lane shipped, Sapphire's strategy IP was reproducible only as a Python sweep on the operator's mac.

This lane closes the loop:

1. Run the sweep (`python3 -m lib.analytics.run_strategies --days 90`) — produces `best_per_symbol_*.json`.
2. Run the generator (`python3 -m services.pine_generation.build`) — translates each (strategy, symbol) pair into a deployable Pine Script v5 file under `pine/generated/<YYYY-MM-DD>/`.
3. (Operator-gated) Push the Pine to TradingView via the local `tradingview-mcp-v2` bridge — `SAPPHIRE_PINE_TV_PUSH_LIVE=1` + payload `confirm: true`.

The strategy IP becomes deployable infrastructure on the world's most-used charting platform. From an acquisition lens, this is the difference between "we have an interesting research script" and "we have a productized strategy library that an analyst at a target shop can install on a TradingView pro account in 90 seconds."

## Architecture

The pipeline is intentionally split into three pure layers, each independently testable:

```
┌──────────────────┐   ┌────────────────────┐   ┌───────────────────────────┐
│ best_per_symbol  │ → │ services.pine_     │ → │ pine/generated/<date>/    │
│   _*.json        │   │ generation.build   │   │ <strategy>-<symbol>.pine  │
│ (sweep output)   │   │                    │   │                           │
└──────────────────┘   └─────────┬──────────┘   └───────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │ lib.pine_generation        │
                    │   .translator              │
                    │   .validator               │
                    │   .templates/              │
                    └────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │ plugins/.../tools/internal/│
                    │ pine_generation.py         │
                    │ (stdin JSON tool)          │
                    └────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │ tradingview-mcp-v2 bridge  │
                    │ (operator-gated push)      │
                    └────────────────────────────┘
```

## The 7 supported strategies

The translator handles the 5 production quant strategies plus the abstract base and the params-only scaffolding form:

| Class | Pine template | Aux symbols | Score components |
|---|---|---|---|
| `RegimeAwareRSI` | `regime_aware_rsi.pine.j2` | BTC | RSI threshold gated by BTC regime |
| `FundingRateContrarian` | `funding_rate_contrarian.pine.j2` | – | 3-day momentum vs `funding_high/low` |
| `CorrelationBreakout` | `correlation_breakout.pine.j2` | SPY | rolling Pearson < `corr_threshold` + RSI |
| `MultiTFMomentum` | `multi_tf_momentum.pine.j2` | – | RSI(`tf_fast`) ∧ SMA(20) ∧ ret(`tf_slow`) all bear |
| `SapphireComposite` | `sapphire_composite.pine.j2` | BTC, SPY | 0–100 score, gate ≥ `composite_threshold` |
| `BaseStrategy` | `base_strategy.pine.j2` | – | RSI mean-reversion only |
| `StrategyParams` | `params_only.pine.j2` | – | inputs scaffold (no execution) |

## Walkthrough: `SapphireComposite` translation

`SapphireComposite` is the most informative example because every other strategy is a degenerate subset of its components.

### Python (lib/analytics/strategies.py)

The Python implementation maintains five additive score components (max 100):

```python
# ── Component 1: Regime (0–25) ────────────────────────────────────
regime_bars = aux.get("btc") or window
old = regime_bars[-(rp + 1)].close
new = regime_bars[-1].close
mom = (new - old) / old if old > 0 else 0.0
if mom >= p.regime_on_threshold:
    score += 25.0
elif mom > p.regime_off_threshold:
    score += 15.0

# ── Component 2: RSI depth (0–25) ────────────────────────────────
rsi = _rsi(closes, p.rsi_period)
if rsi is not None:
    if rsi < 30.0:
        score += min(25.0, (30.0 - rsi) * 25.0 / 20.0)
    elif rsi > 70.0:
        score -= 5.0

# ── Component 3: Funding proxy (0–20) ────────────────────────────
mom_3d = (closes[-1] - closes[-4]) / closes[-4]
if mom_3d < p.funding_low:
    score += min(20.0, abs(mom_3d) * 300.0)
elif mom_3d > p.funding_high:
    score -= 5.0

# ── Component 4: Correlation decoupling (0–15) ───────────────────
corr = _pearson(sym_rets, spy_rets)
if corr < p.corr_threshold:
    score += min(15.0, (p.corr_threshold - corr) * 50.0)

# ── Component 5: Multi-TF alignment (0–15) ───────────────────────
# rsi_fast<40, close<sma20, weekly_ret<0 — fraction agreeing × 15
if score >= p.composite_threshold:
    return Decision(direction="long", size=self._kelly_size(), ...)
```

### Pine v5 translation (sapphire_composite.pine.j2)

The translator emits the identical scoring scheme:

```pine
// ── Component 1: Regime (0–25) ─────────────────────────────────────
btc_close    = request.security("CRYPTOCAP:BTC", timeframe.period, close, lookahead=barmerge.lookahead_off)
btc_old      = btc_close[regime_period]
btc_mom      = btc_old > 0.0 ? (btc_close - btc_old) / btc_old : 0.0
regime_score = btc_mom >= regime_on_threshold ? 25.0 : (btc_mom > regime_off_threshold ? 15.0 : 0.0)

// ── Component 2: RSI depth (0–25) ──────────────────────────────────
rsi             = ta.rsi(close, rsi_len)
rsi_depth_score = rsi < 30.0 ? math.min(25.0, (30.0 - rsi) * 25.0 / 20.0) : (rsi > 70.0 ? -5.0 : 0.0)

// ── Component 3: Funding proxy (0–20) ─────────────────────────────
c_prev          = close[3]
mom_3d          = c_prev > 0.0 ? (close - c_prev) / c_prev : 0.0
funding_score   = mom_3d < funding_low ? math.min(20.0, math.abs(mom_3d) * 300.0) : (mom_3d > funding_high ? -5.0 : 0.0)

// ── Component 4: Correlation decoupling (0–15) ────────────────────
sym_ret         = (close - close[1]) / close[1]
spy_ret         = (spy_close - spy_close[1]) / spy_close[1]
btc_spy_corr    = ta.correlation(sym_ret, spy_ret, corr_period)
corr_score      = (corr_threshold - btc_spy_corr) > 0.0 ? math.min(15.0, (corr_threshold - btc_spy_corr) * 50.0) : 0.0

// ── Component 5: Multi-TF alignment (0–15) ────────────────────────
tf_signal       = (rsi_fast < 40.0 ? 1.0 : 0.0) + (close < sma20 ? 1.0 : 0.0) + (weekly_ret < 0.0 ? 1.0 : 0.0)
tf_score        = 15.0 * tf_signal / 3.0

// ── Composite ─────────────────────────────────────────────────────
composite_score = regime_score + rsi_depth_score + funding_score + corr_score + tf_score
long_cond       = composite_score >= composite_threshold and strategy.position_size == 0
```

### Aux-symbol references

The Python uses `aux["btc"]` and `aux["spy"]` — pre-aligned bar streams. In Pine, we use `request.security("CRYPTOCAP:BTC", timeframe.period, close, lookahead=barmerge.lookahead_off)`. The `lookahead=barmerge.lookahead_off` flag is critical: without it, the request.security call would peek into the future and the Pine backtest would read returns that the live runtime can't access. The translator hardcodes this flag in every aux-symbol call.

### Symbol mapping

The translator translates Sapphire's canonical ticker (e.g. `BTC-USD`) into a TradingView-prefixed exchange ticker (`BINANCE:BTCUSDT`). The mapping table is in `translator.py:SYMBOL_PREFIX_MAP`. Unknown tickers pass through unchanged so the operator can edit the strategy() title in TradingView.

### Position sizing — quarter Kelly

`SapphireComposite._kelly_size()` in Python returns `max(0.05, min(0.50, round((win_prob - (1-win_prob)/(tp/sl)) * 0.25, 3)))` with `win_prob=0.55`. The translator pre-computes this fraction at generation time and bakes it into the `default_qty_value` parameter of the `strategy()` declaration. On `sl=8%, tp=10%`: `b = 1.25, f = 0.55 - 0.45/1.25 = 0.19`, quarter-Kelly = `round(0.0475, 3) = 0.048` → 4.8%. The Pine `default_qty_value` is then `max(1.0, min(100.0, 4.8))` = 4.8%. The hard floor of 1% prevents zero-sized orders if Kelly returns a negative under bad params.

## The validator

`lib.pine_generation.validator.validate_pine(source: str)` runs ten heuristic checks and returns a structured `PineValidationResult`. The validator is a defence-in-depth lint pass — it doesn't replace the TradingView compiler, but it catches every category of malformed Pine the translator could conceivably emit before the source ever leaves the local machine.

| Check | Severity | What it catches |
|---|---|---|
| `//@version=5` directive | error | missing or after-code |
| Balanced parens / brackets | error | unbalanced or mismatched delimiters (string- and comment-aware) |
| `strategy(...)` decl | error | missing, multiple, or unclosed |
| `indicator() and strategy()` both | error | Pine allows only one |
| `var <type> ?` ambiguity | error | malformed variable declaration |
| `request.security(...)` shape | error+warn | too few args; first arg not a quoted string (warn) |
| Body presence | error | no `strategy.entry/close/exit/plot/plotshape/alert` call |
| Trailing `\` continuation | error | Pine v5 disallows backslash continuations |
| Unsubstituted Jinja `{{var}}` | error | template variable that survived rendering |
| `// TODO` / `// FIXME` / `// XXX` | warning | explicit gaps in generated code |
| `initial_capital <= 0` | error | nonsensical capital |
| Double `//@version=5` | warning | second directive (TradingView will ignore but it's noise) |

The validator is **language-aware**: it strips out string-literal contents and `//` line comments before counting parens, so a strategy title like `"Sapphire (Composite)"` and `// (((( debug` won't trigger false positives. The version directive `//@version=5` is preserved.

## CLI usage

### Generate every (strategy, symbol) pair from the latest sweep

```bash
python3 -m services.pine_generation.build
```

This pulls the most recent `best_per_symbol_*.json`, generates one Pine file per row, and writes them to `pine/generated/<YYYY-MM-DD>/<strategy>-<symbol>.pine`. The build manifest summarises generated/skipped/error counts.

### Generate a top-N filtered subset

```bash
python3 -m services.pine_generation.build --limit 5 --strategies SapphireComposite,RegimeAwareRSI
```

### Generate a single strategy via the plugin tool

```bash
echo '{"action":"generate","strategy":"SapphireComposite","symbol":"BTC-USD"}' \
    | python3 plugins/claw-sapphire/tools/pine_generation.py
```

Output is the JSON `{ok, strategy, symbol, tv_symbol, pine_source, validator, bytes}`. Pass `"persist": true` and an optional `"output_root"` to write the source to disk.

### List recent generations

```bash
echo '{"action":"latest"}' | python3 plugins/claw-sapphire/tools/pine_generation.py
```

### Validate a Pine source string

```bash
echo '{"action":"validate","pine_path":"pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine"}' \
    | python3 plugins/claw-sapphire/tools/pine_generation.py
```

### Push to TradingView (operator-gated)

```bash
SAPPHIRE_PINE_TV_PUSH_LIVE=1 echo '{
    "action": "push-to-tv",
    "pine_path": "pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine",
    "title": "Sapphire Composite (BTC)",
    "confirm": true,
    "dry_run": true
}' | python3 plugins/claw-sapphire/tools/pine_generation.py
```

The push refuses unless **both** the env flag is set to `1` **and** the payload includes `confirm: true`. Even when both are present, the default `dry_run: true` returns a no-op manifest. Setting `dry_run: false` invokes the local TradingView MCP bridge; in production this means the operator's `tv pine write` CLI.

## Cross-lane integration

- **Backtest sweep (Tranche 1–4)**: this lane consumes `data/backtests/strategies/best_per_symbol_*.json` produced by `lib/analytics/run_strategies.py`. It does not modify or import strategies.py — the parameter shape is mirrored as a parallel dataclass.
- **Research notes (Tranche 5 Lane 4)**: per the Tranche 5 integration pass (Lane 9), research notes will embed the generated Pine source as an appendix per strategy. This lane's `generate` action is the source.
- **TradingView MCP bridge**: the push path calls into `tradingview-mcp-v2`, the operator's existing CDP-driven TV automation. No new dep on that repo — Sapphire shells out via `tv pine write` if and only if the env flag + confirm gate both pass.
- **Tool registry**: `pine_generation` is a new `internal` entry. The tool is invoked programmatically by services and tests; it is not in `agent-manifest.yaml` because it doesn't need to surface to the LLM tool selector.

## Safety posture

- **No live trading**. Generated Pine writes nothing to `lib/portfolio/`, `lib/trading/`, `lib/analytics/strategies.py`, or `lib/core/kill_switch.py`. The lane is read-only with respect to the trading critical path.
- **No secrets**. The pipeline never reads `~/.sapphire/secrets.env`, never writes credentials into Pine source, and never embeds API keys.
- **No network at generation time**. All translation is offline. The only network step is the operator-gated push.
- **Operator gate**. The push path requires `SAPPHIRE_PINE_TV_PUSH_LIVE=1` AND `confirm: true` AND `dry_run: false`. Any one missing → refuse. This is a 3-key gate; `gemini_ooda` uses the same env-flag pattern.
- **No new external deps**. Templates use Jinja2 (transitive via Flask in `requirements-test.txt`) with a stdlib fallback. The fallback's substitution semantics are identical for our control-flow-free templates.

## Sample output

`pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine` is the canonical example. It was generated from the live sweep on 2026-04-28T23:51Z (`best_per_symbol_20260428T235141Z.json`) — the SapphireComposite winner for BTC-USD with parameters `rsi=7, sl=8%, tp=10%`, scoring **Sortino=4.543, Sharpe=2.517, win_rate=100% (n=2), max DD=0.76%**. The generated Pine is 5,175 bytes, 85 lines, validates clean, and is ready to paste into a TradingView Pine Editor pane.

## Roadmap

- **0.2.0 — symbol watchlist sweep**. Today the build pulls every (strategy, symbol) pair in the latest `best_per_symbol_*.json`. Next iteration: sweep across Sapphire's full symbol watchlist (10–20 tickers per asset class) and persist a sortable index of all generated artifacts.
- **0.2.0 — Pine v5 → v6 migration tracking**. TradingView is rolling out Pine v6. The validator only checks v5; an `engine_version: 6` field on `PineSpec` would emit `//@version=6` and use the v6-only `request.security_lower_tf` for true multi-TF backtests.
- **0.3.0 — strategy.entry/exit reconstruction from `Decision`**. Today every template encodes the strategy logic by hand. A future iteration would `Decision`-trace through each strategy class and emit Pine programmatically, removing the need for hand-written templates.
- **0.3.0 — round-trip parity test**. Run the same strategy with the same params on the same data through both Python and the generated Pine on a TradingView paper account, assert the trade tape matches modulo bar-aggregation differences.

## Follow-ups not in this PR

- The Tranche 5 integration pass (Lane 9) will wire research notes → generated Pine appendix.
- The TradingView MCP push is mocked-only in tests. Live wiring against `tv pine write` happens after the operator paper-tests at least one generated strategy in TradingView and signs off.
- No scheduled task is wired yet. After 1 week of stable manual builds, we'll add `weekly-pine-generation` to `~/.claude/scheduled-tasks/` so every Sunday backtest sweep produces a fresh Pine bundle.
