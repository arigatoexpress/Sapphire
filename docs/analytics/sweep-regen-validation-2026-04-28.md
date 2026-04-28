# Sweep Regen Validation - 2026-04-28

Agent C validation after PR #349 merged.

## Summary

- Result: PASS for the current repository sweep CLI.
- Command validated: `python3 -m lib.analytics.run_strategies --days 90 --bankroll 10000`
- Duration: `real 0.86s`
- Artifacts generated locally only, not committed.
- JSON validation: PASS for both generated files via `python3 -m json.tool`.

## Output Sample

```text
Full sweep (756 backtests) saved -> data/backtests/strategies/strategy_sweep_20260428T041608Z.json
Best params (20 rows) saved -> data/backtests/strategies/best_per_symbol_20260428T041608Z.json
```

Generated artifact shape:

```text
strategy_sweep_20260428T041608Z.json
  results: 756
  config: days=90 bankroll=10000.0 symbols=BTC-USD,ETH-USD,SOL-USD,SPY

best_per_symbol_20260428T041608Z.json
  results: 20
  config: days=90 bankroll=10000.0 symbols=BTC-USD,ETH-USD,SOL-USD,SPY
```

## Notes

- `redis-py` is not installed in this Python, so the event bus used fallback mode.
- `yfinance` is not installed in this Python, so the sweep used the deterministic synthetic OHLCV fallback.
- The handoff-requested smoke command with `--output-dir /tmp/sweep-test/` still fails because `lib.analytics.run_strategies` currently accepts only `--days` and `--bankroll`.
- `lib/analytics/run_strategies.py` was not edited because it is outside Agent C's explicit edit allow-list for this lane.
