---
name: sapphire-agents
description: Agent dispatch — OpenClaw, NemoClaw, orchestrator, runtime policy
type: library
runtime: python
deploy_target: none
dependencies: [sapphire-core]
entry_point: src/sapphire_agents/__init__.py
test_command: pytest tests/unit/
---

# Sapphire Agents

## Purpose
Agent orchestration library. Dispatches tasks to OpenClaw (Mac/Cloud), NemoClaw (Windows GPU), or Kimi Claw (rari1). Manages runtime policies and token budgets.

## Key Files
- `src/sapphire_agents/openclaw_dispatch.py` — OpenClaw gateway client
- `src/sapphire_agents/orchestrator.py` — Task routing and lifecycle
- `src/sapphire_agents/runtime_policy.py` — Agent permissions and boundaries
- `src/sapphire_agents/token_governor.py` — LLM token budget management
