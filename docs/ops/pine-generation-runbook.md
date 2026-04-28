# Pine Strategy Generation — Operator Runbook

**Module**: `lib.pine_generation` 0.1.0 + `services.pine_generation`.
**On-call ownership**: Sapphire trading lead. Notify the operator before any push to live TradingView.
**Trading critical path**: this runbook does NOT touch live capital. Generated Pine is research-grade until paper-tested.

## What this runbook covers

How to run the Pine generation pipeline end-to-end, what to do when the build fails, how to publish a new strategy to TradingView safely, how to roll back a bad push, and how to recover when the underlying backtest sweep itself is stale or corrupt.

## Daily operator flow

### 1. Generate Pine from the latest sweep

```bash
cd ~/Code/Sapphire
python3 -m lib.analytics.run_strategies --days 90        # ~2s — refreshes data/backtests/strategies/
python3 -m services.pine_generation.build                # writes pine/generated/<today>/
```

Expected output:

```
pine_generation: generated=20 skipped=0 errors=0 out=/Users/aribs/Code/Sapphire/pine/generated/2026-04-29
  RegimeAwareRSI           ETH-USD      → regime-aware-rsi-ETHUSD.pine
  SapphireComposite        SPY          → sapphire-composite-SPY.pine
  ...
```

The `errors=0` field is the key health signal. Anything else demands investigation before the operator considers any of the generated Pine ready for paper-testing.

### 2. Spot-check one generated strategy

```bash
echo '{"action":"validate","pine_path":"pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine"}' \
    | python3 plugins/claw-sapphire/tools/pine_generation.py
```

This re-runs the validator against disk. The build already validated every file; this is a defence-in-depth re-check that catches accidental hand-edits.

### 3. Listing recent generations

```bash
echo '{"action":"latest"}' | python3 plugins/claw-sapphire/tools/pine_generation.py
```

Output lists every `.pine` in the most recent date directory under `pine/generated/`.

## Push to TradingView (operator-gated)

**Do not run this routine without a clear operator decision.** Every push lands a strategy on the operator's TradingView account where it can be added to charts and, at the operator's discretion, used to drive live alerts.

### Pre-push checklist

1. The Pine file passes `validate` action: `ok: true`, no errors, ideally no warnings.
2. The strategy's most recent backtest sweep had `total_trades >= 5`. Pine for `total_trades < 5` is statistically unreliable and the operator should hand-tune parameters in TV before considering it.
3. The operator has reviewed the generated source by eye. Pine is small enough (~80 lines for SapphireComposite, smallest is ~37) that this takes 2 minutes per file.
4. The operator has a TradingView pane open with the target symbol on a timeframe that matches the strategy's design (daily for the bar-shape strategies; intraday for the timeframe-proxy strategies).

### Push command

```bash
SAPPHIRE_PINE_TV_PUSH_LIVE=1 echo '{
    "action": "push-to-tv",
    "pine_path": "pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine",
    "title": "Sapphire Composite (BTC) v0.1",
    "confirm": true,
    "dry_run": false
}' | python3 plugins/claw-sapphire/tools/pine_generation.py
```

The 3-key gate refuses unless **all three** of the following are present:

- env: `SAPPHIRE_PINE_TV_PUSH_LIVE=1`
- payload field: `"confirm": true`
- payload field: `"dry_run": false`

If any one is missing, the action returns `ok: false` and explains which gate refused. **Do not bypass any gate**: every gate is intentional.

### Dry-run mode

For mid-iteration testing, leave `dry_run: true` (the default). The push action runs the same code path, but the MCP invocation function returns `status: dry_run` and reports the byte count. No source ever leaves the local machine in dry-run mode.

### Rollback

There is no automatic rollback — TradingView's Pine Editor is single-version-per-strategy-name. To roll back:

1. Open the strategy in the TradingView Pine Editor.
2. Restore the prior Pine source from `pine/generated/<previous-date>/<same-filename>` (or from your `git log -- pine/generated/`).
3. Click "Save". TradingView retains version history server-side; you can revert to any prior save in the editor.

## Failure modes and recovery

### Build reports `errors > 0`

Run the build with `--json` to see structured errors:

```bash
python3 -m services.pine_generation.build --json
```

Each error has a `stage` field: `spec` (backtest row malformed), `generate` (template rendering error), or `validate` (generated Pine failed lint).

| Stage | Likely cause | Recovery |
|---|---|---|
| `spec` | Bad row in `best_per_symbol_*.json` (missing field, unsupported strategy class) | Inspect the JSON, file an issue if a new strategy class shows up that the registry doesn't list |
| `generate` | Template syntax broke after a Jinja2 upgrade | Reinstall pinned Jinja2 (`pip install -r requirements-test.txt`); if persistent, the stdlib fallback in `translator._stdlib_render` should still work — confirm `_JINJA_AVAILABLE` is False in a quick REPL |
| `validate` | Output failed lint | Open the source under `/tmp` and inspect. If it's a real bug, file the lint findings as the failure summary; if it's a known false-positive, capture it in the test suite |

### Build reports `skipped > 0` with `--no-overwrite`

Expected when the operator is iterating and doesn't want to clobber. Use `--no-overwrite` to keep prior outputs and force the operator to delete by hand.

### `latest` action returns no files

The `pine/generated/` tree is empty or has no date subdirectories. Run a build to populate it. If you've never run a build on a fresh checkout, that's the cause.

### `push-to-tv` fails with `gate=SAPPHIRE_PINE_TV_PUSH_LIVE`

The env var is unset or not equal to `1`. Set it explicitly in the same shell that invokes the tool. Do not bake it into a LaunchAgent plist — the gate is meant to require active operator presence.

### `push-to-tv` fails with `gate=confirm`

The payload is missing `"confirm": true`. This is a JSON-level safety gate; even with the env flag set, accidental scripts can't push.

### Generated Pine throws a TradingView compile error after pasting

This means the validator missed something. Steps:

1. Capture the TradingView error message (line number + message).
2. File a `tests/unit/test_pine_generation_validator.py` test case that asserts the malformed input is rejected.
3. Update `validator.py` to catch the new pattern.
4. Re-run the build and verify the bad output is now rejected.

## Routine cadence

The build is not yet wired into the scheduled-task system. The operator runs it manually after every backtest sweep. After 1 week of stable manual operation, we'll add `weekly-pine-generation` to `~/.claude/scheduled-tasks/` (Sunday 7:30 AM CT, after the existing `backtest-sweep` task) so every weekly sweep produces a fresh Pine bundle.

The push action is **never** automated. Every TradingView push happens with operator presence.

## Disk state

Generated Pine files persist under `pine/generated/<YYYY-MM-DD>/<strategy-slug>-<symbol>.pine`. Each file is ~2-5 KB; an entire daily bundle (20 files) is ~50 KB. There is no automatic pruning — the operator should periodically `rm -rf pine/generated/2026-0[1-3]-*/` to clean up old bundles. Git tracks the `pine/generated/2026-04-29/` directory; operator decides whether to commit the most recent build (we do for the inaugural 0.1.0 release as evidence).

## Cross-lane interactions

- **Research Notes (Tranche 5 Lane 4)**: research notes will embed generated Pine as an appendix per strategy after Lane 9 lands. The integration test for that wiring lives in `tests/unit/test_tranche5_integration.py`.
- **Backtest sweep (`lib.analytics.run_strategies`)**: this lane's pipeline is downstream-only. We do not touch the sweep.
- **TradingView MCP**: `tradingview-mcp-v2` lives in the operator's other repo. We invoke it via `_invoke_tv_mcp` in the plugin internal module. In tests this is monkeypatched. In production it shells out (live wiring deferred until operator paper-tests at least one generated strategy).
- **Trading critical path**: untouched. This lane writes nothing to `lib/portfolio/`, `lib/trading/`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, etc.

## Safety review checklist

When introducing a new feature into this pipeline (e.g. a new strategy class, a new template, a new push target), the reviewer must confirm:

- [ ] The strategy is in `SUPPORTED_STRATEGIES` AND has a corresponding `STRATEGY_TEMPLATE_MAP` entry.
- [ ] The new template renders clean for default `PineParams()` and validates with no errors.
- [ ] The new template renders clean for at least 3 distinct param sets and validates each.
- [ ] No strategy template imports symbols from `lib/portfolio/`, `lib/trading/`, `lib/analytics/strategies.py`, or `lib/core/kill_switch.py`.
- [ ] No template references a network endpoint or filesystem path.
- [ ] Any new request.security() call uses `lookahead=barmerge.lookahead_off`.
- [ ] If a new symbol prefix is added, it's added to `SYMBOL_PREFIX_MAP` AND covered by a translator test.
- [ ] If the push API surface changes, the 3-key gate is preserved and tests refresh.

## Operator decisions log

Every TradingView push must be logged to `data/system_events.jsonl` (this is not enforced in code today; it's an operator discipline). Include the strategy class, symbol, sortino, the file SHA-256, and the push timestamp. This gives us a posture audit trail when reviewing live capital posture.

Example log entry:

```
{"ts":"2026-04-29T14:00:00Z","type":"pine_pushed","strategy":"SapphireComposite","symbol":"BTC-USD","file":"pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine","sha256":"...","tv_account":"sapphire-prod"}
```

## Reference: lint heuristics

The validator runs ten heuristics. Each is documented in `lib/pine_generation/validator.py`. The full list of checks, their severity, and what they catch is in `docs/products/pine-generation-0.1.0.md` ("The validator" section).

## Reference: full-output sample

The reference sample is `pine/generated/2026-04-29/sapphire-composite-BTCUSD.pine`. Generated from the live backtest sweep `best_per_symbol_20260428T235141Z.json` with parameters `rsi=7, sl=8%, tp=10%, composite_threshold=55.00`. Backtest stats: **Sortino=4.543, Sharpe=2.517, win_rate=100% (n=2), max DD=0.76%, total_return=2.01%** — read these stats with Tranche 5's "small-sample" caveats: 2 trades on 90 days of synthetic OHLCV is a research artifact, not a tradeable edge. The Pine is 85 lines, 5,175 bytes, validates clean, and renders the 5-component composite score as Pine v5 source.

## Glossary

- **PineSpec**: the input bundle for one Pine generation. Strategy + symbol + parameters + (optional) overrides.
- **PineParams**: the parameter dataclass mirroring `lib.analytics.strategies.StrategyParams`. Note: parallel dataclass, not an import — the lane is regression-isolated from strategies.py.
- **PineValidationResult**: the validator output. `ok` (bool), `errors` (list[str]), `warnings` (list[str]), `stats` (dict).
- **`SAPPHIRE_PINE_TV_PUSH_LIVE`**: the env-flag gate that authorises a live TradingView push. Mirrors the `SAPPHIRE_GEMINI_LIVE` pattern from `gemini_ooda`.
- **`tradingview-mcp-v2`**: the operator's TradingView CDP-driven automation bridge. Sapphire shells out to its `tv` CLI for the actual push step.
- **`pine/generated/<YYYY-MM-DD>/`**: the canonical output directory. One subdirectory per generation date.
- **`best_per_symbol_*.json`**: the backtest sweep artifact this pipeline consumes. Produced by `lib.analytics.strategies.save_results`.
