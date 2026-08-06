---
source: grok-web
date: 2026-08-06
type: status
topics: [gemini, desk, public, monorepo]
title: While Gemini Phase 3 — monorepo desk_projection + warehouse schema
---

# While Gemini runs Phase 3

**Do not thrash Cloud Run / dashboard product code from plant.**

Monorepo additions for when Gemini finishes UI + Claude returns:

| Artifact | Purpose |
|---|---|
| `lib/grok/desk_projection.py` | Fresh desk block builder for telemetry publisher |
| `projects/grok/data/desk_projection_example.json` | Example shape |
| `projects/grok/data/telemetry_publisher_checklist.json` | Plant checklist |
| `docs/strategy/PAPER-OUTCOMES-WAREHOUSE-SCHEMA-2026-08-06.md` | Gemini BQ P2 |
| Data truth docs already on main | UI honesty |

Gemini should pull Sapphire after Phase 3 UI to optional-copy `public_operating_rules.json`.
