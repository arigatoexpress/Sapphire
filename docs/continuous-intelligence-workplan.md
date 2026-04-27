# Continuous Intelligence Workplan

Date: 2026-04-27

## Decision

Sapphire should become a continuous intelligence loop before it becomes a
continuous executor. The first shipped primitive is a read-only task planner:

```bash
python3 -m lib.autonomy.continuous_intelligence --pretty
```

Dashboard API:

```bash
GET /api/autonomy/continuous-intelligence
```

The planner does not dispatch tasks, submit orders, sign payloads, send
Telegram messages, or write artifacts by default. It enumerates real work that
Mac, Windows GPU inference, GitHub Actions, and human review can claim.

## Operating Loop

1. Observe market universe, sovereign thesis, strategy performance, and
   backtest artifacts.
2. Generate claimable tasks for strategy backtests, confluence scans, thesis
   research, data staging, institutional tokenization, agentic payments,
   regional OODA readiness, TradingView parity checks, and promotion gates.
3. Dispatch only read-only or dry-run work to Windows GPU, Mac local, or GitHub
   Actions.
4. Store artifacts under a future ignored autonomy path such as
   `data/.autonomy/continuous_intelligence/`.
5. Promote strategy, scheduler, or executor changes only through a human-reviewed
   PR with rollback notes and safety gates.

## Why This First

Ari wants Windows desktop inference to keep testing strategies, checking
confluence, improving research, and finding new thesis evidence. The system
already has useful components:

- ETH-first market universe and venue symbol normalization.
- Sovereign thesis evidence ledger.
- Strategy-performance feedback aggregation.
- CPCV backtest harness and weekly backtest artifacts.
- TradingView dry-run capability matrix.
- x402 middleware, Base/USDC agent-payment rails, and an ETH-centered
  tokenized-finance thesis.

What was missing was a contract between those components and the worker mesh.
`lib.autonomy.continuous_intelligence` now gives the mesh a task list with
priority, runtime, cadence, inputs, commands or prompts, expected artifacts,
blockers, and acceptance gates.

## Initial Lanes

- `data_staging`: prepare deterministic OHLCV for CPCV runs.
- `strategy_backtest`: run CPCV gates against preferred ETH-centered symbols.
- `confluence_scan`: ask Windows GPU inference to find agreement and conflict
  across thesis, market, performance, and catalyst inputs.
- `strategy_mutation`: generate hypotheses only; no file edits or auto-apply.
- `thesis_research`: refresh privacy, quantum-risk, Ethereum economic-zone,
  institutional tokenization, agentic payments, and investment-catalyst
  evidence.
- `ops_validation`: keep TradingView alert schema parity and x402 agent-market
  smoke tests deep and dry-run.
- `regional_ooda`: review regional-intel manifest v2 readiness, source-health
  coverage, and dropped-row provenance counts using local/export actions only.
- `promotion_gate`: convert evidence into a human-review packet before code or
  executor behavior changes.

## Safety

The planner hard-codes:

- `execution_enabled=false`
- `live_trading_enabled=false`
- `telegram_sends_enabled=false`
- `writes_by_default=false`

Every task has `safe_mode` set to `read_only`, `dry_run`, or `paper`. Live
trading, order signing, order submission, and Telegram sends remain forbidden.
Regional OODA act items are recommendations to review local status, export from
the workbench, or open a PR before any GCP or Foundry write.

## Next PRs

1. Add an ignored artifact sink and append-only task-result schema.
2. Add a dry-run dispatcher that leases P1 tasks to Windows GPU or GitHub
   Actions without secrets or broker mutation.
3. Add a dashboard panel that shows tasks, blockers, stale inputs, and promotion
   packets.
4. Add periodic research collectors for official/primary ETH and investment
   sources, with freshness and invalidation timestamps.
5. Add backtest-result comparators that automatically mark candidate strategy
   variants as reject, needs-data, or ready-for-human-review.
6. Add tokenization/agentic-payment artifact consumers so official source
   updates can refresh the thesis ledger without enabling real payments.
