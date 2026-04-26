# Weekly-Backtest Remote Shadow Soak

Date: 2026-04-26

## Decision

Record first soak evidence for `backtest-weekly` in `infra/org-repos.yaml`.
The local LaunchAgent `com.sapphire.backtest-weekly` remains canonical until
scheduled weekly comparisons satisfy the cutover gate and a later PR disables it
with rollback notes.

## Evidence

Remote workflow:

- Workflow: `.github/workflows/weekly-backtest.yml`
- Manual run id: `24948338321`
- Trigger: `workflow_dispatch` on `main`
- Result: success in 56 seconds
- Artifact: `weekly-backtest-24948338321`

Local artifact pair:

- Sweep: `data/backtests/strategies/strategy_sweep_20260426T040003Z.json`
- Best per symbol: `data/backtests/strategies/best_per_symbol_20260426T040003Z.json`
- Refreshed at: `2026-04-26T04:00:03.725194+00:00`
- Sweep rows: 756

Remote artifact pair:

- Sweep: downloaded GitHub Actions artifact under `/tmp`
- Best per symbol: downloaded GitHub Actions artifact under `/tmp`
- Refreshed at: `2026-04-26T04:36:20.611338+00:00`
- Sweep rows: 756

Comparator command:

```bash
python3 scripts/ops/compare_backtest_artifacts.py \
  --local-root data/backtests/strategies \
  --remote-root /path/to/gh-artifact \
  --max-skew-minutes 90
```

The comparator records the selected local and remote run timestamps, selected
sweep/best-per-symbol paths, candidate counts, and time skew in the JSON and
Markdown reports. Exact-path comparison remains available for forensic reruns:

```bash
python3 scripts/ops/compare_backtest_artifacts.py \
  --local-sweep data/backtests/strategies/strategy_sweep_20260426T040003Z.json \
  --remote-sweep /tmp/sapphire-backtest-shadow.FqMOkm/weekly-backtest-24948338321/data/backtests/strategies/strategy_sweep_20260426T043620Z.json \
  --local-best data/backtests/strategies/best_per_symbol_20260426T040003Z.json \
  --remote-best /tmp/sapphire-backtest-shadow.FqMOkm/weekly-backtest-24948338321/data/backtests/strategies/best_per_symbol_20260426T043620Z.json \
  --report-out /tmp/sapphire-backtest-shadow.FqMOkm/reports \
  --verbose
```

Comparator result:

- Verdict: PASS
- Rows compared: 756
- PASS rows: 756
- WARN rows: 0
- FAIL rows: 0
- Missing in local: 0
- Missing in remote: 0
- Local/remote bar window: `2026-01-25` through `2026-04-24`
- Leaderboard top-3 set equal: true
- Leaderboard top-3 order equal: true

Top-3 Sortino leaderboard matched exactly:

1. `RegimeAwareRSI / ETH-USD`
2. `SapphireComposite / ETH-USD`
3. `SapphireComposite / SPY`

## Soak Gate

Do not retire the local LaunchAgent until all of the following are true:

- At least 4 scheduled weekly remote cycles have completed successfully.
- Each sampled local/remote comparison has PASS verdict.
- Missing rows are 0 in both directions.
- Top-3 leaderboard set and order both match.
- Rollback remains a simple re-enable of the local LaunchAgent plist.

## Safety

No LaunchAgent was unloaded or edited. No trading execution occurred. No
Telegram message was sent. No secrets, raw payloads, or private datasets are
included in this note.
