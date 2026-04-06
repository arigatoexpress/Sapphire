---
name: deploy
description: Deploy a Sapphire service locally or check its status
disable-model-invocation: true
---

# /deploy — Sapphire Service Deployment

Deploy or restart a Sapphire service. All services run on Mac with LaunchAgents.

## Usage

```
/deploy <service>           # Start/restart the service
/deploy <service> status    # Check if running
/deploy all status          # Check all services
```

## Services

| Service | Port | LaunchAgent |
|---------|------|-------------|
| control-plane | 8082 | com.sapphire.control-plane |
| dashboard | 8080 | com.sapphire.dashboard |
| signal-logger | 18081 | com.sapphire.signal-logger |
| telegram-bot | — | com.sapphire.nemotron-bot |
| openbb | 6900 | com.sapphire.openbb-api |
| redis | 6379 | homebrew.mxcl.redis |

## How to Deploy

1. Check if the service is running: `curl -s http://127.0.0.1:<port>/health`
2. If down, restart via LaunchAgent: `launchctl kickstart -k gui/$(id -u)/<launchagent>`
3. Verify it's back: retry the health check
4. Log deployment event to `data/system_events.jsonl`

## Windows Services (via SSH)

| Service | Port | Scheduled Task |
|---------|------|---------------|
| ollama | 11434 | OllamaTailscale |
| webhook | 9090 | SapphireWebhook |

Restart via: `ssh workbench "powershell -Command Start-ScheduledTask -TaskName '<task>'"`

## Pre-deploy Checks

Before deploying, always:
1. Run `ruff check` on the service directory
2. Run related tests: `python3 -m pytest tests/unit/ -q --tb=no`
3. Check for uncommitted changes: `git status --short`
