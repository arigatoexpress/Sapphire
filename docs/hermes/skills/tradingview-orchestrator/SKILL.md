---
name: tradingview-orchestrator
description: Read-only Sapphire TradingView orchestrator surface. Use for "what's the latest TA score for ETH", "list my saved Pine scripts", "probe TradingView state", "list active TV alerts", "generate a Sapphire Pine indicator/strategy for <symbol>", or "run a read-only TV sweep". Wraps the `sapphire_tradingview` plugin tool — every action is read-only by construction; mutation paths live behind `scripts/ops/tradingview_ta_capture.py` under operator supervision.
version: 1.0.0
author: Sapphire
metadata:
  hermes:
    tags: [tradingview, orchestrator, pine, ta, read-only, sapphire]
    commands: [/tvo]
    requires:
      - Sapphire repo at ~/Code/Sapphire
      - Python 3.11+ at /opt/homebrew/bin/python3
      - For probe / sweep / list_alerts: TradingView Desktop with --remote-debugging-port=9222 (probe and sweep degrade gracefully when CDP is down)
---

# /tvo — TradingView Orchestrator (Read-Only)

Hermes wrapper over the `sapphire_tradingview` plugin tool, which exposes the
read-only orchestrator surface from `lib/trading/tradingview_orchestrator.py`
and `lib/trading/pine_templates.py`.

**Companion to the existing `tradingview` skill, not a replacement.** The legacy
`tradingview` skill drives the `tv` CLI directly and includes mutation paths.
This skill stays read-only: no chart mutation, no Telegram, no live trading,
no order submission.

## Action Set

| action | Inputs | Returns |
|---|---|---|
| `probe` | optional `symbol` | `{state, quote, values, mutation_enabled:false}`. |
| `score` | optional `limit` (default 10) | Top-N rows from latest capture manifest, ranked by `abs(score)`. |
| `list_pine` | — | `{tv_account_scripts, generated_local}`. |
| `list_alerts` | — | Active TradingView alerts. |
| `generate_pine` | required `symbol`; optional `kind`=`indicator`(default)\|`strategy`, `name` | Renders a Sapphire Pine v5 source under `pine/generated/`. **No TV push, no compile, no save.** |
| `sweep` | optional `limit` (default 6), `timeframe` (default `"60"`), `offline` (default `true`) | Captures whatever's currently on-screen for the planned symbols. Returns manifest summary. |

The dispatcher hard-blocks orchestrator mutation methods (`set_symbol`,
`set_timeframe`, `setup_chart`, `apply_indicator_stack`, `pine_set_from_file`,
`pine_compile`, `pine_save`, `pine_promote`, `alert_create`, `alert_delete`,
`add_indicator`, `remove_indicator`, `clear_indicators`, `pine_open`) even
when `SAPPHIRE_TV_MUTATION_ENABLED=1` is exported.

## Invocation

```bash
cd ~/Code/Sapphire

echo '{"action":"probe"}'                                              | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"score","limit":5}'                                    | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"list_pine"}'                                          | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"list_alerts"}'                                        | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"generate_pine","symbol":"BINANCE:BTCUSDT"}'           | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"generate_pine","symbol":"BINANCE:ETHUSDT","kind":"strategy"}' | python3 plugins/claw-sapphire/tools/tradingview.py
echo '{"action":"sweep","limit":6,"timeframe":"60","offline":true}'    | python3 plugins/claw-sapphire/tools/tradingview.py
```

Every call returns `{action, ok, data|error}`; the tool returns `ok=false` with
a string `error` instead of raising.

## When to Use

- "Probe TradingView" / "current TV state" → `probe`
- "Latest TA score for <symbol>" / "top scoring symbols" → `score`
- "List my saved Pine scripts" → `list_pine`
- "Active TradingView alerts" → `list_alerts`
- "Generate a Sapphire Pine indicator/strategy for <symbol>" → `generate_pine`
- "Run a TV sweep" / "Capture current TA snapshot" → `sweep`

## What This Skill Does NOT Do

No chart mutation, no Pine push/compile/save, no alert create/delete, no
order submission, no Telegram send. For any of those, point the operator at
`docs/ops/tradingview-orchestrator-runbook.md` §3-§4 (mutation gate + CLI).

## See Also

- `docs/ops/tradingview-orchestrator-runbook.md` — operator runbook.
- `docs/adr/0012-tradingview-orchestrator-architecture.md` — design decisions.
- Plugin tool: `plugins/claw-sapphire/tools/internal/tradingview.py`.
- Legacy mutating sibling skill: `tradingview` (separate, retain for chart control).
