# Heartbeat Runbook

Last reviewed: 2026-04-29

This runbook covers the local Sapphire heartbeat daemon launched by
`infra/launchagents/com.sapphire.heartbeat.plist`. Its job is to sample the
local service mesh, append a compact health record, publish a local event-bus
heartbeat, and alert only when a service transitions between up and down.

This is an observability surface. It does not trade, deploy, rotate secrets,
retarget LaunchAgents, or write to external systems. It may write local
heartbeat records under `data/health/heartbeat.jsonl` and may call the local
Telegram notify tool when the already-running daemon observes a transition.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.heartbeat.plist` |
| Runtime script | `services/heartbeat/heartbeat.py` |
| Local heartbeat log | `data/health/heartbeat.jsonl` |
| LaunchAgent stdout | `data/logs/heartbeat.log` |
| LaunchAgent stderr | `data/logs/heartbeat-err.log` |
| Event topic | `service.heartbeat` |

## What It Checks

The LaunchAgent runs `services/heartbeat/heartbeat.py` continuously with a
300-second interval. Each sweep checks:

| Component | Probe |
|---|---|
| control-plane | `http://127.0.0.1:8082/health` |
| dashboard | `http://127.0.0.1:8080/` |
| signal-logger | `http://127.0.0.1:18081/health` |
| inference-proxy | `http://127.0.0.1:11435/health` |
| OpenBB API | `http://127.0.0.1:6900/api/v1/` |
| Redis | `redis-cli ping` |

HTTP 4xx responses are treated as "up" when the service is responding and the
status code is below 500. That is intentional: auth challenges and missing API
routes are not outages.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.heartbeat
```

Inspect the latest local heartbeat records:

```bash
tail -n 20 /Users/aribs/Code/Sapphire/data/health/heartbeat.jsonl
```

Inspect the LaunchAgent logs:

```bash
tail -n 100 /Users/aribs/Code/Sapphire/data/logs/heartbeat.log
tail -n 100 /Users/aribs/Code/Sapphire/data/logs/heartbeat-err.log
```

Run a one-shot local check from the repo root:

```bash
printf '{"action":"check"}' | /usr/local/bin/python3 services/heartbeat/heartbeat.py
```

The one-shot command writes a local heartbeat record and publishes the local
event-bus heartbeat. A fresh one-shot process has no prior in-memory state, so
it should not send transition alerts unless the script itself is changed.

## Expected Healthy Output

Healthy sweeps look like:

```text
Heartbeat: 6 up / 0 down
```

The JSONL record includes:

```json
{
  "timestamp": "2026-04-29T00:00:00+00:00",
  "services": {"dashboard": "up", "redis": "up"},
  "up": 6,
  "down": 0
}
```

## Common Failures

### Service Shows Down

1. Read the last heartbeat record and identify the service name.
2. Probe that service directly. Examples:

   ```bash
   curl -fsS http://127.0.0.1:8080/health
   curl -fsS http://127.0.0.1:11435/health
   redis-cli ping
   ```

3. Check the owning service runbook before restarting anything.
4. If the service has a LaunchAgent, inspect `launchctl list <label>` and the
   service log.

### Heartbeat Log Stops Updating

1. Confirm the LaunchAgent is loaded:

   ```bash
   launchctl list com.sapphire.heartbeat
   ```

2. Check stderr for Python import failures:

   ```bash
   tail -n 200 /Users/aribs/Code/Sapphire/data/logs/heartbeat-err.log
   ```

3. Confirm the plist still points at the canonical checkout:

   ```bash
   plutil -p infra/launchagents/com.sapphire.heartbeat.plist
   ```

4. Restart only after the logs explain the failure:

   ```bash
   launchctl kickstart -k gui/$(id -u)/com.sapphire.heartbeat
   ```

### Notify Tool Fails

The heartbeat daemon logs notify failures but keeps running. Treat notify
failures as an operator-console issue, not as a heartbeat outage. Check
`plugins/claw-sapphire/tools/notify.py` and the Telegram operator console
runbook before changing the heartbeat daemon.

## Safety Notes

- Do not lower the interval just to get faster alerts. Five minutes is a
  deliberate noise-reduction setting for this daemon.
- Do not add trading, Telegram command dispatch, or GCP writes to this daemon.
- Do not turn 4xx responses into outages without checking the auth behavior of
  every probed service.
- Do not delete `data/health/heartbeat.jsonl`; archive or rotate it if it grows.

## Escalation

Escalate to the service owner when:

- `down > 0` persists for three or more sweeps.
- The heartbeat process exits repeatedly under `KeepAlive`.
- The heartbeat record is healthy but the dashboard or production-readiness
  matrix reports a contradictory state.

Record the service name, last three JSONL records, relevant log lines, and the
direct probe result in the handoff.
