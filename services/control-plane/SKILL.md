---
name: control-plane
description: PM hub — project board, task scoring, event stream, Telegram notification-only status
type: service
runtime: python
deploy_target: rari1
dependencies: [sapphire-core, sapphire-agents]
entry_point: app/main.py
test_command: pytest tests/
build_command: docker build -t control-plane .
---

# Control Plane

## Purpose
Central project management and coordination service. Manages the project board,
scores tasks, and publishes local events. Telegram notification-only delivery
belongs to the separate secure-review rail; this service accepts no Telegram
authority.

## Event System
Publishes tagged events: `task.created`, `task.completed`, `deploy.started`, `alert.fired`
Tags: `project:`, `agent:`, `priority:`, `type:`
Agents subscribe to relevant tags for notifications.

## Key Files
- `app/main.py` — FastAPI entry point (health, events, tasks, Kimi bridge, constant-refusal Telegram tombstone)
- `app/control_plane.py` — State management and persistence (SQLite default)
- `app/project_board.py` — Project and task CRUD
- `app/scoring.py` — Task priority scoring
- `app/event_stream.py` — JSONL event log (no GCP — file-based)
- `app/kimi_bridge.py` — `/api/kimi/pm` dispatch endpoint
- `app/frontend/` — PM dashboard HTML pages

## On-prem Deploy (rari1)

```bash
bash infra/pi/rari1/deploy-control-plane.sh
# Service: http://100.x.x.x:8082
# Kimi bridge: POST /api/kimi/pm  X-Control-Token: <CONTROL_PLANE_TOKEN>
```
