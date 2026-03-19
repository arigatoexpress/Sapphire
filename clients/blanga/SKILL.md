---
name: blanga-bis
description: Brokerage Intelligence System for Joseph Blanga — Austin MSA STNL retail
type: client
runtime: python
deploy_target: cloud-run
dependencies: [sapphire-core]
entry_point: src/main.py
test_command: pytest tests/
build_command: docker build -t blanga-bis .
---

# Blanga Intelligence System (BIS)

## Purpose
Compliance-first brokerage intelligence platform for Joseph Blanga's Austin MSA STNL retail real estate workflows. Synthesizes market intelligence, property tracking, and deal sourcing via Google Sheets integration.

## Key Files
- `src/main.py` — FastAPI wrapper
- `src/bis/api.py` — Main API router (needs modularization)
- `src/bis/scoring.py` — Propensity scoring for transaction likelihood
- `src/bis/signals.py` — Austin COA permit fetching
- `src/bis/intel.py` — Market events and news feeds
- `src/bis/google_sheets_api.py` — Sheets read/write
