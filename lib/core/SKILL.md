---
name: sapphire-core
description: Shared library — risk kernel, circuit breaker, position sizing, trade models, logging
type: library
runtime: python
deploy_target: none
dependencies: []
entry_point: src/sapphire_core/__init__.py
test_command: pytest tests/unit/
---

# Sapphire Core

## Purpose
Foundation library imported by all Sapphire services. Provides risk management, position sizing, circuit breakers, trade models, health checks, and structured logging.

## Key Files
- `src/sapphire_core/risk_kernel.py` — Risk calculations and portfolio limits
- `src/sapphire_core/circuit_breaker.py` — Automatic trading halt on anomalies
- `src/sapphire_core/position_sizing.py` — Kelly criterion and fractional sizing
- `src/sapphire_core/health.py` — Health check endpoints
- `src/sapphire_core/telegram_bot.py` — Base Telegram bot client
- `src/sapphire_core/gateway.py` — OpenClaw gateway client

## API Surface
All modules export public functions. No CLI or HTTP endpoints — this is a library.
