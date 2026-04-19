# Foundry Handoff Prompt

You are continuing Foundry strategy and implementation planning for Sapphire OS in `/Users/aribs/Code/Sapphire`.

## Context

Sapphire is an autonomous trading, intelligence, and operator-control platform with:

- local event/state in `data/`
- operational surfaces in `services/dashboard/` and `services/control-plane/`
- telemetry and warehouse sync into BigQuery/GCS via `services/pipeline/`
- an inference proxy, agent runtime, paper trading, prediction scoring, and Telegram governance

The research memo already written is:

- `/Users/aribs/Code/Sapphire/docs/foundry-strategy-2026-04-19.md`

Read that file first. Treat it as the current best synthesis unless you find stronger evidence in official Palantir docs.

## Goal

Turn the Foundry strategy from a research memo into a concrete Sapphire implementation and demo plan that is credible, staged, and technically specific.

## What to focus on

1. Confirm the best Foundry product surfaces for Sapphire:
   - Ontology
   - Actions
   - Workshop
   - Object Views
   - AIP Logic
   - Agent Studio
   - Developer Console
   - OSDK
   - AIP Evals
   - AIP Observability

2. Produce a phase-by-phase build plan for a first working showcase:
   - what data enters Foundry first
   - how to model the first ontology object types and links
   - which actions to implement first
   - what the first Workshop app should contain
   - what the first AIP Agent should do
   - how to expose a small external app through Developer Console or OSDK

3. Map Sapphire repo artifacts to Foundry ingestion candidates:
   - JSONL / NDJSON / BigQuery / GCS / selected APIs
   - prefer existing structured outputs over raw logs

4. Identify the best “wow demo” sequence for investors, partners, or users:
   - mission control board
   - incident drill-down
   - agent explanation
   - proposal-first action
   - approval / guardrails
   - traces / evals / observability

5. Call out risks and anti-patterns:
   - rebuilding Sapphire inside Foundry
   - ingesting too much too early
   - overusing LLM autonomy
   - weak action guardrails
   - unclear ontology boundaries

## Deliverables

- update or extend the strategy doc if needed
- produce a practical implementation plan with milestones
- propose the first ontology schema in enough detail to build
- propose the first 3 to 5 actions with clear submission criteria
- propose the first agent prompt/spec
- propose the first Workshop layout and object views
- list required Palantir setup steps and API/auth assumptions
- include official Palantir source links

## Constraints

- Use official Palantir docs as the primary source base.
- Tailor recommendations to Sapphire’s actual repo architecture, not generic enterprise examples.
- Prefer the smallest high-signal showcase over a broad platform rewrite.
- Do not disturb unrelated uncommitted work in the repo.

## Nice-to-have

- draft a sample ontology object model table
- draft a sample action approval policy table
- suggest a thin ingestion bridge or export format from Sapphire to Foundry
- identify which parts should stay in Sapphire versus move into Foundry surfaces
