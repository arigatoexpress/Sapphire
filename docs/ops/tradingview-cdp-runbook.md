# TradingView CDP Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: TradingView MCP tools return CDP-not-reachable errors,
or dashboard `/api/system` shows the CDP probe as down.

```bash
launchctl list com.sapphire.tradingview-cdp
```

```bash
curl -fsS http://127.0.0.1:9222/json/version | python3 -m json.tool
```

```bash
tail -n 200 /Users/aribs/autonomy-status/logs/tradingview-cdp.err
```

If `/json/version` returns valid JSON, CDP is healthy and the failure is in
the MCP layer. If it errors with connection refused, the desktop app is not
running with `--remote-debugging-port`. DO NOT kickstart the LaunchAgent while
the operator has live chart work — kickstart kills and reopens the app.
Confirm the operator is not at the chart before restart.

Live monitors: dashboard `/api/system` `cdp` field.
On-call escalation: operator (this is workbench infrastructure, not
production); p4 unless a scheduled MCP capture is blocked, then p3. This
runbook explicitly does not cover live trading paths.

This runbook covers `com.sapphire.tradingview-cdp`, the local macOS
LaunchAgent that starts TradingView Desktop with Chrome DevTools Protocol
enabled on port 9222. The CDP surface supports chart inspection and MCP-driven
TradingView automation. It must remain a workbench surface unless the operator
explicitly authorizes a specific chart or alert mutation.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.tradingview-cdp.plist` |
| Start script | `infra/scripts/start-tradingview-cdp.sh` |
| Setup guide | `docs/tradingview-cdp-setup.md` |
| Dashboard health caller | `services/dashboard/app.py` (`/api/system`) |
| Stdout log | `/Users/aribs/autonomy-status/logs/tradingview-cdp.log` |
| Stderr log | `/Users/aribs/autonomy-status/logs/tradingview-cdp.err` |
| Default local CDP port | `9222` |

## Runtime Shape

The LaunchAgent has `RunAtLoad=true` and `KeepAlive=false`. It runs:

```bash
/Users/aribs/Code/Sapphire/infra/scripts/start-tradingview-cdp.sh
```

The script:

1. Reads `CDP_PORT` from the environment, defaulting to `9222`.
2. Kills any existing TradingView Desktop process.
3. Opens TradingView with `--remote-debugging-port=$CDP_PORT`.
4. Polls `http://localhost:$CDP_PORT/json/version` for up to 24 seconds.

This is not a passive health probe. A kickstart restarts the desktop app and
can interrupt an open chart session.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.tradingview-cdp
```

Check local CDP without changing charts:

```bash
curl -fsS http://127.0.0.1:9222/json/version | python3 -m json.tool
curl -fsS http://127.0.0.1:9222/json | python3 -m json.tool
```

Check dashboard-level status:

```bash
curl -su "${AUTH_USERNAME:-sapphire}:${AUTH_PASSWORD}" \
  http://127.0.0.1:8080/api/system | \
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("cdp"))'
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/autonomy-status/logs/tradingview-cdp.log
tail -n 200 /Users/aribs/autonomy-status/logs/tradingview-cdp.err
```

Restart only when the operator is not actively using TradingView:

```bash
launchctl kickstart -k gui/$UID/com.sapphire.tradingview-cdp
```

The kickstart kills and reopens TradingView through the start script. Save any
chart work first.

## Safe Manual Checks

Read-only checks are acceptable:

- `curl /json/version`
- `curl /json` and count tabs
- dashboard `/api/system` CDP status
- MCP status commands that only inspect connection state
- chart screenshots when the operator expects the visible chart to be captured

Do not use CDP tools that create alerts, edit Pine scripts, change watchlists,
or submit broker/order actions unless the operator explicitly asks for that
specific mutation.

## Common Failures

### Port 9222 Refuses Connections

1. Check `launchctl list com.sapphire.tradingview-cdp`.
2. Read stderr for `TradingView CDP failed to come up`.
3. Confirm no other process owns the port:

   ```bash
   lsof -nP -iTCP:9222 -sTCP:LISTEN
   ```

4. If safe to interrupt TradingView, kickstart the LaunchAgent.

### CDP Responds but No TradingView Tabs Exist

The app may be on a login screen, splash page, or non-chart view. Open a chart
manually and rerun:

```bash
curl -fsS http://127.0.0.1:9222/json | python3 -m json.tool
```

The dashboard counts a tab as TradingView-related when the URL contains
`tradingview`.

### Kickstart Keeps Failing

Run the start script directly once to capture foreground output:

```bash
CDP_PORT=9222 /Users/aribs/Code/Sapphire/infra/scripts/start-tradingview-cdp.sh
```

If `open -a TradingView` fails, confirm TradingView Desktop is installed under
`/Applications/TradingView.app`.

### Windows CDP Confusion

`docs/tradingview-cdp-setup.md` documents a Windows/Tailscale path for a
separate TradingView MCP setup. The LaunchAgent in this runbook is the Mac
local path and the dashboard probes `127.0.0.1:9222`. Do not rewrite the Mac
LaunchAgent to point at Windows just because the Windows guide exists.

### MCP Tools Fail After CDP Is Healthy

CDP health only proves the browser debugging endpoint is available. MCP-level
failures can still come from missing chart tabs, stale TradingView login state,
tooling version drift, or an upstream `tradingview-mcp-v2` issue. Keep the
LaunchAgent stable and debug the MCP layer separately.

## Recovery

For a bad restart:

```bash
tail -n 200 /Users/aribs/autonomy-status/logs/tradingview-cdp.log \
  > /tmp/tradingview-cdp.log.tail
tail -n 200 /Users/aribs/autonomy-status/logs/tradingview-cdp.err \
  > /tmp/tradingview-cdp.err.tail
launchctl kickstart -k gui/$UID/com.sapphire.tradingview-cdp
```

For a port conflict:

```bash
lsof -nP -iTCP:9222 -sTCP:LISTEN
```

Identify the owning process before killing it. Do not terminate unrelated
browser or automation sessions without operator context.

## Safety Notes

- A LaunchAgent restart kills the existing TradingView Desktop process.
- CDP can mutate the visible application state; treat it as operator-control
  automation, not a read-only API.
- Do not create TradingView alerts, write Pine scripts, or alter chart state
  unless explicitly requested.
- Do not connect this surface to trade execution.
- Do not expose port 9222 beyond trusted local/Tailscale contexts.
- Do not paste chart screenshots or account-visible TradingView content into
  public issues without review.

## Escalation

Escalate when:

- CDP has been down for more than one restart attempt.
- A CDP tool creates or changes an alert unexpectedly.
- The dashboard reports CDP healthy but MCP chart tools fail repeatedly.
- The port is reachable from an unintended network interface.
- TradingView restart behavior risks interrupting operator work.

Include launchd status, `/json/version` output, tab count, last 200 log lines,
the exact command or MCP tool used, and whether any chart or alert mutation was
attempted.
