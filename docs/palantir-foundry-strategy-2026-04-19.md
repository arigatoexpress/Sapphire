# Palantir Foundry Strategy For Sapphire

Date: 2026-04-19  
Scope: research-backed plan for using Palantir Foundry to enrich Sapphire and showcase what Foundry does well, without distorting Sapphire's existing strengths.

## Executive take

Foundry is a strong fit for Sapphire if we use it as an **operational intelligence layer** on top of the platform we already have, not as a replacement for Sapphire's real-time runtime.

The best use of Foundry here is:

1. Bring Sapphire's existing data exhaust and workflows into a governed operational model.
2. Turn that model into an Ontology with Actions, Functions, Workshop apps, and AIP Agents.
3. Use Foundry to showcase cross-domain visibility, workflow orchestration, retrieval, and operator UX.

The wrong use is:

- trying to move the latency-sensitive trading execution path into Foundry first,
- rebuilding existing Flask/control-plane/dashboard logic before the Ontology exists,
- treating Foundry as "just another dashboard" instead of an operational graph with governed writeback.

## Why this fits Sapphire specifically

Sapphire already has the ingredients Foundry can amplify:

- a multi-source event/data system,
- a growing operational dashboard surface,
- strong domain objects hiding in code and JSONL artifacts,
- agentic workflows that already need governance, state, approvals, and cross-tool context.

Repo grounding:

- Sapphire already presents itself as an operations platform with event bus, control plane, dashboard, data lake, and plugin tools in [README.md](/Users/aribs/Code/Sapphire/README.md:1).
- The Intel dashboard already has an explicit placeholder for "Palantir Foundry Integration" in [services/dashboard/templates/pages/intel.html](/Users/aribs/Code/Sapphire/services/dashboard/templates/pages/intel.html:341).
- The Intel API also already marks Foundry as a pending source in [services/dashboard/app.py](/Users/aribs/Code/Sapphire/services/dashboard/app.py:2130).

That means the highest-value Foundry work is not speculative; it is a natural extension of the system Sapphire already wants to be.

## What Foundry is best at for us

Based on Palantir's current official docs, the strongest Foundry capabilities for Sapphire are:

### 1. Ontology-backed application development

Palantir's SDK docs make a clean distinction:

- Use the **platform SDKs** when you are automating administrative or governance tasks or need portable Foundry API access across enrollments.
- Use the **Ontology SDK (OSDK)** when you are building an app that reads and writes data from a single Ontology.

For Sapphire, that suggests:

- use **Platform SDK / REST APIs** for generic integration and automation,
- use **OSDK** for the actual Sapphire operational app layer once the Ontology exists.

This is the most important architecture decision because it stops us from building a generic integration when what we really want is an ontology-native application surface.

## 2. Functions + Actions for governed writeback

Foundry Functions are explicitly designed for operational contexts, and Palantir documents them as suitable for:

- returning object sets and variables for Workshop,
- computing metrics,
- querying external systems to enrich ontology objects,
- acting as sidecars in Pipeline Builder.

Function-backed Actions are the real leverage point for Sapphire. They let us move from "dashboard insight" to "approved operational mutation" with auditability.

That is a better fit than wiring raw Foundry reads alone, because Sapphire already has operator-like decisions that should become governed actions:

- acknowledge / suppress / escalate a threat,
- approve / reject a trade candidate,
- create an incident,
- attach an investigation,
- open a maintenance task for a degraded service,
- mark an alert resolved and propagate status to linked objects.

## 3. Workshop for operator-facing mission control

Workshop is a strong match for Sapphire's UI needs because it is explicitly built around:

- object data as the primary building block,
- Actions for writeback,
- Functions for business logic,
- operational patterns like inboxes and common operational pictures.

For Sapphire, this is a natural way to build:

- a trading/risk command center,
- a cyber and regional intel triage inbox,
- a cross-domain mission dashboard that joins infra, markets, threats, and agent outputs.

If we want to *show* what Foundry can do, Workshop is the most legible place to do it.

## 4. AIP Agent Studio for governed operator copilots

AIP Agent Studio is relevant because Palantir's current docs describe agents as using:

- LLMs,
- the Ontology,
- documents,
- custom tools,

and as deployable internally in Foundry and externally through OSDK and platform APIs.

For Sapphire, that means we should not think "chatbot". We should think:

- **Sapphire Operator Agent** for cross-domain situational questions,
- **SOC Analyst Agent** for CVE / threat triage,
- **Trade Review Agent** for explaining signal + risk + macro context before writeback,
- **Infra Triage Agent** for degraded-service investigation and next-step recommendation.

Palantir's AIP Agent APIs also support:

- creating sessions,
- blocking or streaming responses,
- retrieving session history,
- retrieving session traces for debugging.

That is useful if we eventually want Sapphire's existing dashboard or control plane to embed Foundry-hosted agents rather than replace its UX wholesale.

## 5. Document Intelligence + media sets + semantic search

This is one of the best showcase tracks because Sapphire already works with research, threat reports, and other semi-structured content.

Palantir's current docs show:

- **AIP Document Intelligence** can evaluate extraction quality/speed/token cost and deploy the selected extraction strategy directly into a Python transform repository.
- **Media sets** are designed for documents, audio, imagery, video, and other unstructured data.
- **Semantic search** becomes operationally useful when embedded text is associated with Ontology objects.

That maps extremely well to Sapphire:

- CVE advisories,
- threat writeups,
- regulatory or macro reports,
- research PDFs,
- earnings decks or public filings,
- long-form operator notes.

This would let us build a real ontology-backed retrieval layer instead of a pile of markdown files and JSON blobs.

## 6. Pipeline Builder + external transforms for integration and lineage

Pipeline Builder is Foundry's primary data integration surface, and Palantir documents external transforms as the preferred code-based path for:

- REST APIs,
- private-network systems,
- custom batch/export/media sync flows,
- shared connection configuration with governance and lineage.

For Sapphire, this matters because the platform already has many external producers and consumers:

- dashboard APIs,
- control-plane APIs,
- OpenBB,
- regional intel,
- cyber-threat-bot outputs,
- JSONL/event stores,
- GCS/BigQuery syncs.

This is where Foundry can give us stronger lineage and connection governance than Sapphire currently has on its own.

## 7. FoundryTS for time-series analytics

FoundryTS is a good fit for Sapphire's market and telemetry data because Palantir documents it as a Python library for querying time series and linking them back to ontology properties. It integrates with Code Repositories and Code Workbook and can emit datasets that then back time series through the catalog or Pipeline Builder.

This is relevant for:

- BTC/ETH/SOL price series,
- signal quality over time,
- model endpoint health,
- latency and fill-rate metrics,
- strategy performance curves,
- threat volume over time.

## Best Sapphire use cases, prioritized

### Priority 1: Build a Sapphire Ontology and Workshop "Mission Control"

This is the highest-value first move.

Why:

- It showcases Foundry's core differentiation, not just its APIs.
- It gives Sapphire a governed operational graph across multiple domains.
- It aligns with the existing dashboard/intel/control-plane architecture.

Recommended object model:

- `Asset`
- `MarketSeries`
- `Signal`
- `PredictionRun`
- `PaperTrade`
- `Threat`
- `ThreatObservation`
- `IntelItem`
- `Service`
- `ModelEndpoint`
- `Incident`
- `Task`
- `Region`
- `AgentRun`

Recommended links:

- `Signal -> Asset`
- `PredictionRun -> Asset`
- `PaperTrade -> Signal`
- `ThreatObservation -> Threat`
- `ThreatObservation -> Region`
- `Incident -> Service`
- `Incident -> ThreatObservation`
- `Task -> Incident`
- `AgentRun -> Task`

Recommended Workshop modules:

- **Executive COP**: market state + infra state + threat state + latest incidents.
- **SOC Inbox**: triage queue of critical threats and suspicious intel clusters.
- **Trade Review Board**: candidate signals, risk context, macro context, approval action.
- **Infra Command**: service degradation, recent failures, owning tasks, escalation actions.

### Priority 2: Use Foundry as the semantic/retrieval plane for Sapphire intelligence

If you want a "wow, this is more than dashboards" demo, this is the other best path.

Why:

- Sapphire already produces and consumes long-form unstructured intelligence.
- Foundry's media sets + Document Intelligence + semantic search + Ontology association create a real enterprise retrieval workflow.
- This is much stronger than bolting another vector DB into Sapphire ad hoc.

Recommended corpus:

- `data/threat_intel/*.md`
- research docs and strategy memos
- CVE/NVD/CISA PDFs or saved reports
- market/macro reports
- incident postmortems

Recommended output:

- extracted document objects,
- chunk objects,
- embeddings associated to `Threat`, `IntelItem`, `Asset`, or `Incident`,
- semantic search and object-explorer workflows over those relationships.

Best demo:

- Ask an AIP agent about "APAC cyber activity affecting exchange infrastructure"
- Show retrieved linked objects, supporting documents, current incidents, and suggested actions
- Allow operator follow-up from within Workshop

### Priority 3: Use Actions + Functions to turn Sapphire into an auditable operating system

This is how we go from "data platform demo" to "operational platform demo."

Best first actions:

- `EscalateThreat`
- `SuppressThreat`
- `CreateIncidentFromThreat`
- `ApproveTradeCandidate`
- `RejectTradeCandidate`
- `PauseService`
- `AssignInvestigation`
- `ResolveIncident`

Each should be function-backed where multi-object edits or business rules matter.

This is the clearest way to showcase Foundry's governance and operational semantics.

### Priority 4: Add AIP Agents only after the Ontology and Actions exist

This ordering matters.

If you create agents before the Ontology and actions are modeled, the result will be impressive but shallow.

If you create them after:

- the agent has meaningful tools,
- retrieval is grounded,
- writeback is governed,
- tracing/debugging becomes useful,
- the demo becomes much more credible.

Best first agents:

- **Sapphire Command Agent**
- **Threat Triage Agent**
- **Trade Review Agent**

## Best integration patterns for Sapphire

### Pattern A: Start with file/dataset replication

Best first ingestion path for Sapphire:

- push stable Sapphire outputs into Foundry as datasets,
- model the Ontology over those datasets,
- build apps on top.

Best candidate sources from Sapphire:

- `data/system_events.jsonl`
- `data/trading_predictions.jsonl`
- `data/intelligence/YYYY-MM-DD/predictions.json`
- `data/threat_intel/`
- `data/starred_repos/`
- service health and performance artifacts

Why start here:

- lowest organizational friction,
- easiest governance story,
- fastest way to get value from Foundry apps.

Good transport options:

- Foundry's **S3-compatible API** for dataset IO,
- batch uploads through Foundry ingestion tooling,
- or Foundry-side pulls from governed sources.

### Pattern B: Use external transforms for live or semi-live pull integration

Use Foundry external transforms when you want Foundry to call out to Sapphire or adjacent systems directly.

Best uses:

- polling Sapphire control-plane or dashboard APIs,
- pulling OpenBB or regional-intel outputs,
- reaching private/internal systems under Foundry governance,
- building enriched datasets with clear lineage.

This is better than inventing custom one-off pull code in every Foundry function.

### Pattern C: Use OSDK for app development and Platform SDK for automation

Recommended split:

- **OSDK** for the real Sapphire-on-Foundry app surface,
- **Platform SDK / REST API** for administrative automation, CI/CD-like tasks, and generic embedding.

This follows Palantir's own guidance and keeps the integration shape clear.

## What to build first if the goal is "showcase what Foundry can do"

If the goal is not just utility but demo value, build in this order:

1. **Ontology + Workshop COP**
2. **Threat / intel semantic search over document media sets**
3. **Function-backed Actions for triage and approvals**
4. **AIP Agent embedded in Workshop**
5. **Foundry-backed time-series and performance views**

That sequence tells a compelling story:

- data harmonization,
- operational graph,
- governed workflow,
- AI assistance,
- enterprise-grade operator UX.

## What I would not do first

### 1. Do not move trading execution into Foundry first

Sapphire's trading runtime is latency-sensitive and already deeply tied to existing services. Foundry is better used first for:

- review,
- governance,
- analysis,
- approvals,
- historical intelligence,
- unified operational context.

### 2. Do not start with a generic SDK-only integration

If you only wire REST/API calls, you may prove connectivity without proving Foundry's actual value.

### 3. Do not make the first deliverable "another dashboard"

If it does not use:

- Ontology objects,
- Actions,
- Functions,
- Workshop patterns,
- or AIP agents,

then it will under-show what Foundry is actually good at.

## Concrete Sapphire build plan

### Phase 0: Foundation

- Confirm you are using a **custom application / Developer Console** path for new app work, not legacy standalone OAuth clients.
- Decide the first Foundry project and naming convention for Sapphire resources.
- Define the first ingestion contract from Sapphire into Foundry.

Deliverable:

- one Foundry application,
- one ingestion path,
- one project with clean permissions.

### Phase 1: Mirror Sapphire's operational exhaust

Ingest:

- events,
- threats,
- predictions,
- service health,
- selected trade/performance artifacts.

Deliverable:

- Foundry datasets and basic Ontology objects for those domains.

### Phase 2: Build the ontology

Define:

- objects,
- links,
- derived properties,
- security model,
- prominent object types for search and Object Explorer.

Deliverable:

- usable `Asset`, `Threat`, `Service`, `Incident`, `Signal`, `PredictionRun`, `Task`, `Region` graph.

### Phase 3: Ship the first Workshop app

Target app:

- **Sapphire Mission Control**

Minimum views:

- threat inbox,
- infra state,
- market state,
- incident timeline,
- action panel.

### Phase 4: Add function-backed actions

Implement:

- threat escalation,
- incident creation,
- approval/rejection paths,
- service pause/resume metadata updates.

### Phase 5: Add AIP + document workflows

Use:

- AIP Document Intelligence for threat and research documents,
- semantic search tied to ontology objects,
- one embedded AIP agent in Workshop.

## Best "wow demo" storyline

If you want to demo Foundry to someone and have them immediately understand the point:

1. Show a Workshop "Mission Control" COP.
2. Click into a live threat object linked to region, services, incidents, and supporting docs.
3. Open retrieved chunks from Document Intelligence / semantic search.
4. Ask the embedded AIP agent what matters now.
5. Use a governed Action to escalate/create incident/assign investigation.
6. Show the updated state reflected across linked objects and views.

That demo shows:

- ingestion,
- ontology,
- search,
- retrieval,
- operational UX,
- AI,
- governed writeback.

That is a much better Foundry story than "we connected an API."

## Recommended next Sapphire-specific implementation steps

### Immediate

1. Create a Foundry resource map for these existing Sapphire outputs:
   - `data/system_events.jsonl`
   - `data/threat_intel/`
   - `data/trading_predictions.jsonl`
   - `data/intelligence/*/predictions.json`
   - service health outputs
2. Define the v1 Ontology object model.
3. Decide whether the first app is:
   - **Mission Control**
   - **SOC Triage**
   - **Trade Review**

Recommendation: start with **Mission Control**, because it shows the broadest Foundry value fastest.

### Next after that

4. Replace the placeholder Foundry panel in the Intel dashboard with a real integration status/readiness view.
5. Build the first Foundry-backed action flow.
6. Add document ingestion + semantic retrieval for threat intelligence.

## Repo-grounded first-wave ingestion map

These are the highest-signal Sapphire artifacts to push into Foundry first because they already exist on disk, are structured enough to ingest with minimal shaping, and map cleanly to Ontology objects:

| Sapphire surface | Current shape | Best Foundry ingress | First Ontology anchors | Why it belongs in wave 1 |
| --- | --- | --- | --- | --- |
| `data/system_events.jsonl` | append-only event log | dataset upload or S3-compatible API | `AgentRun`, `Incident`, `Task`, `Service` | Gives us the operational timeline and cross-domain event spine immediately. |
| `data/health/*.ndjson` and `data/metrics/*.ndjson` | service telemetry snapshots | dataset upload | `Service`, `ModelEndpoint`, `Incident` | Ideal for Mission Control and object health drill-downs. |
| `data/trading_predictions.jsonl` and `data/intelligence/*/predictions.json` | structured forecasts | dataset upload | `Asset`, `Signal`, `PredictionRun` | Shows forecast lineage, scoring, and review workflows without moving execution into Foundry. |
| `data/paper_trading.jsonl` and `data/paper_portfolio.json` | simulated execution state | dataset upload | `PaperTrade`, `PortfolioSnapshot`, `Signal` | Lets us showcase approvals, explainability, and post-trade review safely. |
| `data/threat_intel/*.md` and `data/intelligence/*/threats.json` | mixed unstructured + structured threat data | media sets + extracted datasets | `Threat`, `ThreatObservation`, `IntelItem`, `Region` | Best path for Document Intelligence, semantic search, and linked operational intel. |
| `data/decisions/*.jsonl`, `data/trading_research.jsonl`, `data/market_pulse/*.md` | human/agent decision exhaust | dataset upload + media sets | `Decision`, `IntelItem`, `Task` | Makes operator judgment and AI recommendations auditable in the Ontology. |

Phase-2 candidates after the core demo is working:

- `data/content/drafts/` and `data/content/ready/` for content-generation lineage and approvals.
- `data/starred_repos/` for external research and trend-watch workflows.
- `data/chain/*.json` and `data/chain/history.jsonl` for richer market/chain correlation views once Mission Control is stable.

## Required Foundry setup checklist

1. Create a **Developer Console custom application** for Sapphire.
   Palantir's current docs position Developer Console as the application path for new app work, and the standalone OAuth client path is explicitly marked legacy.
2. Grant the app only the first project's permissions.
   Start with one Foundry project, one namespace, and the smallest set of dataset / Ontology permissions needed for the Mission Control slice.
3. Pick one ingestion bridge first.
   For Sapphire, that should be either batch dataset sync through the S3-compatible API or a straightforward Foundry-side ingestion flow.
4. Keep live pull logic behind explicit boundaries.
   Use external transforms only after the first datasets are stable and when Foundry truly needs to pull from Sapphire APIs or adjacent governed systems.
5. Build the Ontology before building agents.
   The first Workshop app, Object Views, and Actions should land before Agent Studio becomes the center of the demo.

## First Workshop and action package

Smallest credible Foundry showcase for Sapphire:

- **Workshop app:** `Sapphire Mission Control`
- **Primary object views:** `Service`, `Threat`, `PredictionRun`, `PaperTrade`, `Incident`
- **First action set:**
  - `CreateIncidentFromThreat`
  - `EscalateThreat`
  - `ApproveTradeCandidate`
  - `RejectTradeCandidate`
  - `PauseService`

Recommended submission criteria:

- An incident cannot be created from a threat without a severity and source reference.
- A trade candidate cannot be approved unless confidence, symbol, and time horizon are present.
- A service cannot be paused unless the acting role has elevated permissions and a rationale is supplied.
- An escalation cannot proceed without an owning region or service link.

## First agent spec

Build one agent first:

- **Name:** `Sapphire Command Agent`
- **Primary role:** answer "what matters right now?" across infra, threat, and forecast state
- **Allowed tools:** ontology queries, semantic search over linked documents, read-only analysis functions, proposal-first actions
- **Not allowed initially:** direct execution-path mutations outside governed Foundry Actions

Minimum prompt contract:

> You are Sapphire Command Agent. Use Ontology state, linked documents, and approved read-only functions to summarize live platform risk, explain the strongest drivers, and recommend the next operator action. When an action is warranted, propose it through the relevant governed Action and explain what evidence supports it.

## System boundary: what stays in Sapphire

Foundry should enrich Sapphire, not absorb it wholesale.

Keep these in Sapphire:

- latency-sensitive trading execution
- existing real-time service control loops
- low-level inference runtimes and routing
- current event production and operational APIs

Move or mirror these into Foundry:

- semantic operational model
- approval workflows and auditable write-back
- operator-facing mission control views
- document retrieval and linked intelligence
- AI traces, evals, and operator copilot workflows

## Sources

Official Palantir sources used for this strategy:

- Ontology SDK overview: <https://www.palantir.com/docs/foundry/ontology-sdk/overview>
- Platform SDK vs OSDK: <https://www.palantir.com/docs/foundry/api/general/overview/sdks>
- API reference landing page: <https://www.palantir.com/docs/foundry/api-reference>
- S3-compatible API for Foundry datasets: <https://www.palantir.com/docs/foundry/data-integration/foundry-s3-api>
- Pipeline Builder overview: <https://www.palantir.com/docs/foundry/pipeline-builder/overview>
- Functions overview: <https://www.palantir.com/docs/foundry/functions/overview>
- Function-backed actions overview: <https://www.palantir.com/docs/foundry/action-types/function-actions-overview>
- Workshop overview: <https://www.palantir.com/docs/foundry/workshop/overview>
- Object Explorer overview: <https://www.palantir.com/docs/foundry/object-explorer/overview>
- AIP overview: <https://www.palantir.com/docs/foundry/aip/overview>
- AIP Agent Studio overview: <https://www.palantir.com/docs/foundry/agent-studio>
- AIP Agents through Foundry APIs: <https://www.palantir.com/docs/foundry/agent-studio/foundry-apis>
- External transforms: <https://www.palantir.com/docs/foundry/data-connection/external-transforms>
- FoundryTS: <https://www.palantir.com/docs/foundry/time-series/foundryts>
- Media sets overview: <https://www.palantir.com/docs/foundry/data-integration/media-sets>
- AIP Document Intelligence overview: <https://www.palantir.com/docs/foundry/document-intelligence/overview>
- Semantic search overview: <https://www.palantir.com/docs/foundry/ontology/overview-semantic-search>
- Developer Console permissions: <https://www.palantir.com/docs/foundry/developer-console/permissions>
- Legacy standalone OAuth clients note: <https://www.palantir.com/docs/foundry/developer-console/oauth-clients>
- April 2025 announcement on Developer Console + Marketplace deployment: <https://www.palantir.com/docs/foundry/announcements/2025-04/>
