# Sapphire ASFAO Architecture
**Artificial Superintelligent Fully Autonomous Organization — design v0.1**
Date: 2026-05-03
Author: Sapphire Brain (synthesis)
Audience: Ari, future operator agents

---

## 0. Thesis

Sapphire is currently an N=1 operator (Ari) plus a swarm of cloud agents shipping ~30 PRs/day across THO, trading, threat-intel, and wildfire-watch. The next step is not "more agents." It is **role specialization with bounded autonomy + immutable audit + a self-improvement loop**. We adopt the Western corporation as the org primitive (CEO/CFO/CTO/Ops/etc.) because that's the abstraction every downstream tool — accounting, legal, hiring — already expects.

Goal: an org that runs while Ari sleeps, makes auditable decisions inside hard guardrails, escalates the right things, and writes a weekly diff of itself.

---

## 1. Multi-agent library decision

**Recommendation: build a custom thin orchestrator on top of the Claude Agent SDK + Letta for memory + A2A for cross-org talk. Don't adopt CrewAI or LangGraph as the spine.**

Why custom-thin instead of a fat framework:

| Framework | Verdict for Sapphire | Reason |
|---|---|---|
| **Claude Agent SDK (subagents)** | **Adopt as foundation** | Already in use. Sub-agents give context isolation + parallel exec + tool restriction. Maps 1:1 to "role." ([source](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)) |
| Microsoft Agent Framework 1.0 | Watch, don't adopt | GA April 2026. Magentic-One orchestrator pattern is the right shape but .NET-first and Azure-coupled. Steal the *pattern*, not the runtime. ([source](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)) |
| AutoGen | **Skip** | Microsoft moved it to maintenance mode in favor of MAF. Group-chat pattern is good idea, dead vehicle. ([source](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/)) |
| CrewAI | Steal one idea | Role-task-process model is correct; but the framework is opinionated and our roles already exist as plugin tools. ([source](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen)) |
| LangGraph | Skip for spine, **adopt for individual workflows** | Best-in-class for stateful graph workflows w/ LangSmith tracing. Use it inside specific roles (e.g., the THO document-generation pipeline) but not as the org-level orchestrator. ([source](https://pratikpathak.com/langgraph-vs-crewai-vs-autogen-2026/)) |
| MetaGPT / ChatDev | Steal the *SOP-as-prompt* idea | Standard Operating Procedures encoded as prompt sequences = auditability win. ([source](https://github.com/FoundationAgents/MetaGPT)) |
| OpenHands (formerly OpenDevin) | Adopt for autonomous PR work | 53%+ on SWE-bench Verified with Claude 4.5. Already-spawned agents fit our PR pipeline. Use *alongside* Claude Code, not as replacement. ([source](https://localaimaster.com/blog/openhands-vs-swe-agent)) |
| **Letta (MemGPT)** | **Adopt for cross-session memory** | LLM-as-OS paradigm with archival/recall memory. Sapphire Brain + Sapphire-brain repo are *already* a Letta-shaped pattern; formalize it. ([source](https://github.com/letta-ai/letta)) |
| **A2A (Linux Foundation)** | **Adopt at the boundary** | 150+ orgs, v1.0 stable. Use it for `Sapphire <-> THO`, `Sapphire <-> wildfire-watch`, `Sapphire <-> external customer agents`. ([source](https://a2a-protocol.org/latest/)) |
| Sakana AI Scientist | Read the papers, don't run the code | 42% experiment failure rate. The pattern (hypothesis → exp → review) is right; the implementation is research-tier. ([source](https://sakana.ai/ai-scientist/)) |
| CAMEL | Skip | Useful for emergent-behavior research, not for shipping ARR. ([source](https://github.com/camel-ai/camel)) |

**The Sapphire spine:**
```
              ┌──────────────────────────────────────┐
              │  CEO Agent (Ari proxy)               │
              │  - escalation queue                  │
              │  - weekly OKR diff                   │
              └──────────────┬───────────────────────┘
                             │  Magentic-style dispatch
                             │
   ┌──────────┬──────────┬───┴──────┬──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼          ▼          ▼          ▼
 CTO       CFO        Ops      ThreatI    WildfireOps  THOcust    Strategy
 (code)   (P&L)     (deploy)  (CVE)      (drones)    (CRM)      (synth)
   │          │          │          │          │          │          │
   └──────────┴──────────┴───┬──────┴──────────┴──────────┴──────────┘
                             ▼
                  ┌──────────────────────┐
                  │  Letta memory bus    │
                  │  + BigQuery audit    │
                  │  + Redis short-term  │
                  └──────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  A2A boundary plane  │
                  │  (talk to outside)   │
                  └──────────────────────┘
```

Total orchestrator code budget: **<2 kLOC** of Python wrapping Claude Agent SDK + a Letta client + a BigQuery writer + a routing table. Resist the urge to grow it.

---

## 2. The 7 roles

Opinionated. Don't add an 8th without retiring one.

### 2.1 CEO Agent (Ari proxy)
- **What it does:** holds the OKRs, owns the escalation queue, signs off on irreversible actions.
- **Autonomous:** approve PRs labeled `safe-merge` after CTO + 1 reviewer; trigger weekly digest; close stale issues.
- **Escalates:** anything touching live capital >$50, anything touching Cloud Run prod traffic shifts >25%, anything firing customer notifications, any new contractor/vendor.
- **Guardrails:** read-only access to secrets; can request a rotation but not perform; cannot disable other agents.
- **Audit row:** `ceo_decision { okr_id, action, reviewer_chain[], escalated_to_ari: bool, ari_response_ts }`

### 2.2 CTO Agent (architecture, refactor, code review)
- **What it does:** PR review, architecture proposals, refactor planning, dependency upgrades.
- **Autonomous:** merge dependabot PRs that pass CI; reject PRs that break test inventory; spawn refactor sub-agents for files >500 LOC.
- **Escalates:** schema migrations, public API breaks, anything renaming a plugin tool (the manifest is load-bearing — research shows tool-selection accuracy drops 74% → 49% as manifest grows; we already paid for this lesson with the shim layer).
- **Guardrails:** cannot bypass CI; cannot self-merge its own PRs; cannot edit `infra/tool-registry.yaml` without a CFO co-sign (because that's the contract surface).
- **Audit row:** `cto_review { pr_url, verdict, files_touched, tests_added, lloc_delta, model_used, cost_usd }`
- **Reference:** Anthropic's pm-spec → architect-review → implementer-tester pipeline pattern.

### 2.3 CFO Agent (P&L, risk caps, budget)
- **What it does:** trading P&L watch, agent-cost watch (Claude/Anthropic/Ollama tokens), monthly budget reconciliation, kill-switch on Hyperliquid + Robinhood.
- **Autonomous:** trip the killswitch file `~/.sapphire/hyperliquid_trading_pause` if 24h drawdown >2% of capital; pause routines if Anthropic spend > daily cap; cap daily-loss enforcement.
- **Escalates:** ALL position sizing >$5/order on Robinhood (current cap), any new venue, any leverage increase, signing-key activation on Hyperliquid mainnet (currently fail-closed by code).
- **Guardrails:** cannot move money. Cannot raise its own caps without Ari + 14 days of green soak. Read-only on broker APIs; the only write op is *pause*.
- **Audit row:** `cfo_action { type: "pause"|"alert"|"report", venue, amount_usd, reason, sortino_14d, calmar_30d }`
- **CFO is the most paranoid role. Bias every ambiguity toward refusal.**

### 2.4 Ops Agent (deploys, incidents, LaunchAgent)
- **What it does:** Cloud Run revisions, LaunchAgent restarts, incident triage, log rotation health, Tailscale node health.
- **Autonomous:** restart LaunchAgent on crash (current behavior), roll Cloud Run forward on green canary, rotate logs, prune `~/.sapphire/routine_pause/` flags older than 7d.
- **Escalates:** rolling backward (which is more dangerous than forward in most cases — picks up unstaged migrations); any incident touching prod billing or customer data; orphan-service deletion (cf. tho-agent finding 2026-04-30).
- **Guardrails:** cannot delete services; cannot rotate secrets (CTO signs, CEO co-signs); cannot disable monitoring.
- **Audit row:** `ops_action { service, env, action, success, p95_after_ms, blast_radius }`

### 2.5 Threat Intel Agent (CVE, alerts, regional)
- **What it does:** CISA KEV ingestion, NVD diff, MITRE ATT&CK mapping, regional-intel-workbench feeds, Telegram alert routing.
- **Autonomous:** triage CVEs by CVSS + exposure (does Sapphire run that package?), suppress duplicate alerts, post to Telegram, write a daily threat brief.
- **Escalates:** active exploitation in our stack, supply-chain compromise of an installed dependency, any CVE >9.0 that touches a Sapphire-exposed surface.
- **Guardrails:** cannot patch — only proposes a PR. Patching goes through CTO. Cannot block traffic without CEO approval.
- **Audit row:** `threat_decision { cve_id, cvss, kev_listed, sapphire_exposed, action: "patch_proposed"|"alert"|"suppress", routed_to[] }`

### 2.6 Wildfire Ops Agent (sensor health, drone dispatch — Phase 0)
- **What it does:** Mavic Mini + Pi sensors health, fire-detection model triage, false-positive filtering, fire-dept handoff packet.
- **Autonomous:** suppress known-noise sensors, batch low-confidence detections into a daily review, generate the operator handoff PDF.
- **Escalates:** any high-confidence detection (>0.85 fire prob), drone battery <20%, sensor offline >1h, any first-time fire-dept-API call.
- **Guardrails:** **never** auto-launches a drone. Drone ops are pilot-in-loop in Phase 0 by hard rule. Cannot communicate with fire dept without Ari approval per incident.
- **Audit row:** `wildfire_decision { sensor_id, lat, lon, confidence, action, pilot_in_loop_user, handoff_pdf_uri }`

### 2.7 THO Customer Agent (lead nurture, document generation)
- **What it does:** lead-nurture cadence, deal pipeline updates, XFA document filling, customer-search indexing.
- **Autonomous:** advance LEAD → ENROLLED on document-receipt + email-verify; generate documents when all required fields are filled (per `getValidationState`); send the "your packet is ready" email after Ari approval.
- **Escalates:** any state that closes a deal (CLOSED), any refund flow, any customer who opens a chargeback, any contract amendment, any document touching SSN/banking (read-only — *we type none of these*; we only confirm the customer typed them).
- **Guardrails:** cannot send email without Ari OR an explicit per-customer approval token. Cannot bypass `getValidationState`. Cannot edit a generated PDF after Ari signs (immutability per audit).
- **Audit row:** `tho_action { customer_id, deal_id, state_from, state_to, documents_generated[], email_sent, ari_token_id }`

### 2.8 Strategy Agent (Sapphire Brain — already partial)
- **What it does:** cross-silo synthesis, PR landing-zone planning, weekly digest, "what should we ship next" recommendation.
- **Autonomous:** write the daily morning digest, rank open PRs by merge-order conflict risk, identify orphan services (cf. tho-agent), draft the weekly OKR check-in.
- **Escalates:** any recommendation that would change role caps or guardrails (i.e., it can propose, never enact, an autonomy expansion).
- **Guardrails:** read-only across all systems. The most-privileged *reader*, the least-privileged *writer*. Writes only to `Sapphire-brain/docs/`.
- **Audit row:** `strategy_brief { brief_id, scope, sources[], recommendations[], adopted_by_role, adoption_ts }`

---

## 3. Decision flow & escalation

```
Action proposed by role X
    │
    ▼
Check role X autonomy bounds
    │
    ├── inside ──► Execute, write audit row to BigQuery, done
    │
    └── outside ──► Route to Ari via Telegram (hermes)
                    │
                    ├── approved within 10 min ──► Execute, audit
                    ├── approved >10 min ──── ► Re-confirm context, then execute
                    └── timeout 24h ────────► Auto-escalate to Strategy Agent
                                              for "should this rule change?"
```

Two non-negotiables:

1. **Every audit row goes to BigQuery `sapphire_audit.decisions_v1`** (and a local SQLite mirror). Schema is one row per decision with `agent_role, action_id, autonomy_bound: "inside"|"outside", outcome, blast_radius, cost_usd, tokens_in, tokens_out, ts`. Immutable, append-only, with weekly partitions. Per the EU AI Act posture (obligations begin Aug 2026), this is the lawful-basis record. ([source](https://www.covasant.com/blogs/the-ai-governance-mandate-scaling-agentic-ai-on-google-cloud-in-2026))
2. **The CEO agent reviews the audit table weekly** and proposes 1-3 autonomy expansions or contractions. Never enacts; just proposes for Ari.

---

## 4. Self-improvement loop ("dev pulse" generalized)

LangChain's framing is correct: a **trace-centered improvement loop** is the only kind that works. ([source](https://www.langchain.com/conceptual-guides/traces-start-agent-improvement-loop))

What we already have:
- Existing `dev_pulse` tool reads logs and proposes improvements (cf. tools/dev_pulse.py).
- BigQuery audit table (proposed §3).
- Sapphire Brain (= partial Strategy Agent).

What we need to add:

### 4.1 The weekly reflection routine

Every Sunday 23:00 CT, the Strategy Agent runs:
1. Pull last 7d of `decisions_v1` from BigQuery.
2. Group by `(role, outcome=fail)` and find the top 5 failure clusters.
3. For each: pull the matching traces (Anthropic API request IDs), draft a Reflexion-style verbal post-mortem ("the CFO agent paused trading 3x this week from a flapping Sortino calc; the calc was numerically unstable below $25 NAV"). ([source](https://ar5iv.labs.arxiv.org/html/2303.11366))
4. Propose 1 of: prompt patch, code patch, new test, new guardrail, role-cap change.
5. Open a PR labeled `reflection-fix` against the relevant repo.

Critical caveat from the research: **don't have the same agent grade itself**. Use a *different* model for the post-mortem (e.g., GPT-5 or Opus-different-prompt) to get asymmetric criticism. ([source](https://dev.to/turacthethinker/your-agent-isnt-reflecting-its-performing-reflection-b41))

### 4.2 Skill discovery via Letta

Sapphire's plugin-tool registry is the skill set. Letta-style: when an agent solves a problem 3+ times the same way, the Strategy Agent proposes promoting the pattern to a plugin tool (i.e., a skill). The Letta `agent.skills` slot is mirrored in `infra/tool-registry.yaml`. ([source](https://www.letta.com/blog/letta-code))

### 4.3 Self-Refine for content (NOT for code)

For artifacts where the failure mode is "incomplete or sloppy" rather than "wrong" — daily digests, customer emails, threat briefs — apply Self-Refine: feedback → refine → feedback. ([source](https://selfrefine.info/)) Code goes through tests; content goes through Self-Refine + a human spot-check.

### 4.4 Continuous benchmarking

Stand up an internal "OpenHands Index"-style scoreboard: for each role, weekly resolve-rate on a fixed eval set (24 closed PRs replayed, 50 historical trades scored vs actual, 100 historical CVEs vs our triage). Regression of >10% blocks the next autonomy expansion. ([source](https://openhands.dev/blog/openhands-index))

---

## 5. Cost & state management

| Concern | Choice | Reason |
|---|---|---|
| Short-term state (within a single agent turn) | Redis | Already running |
| Long-term memory (across sessions, across roles) | Letta archival/recall on top of Postgres | Cheaper than re-stuffing prompts |
| Audit log | BigQuery `sapphire_audit.decisions_v1` (partitioned weekly) + SQLite local mirror | Forensic + queryable |
| Cross-org talk | A2A | Future-proofs against THO/wildfire-watch becoming separate identities |
| Tool calls inside an agent | MCP | Already standardized |
| Agent-to-agent inside Sapphire | Magentic-style dispatch via custom thin orchestrator | < 2 kLOC of Python; no fat framework |

Daily token budget guardrails (CFO-enforced):
- CEO: 50k tokens (mostly reads)
- CTO: 1M tokens (PR review heavy)
- CFO: 100k tokens
- Ops: 100k tokens
- ThreatI: 200k tokens (large-context reads)
- WildfireOps: 50k (Phase 0)
- THOcust: 300k (customer-facing)
- Strategy: 500k (synthesis-heavy)

Total daily cap: ~2.3M tokens (well under current observed ~30 PRs/day spend).

---

## 6. Migration plan (4 phases)

**Phase 1 (week 1-2): Audit foundation.** Stand up `sapphire_audit.decisions_v1`. Wire the existing 49 plugin tools to write a row on every invocation. No new agents. (Resist scope creep.)

**Phase 2 (week 3-6): Promote 3 existing patterns to roles.** Strategy (Sapphire Brain — already exists), Ops (already partially in `service_supervisor`), CFO (kill-switch logic exists, formalize the role wrapper).

**Phase 3 (week 7-12): The remaining 4 roles.** CEO, CTO, ThreatI, THOcust as proper roles. Each role gets its own LaunchAgent + Letta agent_id + BigQuery audit emitter.

**Phase 4 (q3 2026): Self-improvement loop turns on.** Weekly reflection runs. Continuous bench. Autonomy expansions begin to be proposed by data, not by Ari hunch.

WildfireOps stays manual through phase 4. We do not automate Phase 0 wildfire.

---

## 7. What we explicitly are NOT doing

- **Not building a fat framework.** Custom thin orchestrator wins.
- **Not letting roles spawn other roles.** The org chart is finite. Roles spawn sub-agents (Claude Agent SDK), not peers.
- **Not auto-trading on stocks.** Crypto-only with $5 rung, per the 2026-04-28 Robinhood live-capital posture.
- **Not auto-launching drones.** Pilot-in-loop, period.
- **Not deleting anything irreversible.** Soft-delete + 30d retention everywhere.
- **Not training our own foundation model.** Distillation later, maybe; foundation, no.
- **Not adopting a DAO governance layer.** We are not a token-holder organization. ([context](https://www.pseudorandombits.io/p/agentic-daos-ai-meets-decentralized-governance))

---

## 8. Open questions for Ari

1. Do you want a "board" — i.e., a once-a-month 3-hour deep-review session where every role shows its quarter-over-quarter metrics?
2. Where do customer-agent decisions live legally? THO is your mom's LLC. Do CRM auto-emails count as the LLC speaking?
3. The OpenHands $18.8M Series A and the AMD/Apple/Google adoption ([source](https://localaimaster.com/blog/openhands-vs-swe-agent)) suggests we should explore using their runtime for the CTO role's heavy refactor work. Yes/no/later?
4. Do you want Letta-the-company in the loop (their managed service) or self-host on Postgres? Self-host is the default; Letta managed unlocks a UI we don't have to build.

---

## Sources cited
- [Anthropic — Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Anthropic — Subagents in the SDK](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Microsoft Agent Framework 1.0 GA](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- [Magentic orchestration pattern](https://learn.microsoft.com/en-us/agent-framework/user-guide/workflows/orchestrations/magentic)
- [AutoGen migration guide (now maintenance mode)](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/)
- [CrewAI vs LangGraph vs AutoGen — DataCamp](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen)
- [LangGraph vs CrewAI vs AutoGen 2026 — Pratik Pathak](https://pratikpathak.com/langgraph-vs-crewai-vs-autogen-2026/)
- [MetaGPT GitHub](https://github.com/FoundationAgents/MetaGPT)
- [Sakana AI Scientist](https://sakana.ai/ai-scientist/)
- [Sakana evaluation paper](https://arxiv.org/abs/2502.14297)
- [Letta GitHub (formerly MemGPT)](https://github.com/letta-ai/letta)
- [Letta Code blog](https://www.letta.com/blog/letta-code)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [Linux Foundation A2A announcement](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)
- [OpenHands SWE-Bench leaderboard 2026](https://localaimaster.com/blog/openhands-vs-swe-agent)
- [OpenHands Index](https://openhands.dev/blog/openhands-index)
- [Reflexion paper (arxiv 2303.11366)](https://ar5iv.labs.arxiv.org/html/2303.11366)
- [Self-Refine](https://selfrefine.info/)
- [LangChain — trace-centered improvement loop](https://www.langchain.com/conceptual-guides/traces-start-agent-improvement-loop)
- [Asymmetric criticism critique](https://dev.to/turacthethinker/your-agent-isnt-reflecting-its-performing-reflection-b41)
- [CAMEL multi-agent](https://github.com/camel-ai/camel)
- [Covasant — AI governance on Google Cloud, EU AI Act 2026](https://www.covasant.com/blogs/the-ai-governance-mandate-scaling-agentic-ai-on-google-cloud-in-2026)
- [Agentic DAOs](https://www.pseudorandombits.io/p/agentic-daos-ai-meets-decentralized-governance)
