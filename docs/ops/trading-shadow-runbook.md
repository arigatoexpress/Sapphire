# Trading Shadow Controller Runbook

Last reviewed: 2026-04-29

This runbook covers `com.sapphire.trading-shadow-controller`, the paper-shadow
market screening LaunchAgent that ranks crypto candidates, writes a capped
shadow report, and emits manual dry-run order instructions for operator review.

The controller cannot spend money. It does not read Robinhood secrets, does not
include `--execute`, does not sign orders, and is not wired into dashboard,
scheduler, Telegram, or TradingView live-submit paths. Keep it that way unless
Ari explicitly authorizes a separate live-trading promotion PR.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.trading-shadow-controller.plist` |
| CLI wrapper | `scripts/ops/trading_shadow_controller.py` |
| Core report builder | `lib/trading/shadow_controller.py` |
| Strategy lab doc | `docs/trading-strategy-lab.md` |
| Robinhood readiness doc | `docs/ops/robinhood-real-funds-readiness.md` |
| Routine manifest row | `docs/routines-manifest.md` |
| Unit tests | `tests/unit/test_trading_shadow_controller.py` |
| Plist safety tests | `tests/unit/test_launchagent_plists.py` |
| Dashboard paper endpoint test | `tests/integration/test_dashboard_endpoints.py` |
| Latest report | `data/trading/shadow-controller-latest.json` |
| Stdout log | `/Users/aribs/Library/Logs/sapphire/trading-shadow-controller.log` |
| Stderr log | `/Users/aribs/Library/Logs/sapphire/trading-shadow-controller.err` |

## Schedule

The LaunchAgent has `RunAtLoad=true`, `StartInterval=1800`, and
`ThrottleInterval=300`. It runs every 30 minutes:

```bash
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/scripts/ops/trading_shadow_controller.py --output
```

The committed plist sets only `PATH`, `HOME`, and `PYTHONPATH`. It must not
contain Robinhood, broker, exchange, signing, or secret environment variables.

## Data Flow

```text
LaunchAgent every 30 minutes
  -> scripts/ops/trading_shadow_controller.py --output
  -> lib.trading.shadow_controller.build_shadow_trading_report()
  -> public/fallback market universe
  -> capped paper candidates and blocked live-surface evidence
  -> data/trading/shadow-controller-latest.json
```

Default policy:

| Control | Value |
|---|---|
| Mode | `paper_shadow` |
| Live execution | `False` |
| Requested first-order notional | capped to `$5` |
| Daily real cap reference | `$10` |
| Max candidates | `3` |
| Manual confirmation | required |
| Limit orders only | `True` |

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.trading-shadow-controller
launchctl print gui/$(id -u)/com.sapphire.trading-shadow-controller
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/trading-shadow-controller.log
tail -n 200 /Users/aribs/Library/Logs/sapphire/trading-shadow-controller.err
```

Inspect the latest report:

```bash
test -f data/trading/shadow-controller-latest.json && \
  python3 -m json.tool data/trading/shadow-controller-latest.json
```

Run the safe test path:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_trading_shadow_controller.py \
  tests/unit/test_launchagent_plists.py \
  tests/integration/test_dashboard_endpoints.py::test_trading_shadow_controller_endpoint_is_paper_only -q
```

Run an offline deterministic report:

```bash
/usr/local/bin/python3 scripts/ops/trading_shadow_controller.py --offline
```

Run an offline report to a noncanonical path:

```bash
/usr/local/bin/python3 scripts/ops/trading_shadow_controller.py \
  --offline \
  --output /tmp/shadow-controller-latest.json
```

## Paper-Only Invariants

The report must always include:

- `mode == "paper_shadow"`
- `live_execution_enabled == false`
- `paper_trading_enabled == true`
- bounded candidate notional at or below the pilot cap
- `blocked_live_actions` for scheduler, dashboard, Telegram, and TradingView
- `manual_order_candidate.execute_flag_included == false` when candidates exist
- no `--execute` in generated command arrays

The plist safety test pins the key launchd invariants: `--output` is present,
`--execute` is absent, and no `ROBINHOOD*` environment variable is embedded.

## Common Failures

### Report Has No Candidates

This is normal when no token clears confidence, tradability, momentum, and risk
gates. Inspect `watchlist`, `blockers`, and `operator_next_step` before changing
thresholds.

### Public Market Data Fails

The CLI defaults to live public market data, but `--offline` uses the
deterministic fallback universe. Use offline mode to separate code regressions
from public-source availability.

### Candidate Command Looks Executable

This is a release blocker. The generated command must omit `--execute` and use a
placeholder guarded limit price. If `--execute` appears anywhere in the
shadow-controller report or plist, pause the routine and fix tests before
resuming.

### Dashboard Endpoint Looks Live

`GET /api/trading/shadow-controller` is a paper report endpoint. Use
`?offline=1` for deterministic local checks. It must not import submit
functions or read Robinhood credentials.

### Output File Stale

Check launchd state and logs. The routine health table tracks
`data/trading/shadow-controller-latest.json`; if the file is stale but the
LaunchAgent is healthy, run an offline noncanonical report first, then decide
whether to let the scheduled job refresh the canonical file.

## Recovery

Pause by unloading only if there is a live-execution regression or repeated
bad report. For routine review, prefer disabling via a repo PR or routine pause
mechanism rather than ad hoc plist edits.

Preserve the latest report before replacing it:

```bash
test -f data/trading/shadow-controller-latest.json && cp \
  data/trading/shadow-controller-latest.json \
  data/trading/shadow-controller-latest.json.$(date -u +%Y%m%dT%H%M%SZ).bak
```

Then run:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_trading_shadow_controller.py -q
/usr/local/bin/python3 scripts/ops/trading_shadow_controller.py --offline
```

## Safety Notes

- Do not add `--execute` to this LaunchAgent or generated command.
- Do not add Robinhood, Hyperliquid, broker, signing, or secret env vars to the
  plist.
- Do not wire scheduler, dashboard, Telegram, TradingView, or webhook paths to
  live submission.
- Do not raise notional caps or lower confidence gates without tests and
  explicit operator approval.
- Do not replace paper candidates with real orders from this runbook.
- Do not delete historical shadow reports or backups during incident review.

## Escalation

Escalate immediately when:

- Any shadow-controller path includes `--execute`.
- A report claims live execution is enabled.
- A broker credential appears in plist env or report output.
- The dashboard or scheduler imports a live submit path.
- A candidate exceeds the pilot cap or bypasses manual confirmation.

Include launchd status, latest report path, `risk_policy`, candidate command
arrays, blocked live actions, last 200 log lines, and the exact command that
produced the report.
