---
name: control-plane
description: PM hub — project board, task scoring, event stream, Telegram integration
type: service
runtime: python
deploy_target: cloud-run
dependencies: [sapphire-core, sapphire-agents]
entry_point: src/main.py
test_command: pytest tests/
build_command: docker build -t control-plane .
---

# Control Plane

## Purpose
Central project management and coordination service. Manages the project board, scores tasks, publishes events, and integrates with Telegram for agent-human communication.

## Event System
Publishes tagged events: `task.created`, `task.completed`, `deploy.started`, `alert.fired`
Tags: `project:`, `agent:`, `priority:`, `type:`
Agents subscribe to relevant tags for notifications.

## Key Files
- `src/control_plane.py` — State management and persistence
- `src/project_board.py` — Project and task CRUD
- `src/scoring.py` — Task priority scoring
- `src/event_stream.py` — Event publishing and subscription
- `src/telegram_api.py` — Telegram bot integration
- `src/frontend/` — PM dashboard HTML pages
