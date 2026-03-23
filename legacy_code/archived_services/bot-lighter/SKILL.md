---
name: lighter-bot
description: "PRODUCTION: Lighter Protocol trading bot on rari2"
type: service
runtime: python
deploy_target: rari2
dependencies: [sapphire-core]
entry_point: src/main.py
test_command: pytest tests/
build_command: docker build -t lighter-bot .
---

# Lighter Trading Bot

## Purpose
Production trading bot executing on Lighter Protocol via rari2 Pi. Handles order placement, position management, and PnL tracking. REVENUE-CRITICAL — changes must be tested in paper mode first.

## Operations
- Runs as `lighter-trading.service` on rari2
- Connected via ProtonVPN Switzerland
- Deploy: `scripts/deploy/deploy_to_pi.sh rari2`
