# TradingView Orchestrator Runbook

The canonical operator guide for the Sapphire TradingView orchestrator surface.
Pair this with `docs/tradingview-cdp-setup.md` for first-time CDP wiring.

## 1. Overview

The orchestrator drives the local TradingView Desktop instance on the Mac
commander as a TA rendering engine. It:

- Calls the `tv` CLI (a thin CDP client over `--remote-debugging-port=9222`) to
  read state, set symbols/timeframes/indicator stacks, take screenshots, and
  emit OHLCV + indicator value snapshots.
- Generates Sapphire-aligned Pine v5 indicators that emit JSON alert payloads
  matching the Sapphire webhook contract, and validates them server-side
  (`tv pine check`) without touching the chart.
- Writes per-session manifests + artifacts under
  `~/Code/Sapphire/data/tradingview_ta/<session_id>/`.
- Renders the latest session, screenshots, generated Pine, and active alerts
  through the dashboard at `/showcase` → analytics page (orchestrator panel).

Source files (do not modify in this lane):

- `lib/trading/tradingview_orchestrator.py` — orchestrator class.
- `lib/trading/pine_templates.py` — Sapphire Pine v5 generator.
- `scripts/ops/tradingview_ta_capture.py` — operator CLI.
- `services/dashboard/app.py` — `/api/tradingview/orchestrator/*` endpoints.
- `services/dashboard/templates/pages/analytics.html` — orchestrator panel.

## 2. Prerequisites

- TradingView Desktop launched with `--remote-debugging-port=9222` (see
  `docs/tradingview-cdp-setup.md`). Without CDP, every `tv` call fails.
- `tv` CLI installed at `/opt/homebrew/bin/tv` (resolves via `tv` on `$PATH`
  for the LaunchAgent).
- Python 3.11+ at `/opt/homebrew/bin/python3` (matches the plists).
- Working dir conventions:
  - Artifacts: `~/Code/Sapphire/data/tradingview_ta/<session_id>/`
  - Generated Pine: `~/Code/Sapphire/pine/generated/`
  - tv CLI screenshot staging: `~/Code/tradingview-mcp-v2/screenshots/`
    (orchestrator copies + unlinks from here).

Quick sanity:

```bash
tv status && tv quote
python3 scripts/ops/tradingview_ta_capture.py probe
```

## 3. Mutation Gate

`SAPPHIRE_TV_MUTATION_ENABLED=1` is the single env gate for all chart
mutations. The CLI also requires the explicit `--mutate` flag so a typo can't
accidentally write to TV. The CLI refuses `--mutate` with a non-zero exit if
the env var is unset.

Without the gate, all setters return `{"mutated": false, "reason": "...must be 1"}`
and the orchestrator runs in pure read-only capture mode (records what is
currently on screen without changing symbol or studies).

Methods covered by the gate (from `lib/trading/tradingview_orchestrator.py`):

- `set_symbol`, `set_timeframe`, `set_pane_layout`, `setup_chart`
- `add_indicator`, `remove_indicator`, `clear_indicators`, `apply_indicator_stack`
- `pine_open`, `pine_set_from_file`, `pine_compile`, `pine_save`
- `alert_create`, `alert_delete`

Read-only methods (`probe_*`, `pine_list/get/errors/console/check_file/analyze_file/validate_file`,
`alerts_list`, `latest_manifest`, `list_sessions`, `screenshot`, `capture_*`)
work without the gate, but the deeper `capture_*` flows produce richer
manifests when mutation is enabled (chart_setup + indicator_stack steps).

## 4. CLI Reference (`scripts/ops/tradingview_ta_capture.py`)

All commands accept `--tv-bin <path>` (default `tv`) and `--out <json>` to
also write the JSON output to disk.

### Read-only

```bash
# Snapshot current TV state (state + quote + ohlcv summary + values + info)
python3 scripts/ops/tradingview_ta_capture.py probe

# Show latest captured session manifest + the most recent N sessions
python3 scripts/ops/tradingview_ta_capture.py latest --limit 10

# List Pine scripts on the TV account + locally generated templates
python3 scripts/ops/tradingview_ta_capture.py pine-list

# Server-side compile + offline static analysis of a Pine source file
python3 scripts/ops/tradingview_ta_capture.py pine-validate pine/generated/Sapphire_Watch_BINANCE_BTCUSDT.pine

# Generate a Sapphire-aligned Pine v5 indicator for one symbol (writes to
# pine/generated/, optionally validates)
python3 scripts/ops/tradingview_ta_capture.py pine-generate BINANCE:BTCUSDT --validate

# Generate the top-N market universe in one pass (read-only, validates)
python3 scripts/ops/tradingview_ta_capture.py pine-generate-batch --offline --limit 8 --validate

# List active TradingView alerts
python3 scripts/ops/tradingview_ta_capture.py alerts-list
```

### Mutation-gated

```bash
# Sweep capture: one timeframe across N top symbols. Without --mutate this is
# read-only; with --mutate it sets each symbol on the chart before capture.
SAPPHIRE_TV_MUTATION_ENABLED=1 \
python3 scripts/ops/tradingview_ta_capture.py --mutate sweep --offline --limit 6 --timeframe 60

# Deep capture: one symbol across multiple timeframes with full indicator stack
SAPPHIRE_TV_MUTATION_ENABLED=1 \
python3 scripts/ops/tradingview_ta_capture.py --mutate deep ETH \
    --tv-symbol BINANCE:ETHUSDT --timeframes 15,60,240,D

# Push a Pine source file into the TV editor (optionally compile + report errors)
SAPPHIRE_TV_MUTATION_ENABLED=1 \
python3 scripts/ops/tradingview_ta_capture.py --mutate pine-load \
    pine/generated/Sapphire_Watch_BINANCE_BTCUSDT.pine --compile
```

If `--mutate` is passed but `SAPPHIRE_TV_MUTATION_ENABLED` is not `1`, the CLI
prints `{"status": "error", "reason": "SAPPHIRE_TV_MUTATION_ENABLED must be 1 for --mutate"}`
to stderr and exits 1.

## 5. Dashboard Endpoints

All require dashboard auth (`AUTH_PASSWORD`, default `sapphire`). Mounted in
`services/dashboard/app.py`.

| Endpoint | Returns |
|---|---|
| `GET /api/tradingview/orchestrator/sessions?limit=N` | Recent sessions: `[{session_id, generated_at, schema_version, symbol_count, timeframe_count}]` (default N=20, max 100). |
| `GET /api/tradingview/orchestrator/latest` | Full latest manifest as written by `capture_sweep` / `capture_symbol_deep` (or `{manifest: null}` if none). |
| `GET /api/tradingview/orchestrator/probe` | Live read-only probe: `{state, quote, values}` from the running TV. |
| `GET /api/tradingview/orchestrator/artifacts/<path>` | Serves a single artifact file (PNG or JSON) from `data/tradingview_ta/`. Path-traversal guarded; 404 on missing. |
| `GET /api/tradingview/orchestrator/pine` | `{tv_account: {ok, scripts}, generated_local: [...]}` — Pine on the TV account + locally generated templates. |
| `GET /api/tradingview/orchestrator/alerts` | `{alert_count, alerts}` — active TV alerts (read-only). |

The analytics page panel (`templates/pages/analytics.html`) renders sessions,
the latest manifest summary, screenshot grid (4-up), Pine table, and alert
table. The "Read-Only" / "Mutation On" badge is driven by
`latest.mutation_enabled` from the most recent session manifest.

## 6. Pine ↔ Webhook Contract

Generated indicators (`render_sapphire_watch_indicator`) emit `alert(...)` JSON
that maps 1:1 onto `services/webhook/src/receiver.py::TradingViewAlert.from_webhook`.

Field map:

| Pine source | Webhook field | Receiver use |
|---|---|---|
| `syminfo.ticker` | `symbol` | uppercased; if `EXCHANGE:SYM` form, the `:` prefix is stripped; then `SYMBOL_MAP` aliasing |
| (literal) `long` / `short` / `exit_long` / `exit_short` | `action` | lowercased; must be in `VALID_ACTIONS` |
| `close` | `price` | `float()` |
| `time` | `timestamp` | passed through (defaults to `now(UTC).isoformat()` if missing) |
| `timeframe.period` | `interval` | passed through |
| `syminfo.prefix` | `exchange` | passed through |
| (literal) `"sapphire_watch_indicator"` | `strategy` | recorded in alert history |
| (literal) `"tradingview_pine"` | `source` | passed through |

`VALID_ACTIONS` (from `services/webhook/src/receiver.py`):

```
buy, sell, long, short, exit, close,
entry_long, entry_short, exit_long, exit_short
```

The generator emits only `long` / `short` / `exit_long` / `exit_short`, all of
which are accepted. To wire a generated indicator end-to-end:

1. `pine-generate` (or `pine-generate-batch`) writes the `.pine` + sidecar JSON.
2. `pine-validate` (or `--validate` flag) runs `tv pine analyze` + `tv pine check`
   server-side — no chart manipulation needed.
3. `pine-load --compile` (mutation-gated) pushes into the editor, compiles, and
   reports any errors. After Save & Apply on the chart, configure a TV alert
   with `{{strategy.order.alert_message}}` (or any payload-passing template)
   pointing at the Sapphire webhook receiver.

## 7. Scheduled Jobs (LaunchAgents)

Both run on the Mac commander, both are read-only.

| Label | Schedule | What it runs | Output |
|---|---|---|---|
| `com.sapphire.tradingview-ta-capture` | Every 4h: 02:30, 06:30, 10:30, 14:30, 18:30, 22:30 local | `tradingview_ta_capture.py sweep --offline --limit 6` | `~/autonomy-status/logs/tradingview-ta-capture.{log,err}` plus a session dir under `data/tradingview_ta/` |
| `com.sapphire.tradingview-pine-batch` | Daily 13:00 local | `tradingview_ta_capture.py pine-generate-batch --offline --limit 8 --validate` | `~/autonomy-status/logs/tradingview-pine-batch.{log,err}` plus the latest summary at `~/autonomy-status/logs/tradingview-pine-batch-latest.json` |

Manage:

```bash
launchctl list | grep sapphire.tradingview
launchctl unload ~/Library/LaunchAgents/com.sapphire.tradingview-ta-capture.plist
launchctl load   ~/Library/LaunchAgents/com.sapphire.tradingview-ta-capture.plist
```

## 8. Windows TV Agent

`services/windows_tv_agent/server.py` is a read-only Windows-side health probe.
It does **not** drive TradingView itself — the canonical Sapphire topology has
TV running on the Mac commander.

Status states (`build_status_payload`):

| `WINDOWS_TV_AGENT_CDP_REQUIRED` | CDP healthy? | `status` |
|---|---|---|
| unset / `0` (default) | yes | `healthy` |
| unset / `0` (default) | no  | `agent_only` ← process up, no local TV CDP. Expected on the canonical topology. |
| `1` | yes | `healthy` |
| `1` | no  | `degraded` ← real failure: agent expects local TV but can't reach `:9222`. |

Set `WINDOWS_TV_AGENT_CDP_REQUIRED=1` only if you actually run TradingView on
the Windows host and want the agent to fail loud when CDP drops. On the
default Mac-only topology, leave it unset.

Restart on Windows (PowerShell as admin):

```powershell
Stop-ScheduledTask  -TaskName "Sapphire-TV-Agent"
Start-ScheduledTask -TaskName "Sapphire-TV-Agent"

Stop-ScheduledTask  -TaskName "SapphireWebhook"
Start-ScheduledTask -TaskName "SapphireWebhook"
```

## 9. Troubleshooting

### a) Screenshot missing from artifact dir

The `tv` CLI saves PNGs into its own staging directory
(`~/Code/tradingview-mcp-v2/screenshots/`). The orchestrator's `screenshot()`
method copies the file into the session dir and unlinks the source. If the
artifact is missing under `data/tradingview_ta/<session>/`:

```bash
ls -lt ~/Code/tradingview-mcp-v2/screenshots/ | head
```

If a matching `*<symbol>_<timeframe>_screenshot*.png` exists there, the copy
step failed (permissions, disk full, dir missing). Re-run the capture or
manually `cp` the file into the session dir.

### b) `tv pine check` returns `success=true` but `compiled=false`

`pine-validate` returns `ok=True` only when both `analyze` and `check`
succeed. If `check.ok=True` but the payload reports `compiled=false`, the
script analyzed cleanly but the server-side compile rejected it. Read the
error list:

```bash
python3 scripts/ops/tradingview_ta_capture.py pine-validate <path> --out /tmp/pv.json
jq '.result.check.payload.errors[]' /tmp/pv.json
```

Common causes for the Sapphire watch template specifically: stray quotes in
`webhook_payload_extra` values (the renderer JSON-escapes them, but values
must be JSON-safe scalars), or feeding a template name that contains
characters Pine rejects in `indicator(title=...)`.

### c) Sweep WARN with `degraded_services=windows_tv_agent`

The Mac-side health collector (NOT the orchestrator) flagged the Windows agent
as `degraded`. Two cases:

1. Windows host is running TV locally and CDP dropped — restart TV with
   `--remote-debugging-port=9222` and the agent task (see §8).
2. Windows host is **not** running TV (canonical topology) but
   `WINDOWS_TV_AGENT_CDP_REQUIRED=1` is set in the agent env. The expected
   status for that host is `agent_only`, not `healthy`. Unset the flag (or set
   to `0`) and restart `Sapphire-TV-Agent`.

If `agent_only` is showing as a degraded signal upstream, the upstream
collector should be treating `agent_only` as healthy on the Mac-only
topology — that's a collector bug, not an orchestrator issue.

### d) Screener Pine: alerts misroute / `MAX_SCREENER_SYMBOLS` cap

The static analyzer (`lib/pine/static_analyzer.py`) enforces three
screener-specific rules whenever a Sapphire-tagged Pine source has more
than one `request.security()` call:

1. The total `request.security()` count must not exceed
   `MAX_SCREENER_SYMBOLS` (40, mirroring `lib.trading.pine_templates`).
   Trim the universe or split into two screeners.
2. Every `request.security()` must bind to a tuple — the screener
   contract returns OHLCV-shaped tuples that drive the multi-action
   alert block; a bare scalar binding (`x = request.security(...)`) is
   warned about.
3. Alert payloads must hard-code the firing symbol literal. Using
   `syminfo.ticker` in the JSON `"symbol"` slot resolves to the chart's
   ticker (not the firing one) and silently misroutes every alert. The
   analyzer rejects this as an error.

Run `python3 scripts/lint_pine.py --strict <file.pine>` during promotion
— `--strict` promotes warnings (e.g. unpaired `strategy.entry/close` or
partial tuple bindings) to errors so pre-promote diffs surface them.

## 10. Safety

- **Read-only by default.** Every mutation is gated by
  `SAPPHIRE_TV_MUTATION_ENABLED=1` *and* the explicit `--mutate` flag on the
  CLI. The two scheduled LaunchAgents are read-only (`sweep --offline` and
  `pine-generate-batch --offline --validate`); neither passes `--mutate`.
- **No live trading.** The orchestrator never submits orders. The webhook
  contract feeds the signal pipeline, which is paper-only unless the trading
  critical path is independently enabled (and that path has its own caps and
  killswitch — see `docs/ops/hyperliquid-live-trading-runbook.md`).
- **No Telegram sends.** The orchestrator never calls a Telegram surface.
- **Manifest safety block.** Every session manifest carries
  `safety: {live_trading_enabled: false, telegram_sends_enabled: false, execution_policy: "analysis_only_no_order_submit"}`
  for downstream consumers to assert against.
- **Path-traversal guard.** The dashboard artifact endpoint resolves and
  validates that the requested path stays under `data/tradingview_ta/`.
