---
source: grok-web
date: 2026-08-06
type: research
topics: [public, telemetry, trading-data, gemini]
title: Public trading data truth — live rich, desk stale, widgets sparse
---

# Public trading data truth

**Canonical:** `docs/strategy/PUBLIC-TRADING-DATA-TRUTH-2026-08-06.md`  
**Gemini:** `docs/handoffs/GEMINI-DATA-TRUTH-AND-PUBLIC-SURFACE-2026-08-06.md`  
**Claude plant:** `docs/handoffs/CLAUDE-TELEMETRY-DESK-REFRESH-2026-08-06.md`  
**Audit:** `python3 scripts/ops/public_surface_audit.py`

Live `/api/v1/live` is rich; desk stale; widgets gate unavailable by design on Cloud Run.
Fix = publisher desk refresh + UI honesty + public operating rules (no fake PnL).
