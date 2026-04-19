# Foundry Strategy for Sapphire

**Date:** 2026-04-19  
**Scope:** How to use Palantir Foundry and AIP to enrich Sapphire and showcase what Foundry is genuinely good at.

## Executive Summary

Foundry is not most valuable to Sapphire as "another place to host dashboards" or "another generic AI wrapper."

The highest-value use for Sapphire is:

1. **Ontology + Actions as an operational control layer**
2. **Workshop + Object Views as the operator surface**
3. **AIP Logic + Agent Studio as governed AI copilots and automation**
4. **Developer Console + OSDK as the external app and API surface**
5. **AIP Evals + Observability as the trust and demo layer**

For Sapphire specifically, Foundry is strongest when it becomes the **governed operational twin** of the platform:

- services
- agents
- inference tiers
- predictions
- paper trades
- alerts
- incidents
- research artifacts
- operator decisions

The best showcase is not "we connected Foundry to our data."  
It is:

> "We turned Sapphire into an ontology-backed mission-control system where humans and agents can inspect live state, explain anomalies, propose actions, approve or reject write-backs, and audit everything."

## What Foundry Is Best At For Sapphire

### 1. Ontology-backed operations

Palantir’s own platform overview emphasizes the Ontology as the layer that combines **data, logic, and actions** into an AI-accessible operational environment. That matches Sapphire unusually well, because Sapphire already has all three:

- data: metrics, health, predictions, trades, threat intel, repo/project state
- logic: risk kernel, heuristics, classifiers, agent routing, paper trading, forecasting
- actions: alerts, approvals, state transitions, notifications, workflow triggers, external side effects

For Sapphire, that means the Ontology should not just mirror datasets. It should model operational entities.

### 2. Human + AI workflows, not just chat

AIP Logic, Agent Studio, Workshop, and Actions are most compelling when AI is embedded into workflows with permissions, application state, and action constraints. That is much better suited to Sapphire than a raw "chat with your data" experience.

### 3. Governed write-backs and approvals

Foundry Actions, submission criteria, and permissions are a strong fit for risky operational decisions. This matters for Sapphire because many desirable automations should remain proposed or reviewable:

- pause an agent
- change routing tier policy
- approve a paper-trade promotion rule
- mark an incident as mitigated
- escalate a bad model or service tier

### 4. Demoable lineage, observability, and evals

Sapphire already has rich internal telemetry. Foundry adds a way to present:

- where operational truth comes from
- what logic and agents did
- which actions were proposed or executed
- how AI behavior was evaluated over time

This is one of the best showcase angles for customers or partners.

## Best-Fit Foundry Use Cases For Sapphire

### A. Sapphire Mission Control

Build a Workshop application as the main operator surface for:

- service health
- inference tier routing
- agent status
- task queue state
- prediction and signal summaries
- incident triage
- action proposals

Why this is the best showcase:

- Workshop is meant for operational applications
- Object Views give clean drill-down on ontology objects
- AIP Agent widgets can read and write application state
- commands can orchestrate cross-app workflows
- read-only dashboards can be separated cleanly for broader audiences

### B. Operator Copilot / AIP Agent

Build a single strong agent first, not ten weak ones.

Recommended agent:

**Sapphire Operator Agent**

It should answer:

- What is degraded right now?
- Why did the proxy fall back to Mac?
- Which models or tiers are failing most?
- Which predictions were wrong most recently?
- Which routines are stale or missing artifacts?
- What should the operator do next?

It should be able to:

- query ontology objects
- call functions for deeper analysis
- propose actions with confirmation
- update Workshop variables
- explain its reasoning and traces

### C. Proposal-first automation

Use AIP Logic for structured, reviewable workflows before attempting full autonomy.

Best first Logic functions:

- incident summarizer
- stale-artifact triage
- prediction failure explainer
- repo drift / hygiene summarizer
- threat-to-service impact assessor

These should return either:

- a proposed classification
- a recommended next step
- a draft ontology edit

Then connect them to Actions or Automate.

### D. External-facing Sapphire app via Developer Console + OSDK

This is likely the best way to showcase Foundry externally.

Build a small custom application with:

- ontology-scoped access
- hosted frontend or external frontend
- generated SDKs
- app metrics
- optional embedded agents

Good public/demo-facing slices:

- read-only reliability board
- prediction track-record explorer
- incident and remediation explorer
- AI operations observability viewer

### E. AI quality and trust plane

Use AIP Evals and AIP Observability to create a visible trust layer for Sapphire’s AI workflows:

- eval suites for prompt / agent changes
- comparisons across model choices
- traces of agent / function executions
- metrics for function and action success/failure

This is a better demo than "we have an agent" because it shows production discipline.

## Recommended Ontology For Sapphire

### Core operational objects

- `Service`
- `Agent`
- `InferenceTier`
- `ModelEndpoint`
- `Prediction`
- `PaperTrade`
- `Signal`
- `Incident`
- `RoutineRun`
- `Alert`
- `ResearchArtifact`
- `Project`
- `Task`
- `ActionProposal`
- `Decision`

### Important links

- `Service -> Incident`
- `Service -> Alert`
- `Agent -> Task`
- `Agent -> Incident`
- `Prediction -> PaperTrade`
- `Prediction -> ModelEndpoint`
- `RoutineRun -> ResearchArtifact`
- `ActionProposal -> Incident`
- `ActionProposal -> Service`
- `Decision -> ActionProposal`

### Suggested first Actions

- `AcknowledgeIncident`
- `AssignIncidentOwner`
- `PauseAgent`
- `ResumeAgent`
- `EscalateTierFailure`
- `ApproveProposedMitigation`
- `RejectProposedMitigation`
- `MarkArtifactReviewed`
- `PromotePredictionRule`

### Important submission criteria examples

Use Action submission criteria for guardrails such as:

- cannot close an incident without evidence attached
- cannot promote a rule if evaluation score is below threshold
- cannot pause a critical service without elevated role
- cannot approve a mitigation if a required review field is blank

## How Sapphire Should Feed Foundry

### Best ingestion strategy

Do **not** start by rebuilding Sapphire inside Foundry.

Start by treating Foundry as the operational semantic layer on top of Sapphire’s existing truth sources.

Recommended order:

1. **BigQuery / GCS / existing structured artifacts first**
2. **Key JSONL / NDJSON outputs next**
3. **Selected service APIs after that**
4. **Only then build bidirectional actions**

Why:

- Sapphire already writes structured telemetry and artifacts
- Foundry Data Connection is intentionally light on transformation before the pipeline
- Foundry works best when raw ingress stays simple and shaping happens in Foundry pipelines / ontology

### Best sources to ingest first from Sapphire

Low-friction, high-value candidates:

- `data/metrics/*.ndjson`
- `data/health/*.ndjson`
- `data/intelligence/**/*.json`
- `data/decisions/*.jsonl`
- `data/chain/*.json`
- `data/content/**/*`
- control-plane task / board artifacts
- paper trading state and history
- prediction outputs and scoring outputs

### What not to ingest first

- every raw log stream
- every repo file
- every intermediate artifact
- every high-cardinality transient event

That would make the ontology noisy and the demo muddy.

## Best Showcase Builds

### Showcase 1: Reliability and AI Operations Board

Workshop app with:

- live system posture
- tier health
- failed routines
- recent incidents
- recent prediction misses
- action proposal queue
- embedded AIP Agent widget

Why this showcases Foundry:

- ontology-backed views
- workflow actions
- AI assistant in context
- security-aware dashboards
- operational app, not just BI

### Showcase 2: Prediction Trust Explorer

Focused app for:

- forecast history
- model vs outcome
- per-symbol performance
- confidence drift
- failure analysis
- recommended model/rule changes

Use AIP Logic to summarize prediction misses and propose adjustments.  
Use Evals and Observability to show why changes should be trusted.

### Showcase 3: Incident Copilot

Agent + Workflow setup:

- read service / agent / alert objects
- explain likely root cause
- generate proposed mitigations
- create or update incidents
- request approval before sensitive actions

This is one of the clearest demos of "Foundry is not just storage; it connects AI to operations."

### Showcase 4: Read-only external board

Use Workshop’s read-only pattern to create a broader-consumption dashboard for:

- investors
- advisors
- internal stakeholders
- clients

This lets you demonstrate governance and controlled distribution, not just analytics.

## Best Technical Strategy

### Use Foundry where it is strongest

Use Foundry for:

- semantic operational modeling
- governed workflows
- action permissions
- AI-assisted operator UX
- external/internal app distribution
- observability and evals for AI workflows

### Keep Sapphire where it is strongest

Keep Sapphire as the primary home for:

- core trading / analytics code
- experimental model logic
- custom service runtime
- internal low-level agent orchestration
- local-first and infra-heavy execution paths

### Inference

Do not rush to move Sapphire inference into Foundry just because Foundry can host AI workflows.

Better pattern:

- Sapphire remains the execution and intelligence engine
- Foundry becomes the semantic / operational / workflow / approval layer
- AIP Logic and Agent Studio call into curated functions, datasets, and actions

This keeps the architecture honest and easier to explain.

## Recommended 90-Day Plan

### Phase 1: Establish the semantic layer

Goal: show meaningful value fast.

- Set up Data Connections for the highest-value Sapphire outputs
- Create first Ontology objects:
  - Service
  - Incident
  - Prediction
  - PaperTrade
  - Agent
  - RoutineRun
- Configure standard and a few curated object views
- Build a first read-only Workshop board

Success looks like:

- one clean ontology
- one visible operational app
- one useful drill-down path per object

### Phase 2: Add governed actions

- Add actions for incident and service operations
- Add submission criteria and permissions
- Add application variables and Workshop interactions
- Show proposal-first flows before auto-execution

Success looks like:

- operators can use Foundry to review and take action
- every write path is governed and auditable

### Phase 3: Add AI copilots

- Build Sapphire Operator Agent in Agent Studio
- Build 2-3 AIP Logic functions
- Add Evals and Observability
- Deploy through Workshop and optionally Developer Console

Success looks like:

- agent assists operators with real context
- agent can propose changes but does not free-run blindly
- traces, metrics, and evals are visible

## Best "Wow" Demos

If you want to impress technical and business audiences, demo this sequence:

1. Open a Workshop "Mission Control" app
2. Show a degraded service or stale artifact surfacing as an object
3. Drill into the object view and linked incident / prediction history
4. Ask the AIP Agent why this happened
5. Have the agent call a function and query related objects
6. Show a proposed mitigation action
7. Approve it with submission criteria and auditability visible
8. Show metrics / traces / evaluation history for the underlying AI workflow

That sequence demonstrates:

- ontology
- operational apps
- AI in workflow
- action governance
- observability
- trust

## Specific Foundry Features Sapphire Should Lean Into

### Strong bets

- Ontology Manager
- Actions + submission criteria
- Workshop
- Object Views
- AIP Agent Studio
- AIP Logic
- AIP Evals
- AIP Observability
- Developer Console
- OSDK

### Useful but secondary

- Pipeline Builder `Use LLM` node for bulk enrichment
- read-only Workshop distribution patterns
- custom widgets using OSDK
- marketplace packaging later, once the product surface stabilizes

### Caution / lower priority

- broad ingestion of everything
- premature full agent autonomy
- moving too much custom runtime into Foundry
- building many agents before one good one works

## Best First Practical Build

If only one thing gets built first, it should be:

### Sapphire Reliability Mission Control

Backed by:

- Ontology objects for services, incidents, agents, predictions
- Workshop app
- 3-5 actions
- one Agent Studio copilot
- one or two AIP Logic functions

This is the smallest build that still shows why Foundry is different.

## Research Notes and Source Highlights

The following official docs were the most relevant:

- Platform overview:
  - https://palantirfoundation.org/docs/foundry/platform-overview/overview
- Ontology Manager:
  - https://palantirfoundation.org/docs/foundry/ontology-manager/overview
- Action submission criteria:
  - https://palantirfoundation.org/docs/foundry/action-types/submission-criteria
- Data Connection:
  - https://palantirfoundation.org/docs/foundry/data-connection/overview
- Workshop overview:
  - https://www.palantir.com/docs/foundry/workshop/overview
- Workshop AIP Agent widget:
  - https://www.palantir.com/docs/foundry/workshop/widgets-aip-agent
- Object Views:
  - https://www.palantir.com/docs/foundry/object-views/overview/
- AIP Logic:
  - https://www.palantir.com/docs/foundry/logic/overview
- AIP Agent Studio:
  - https://www.palantir.com/docs/foundry/agent-studio
- Agent tools:
  - https://www.palantir.com/docs/foundry/agent-studio/tools
- AIP Agents via APIs:
  - https://www.palantir.com/docs/foundry/agent-studio/foundry-apis
- Developer Console:
  - https://palantirfoundation.org/docs/foundry/developer-console/overview
- OSDK in custom widgets:
  - https://palantirfoundation.org/docs/foundry/custom-widgets/use-osdk
- AIP Evals:
  - https://www.palantir.com/docs/foundry/aip-evals/overview
- AIP Observability:
  - https://www.palantir.com/docs/foundry/aip-observability/overview
- Automate on stream-backed objects:
  - https://palantirfoundation.org/docs/foundry/automate/streaming

## Bottom Line

The smartest Foundry move for Sapphire is:

- **not** "port Sapphire into Foundry"
- **not** "just build another dashboard"
- **not** "throw an LLM on the data"

It is:

> Build a governed operational twin of Sapphire in Foundry, then use Workshop, Actions, Agent Studio, Logic, Evals, and OSDK to turn that twin into a live human+AI control surface.
