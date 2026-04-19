# Agent System

This file is the operating agreement for concurrent work across Codex and Claude.

The goal is simple: parallelize aggressively without duplicate effort, merge pain, or conflicting product decisions.

## Shared Principles

- One product thesis. Many execution lanes.
- Shared facts live in docs, not in chat memory.
- Every task needs a clear owner and a declared write surface.
- Architecture changes need a decision note before implementation fans out.
- Small, mergeable artifacts beat giant rewrites.

## Source Of Truth

- [README.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/README.md): product wedge and scope
- [ARCHITECTURE.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/ARCHITECTURE.md): system design and technical defaults
- [BACKLOG.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/BACKLOG.md): claimable work queue

If a chat conclusion does not land in one of these files, it is not durable yet.

## Lane Split

| Lane | Primary owner | Best use |
| --- | --- | --- |
| Product narrative, user research synthesis, buyer objections, pricing framing | Claude | High-context writing, synthesis, positioning |
| Architecture, schemas, scaffolding, integration contracts, task decomposition, code changes | Codex | Concrete system design and implementation |
| Decisions that affect both product and implementation | Shared | Requires a short written decision before branching |

## Recommended Write Ownership

### Codex owns first

- code scaffolding
- repo structure
- API and schema definitions
- adapter interfaces
- test harnesses
- implementation checklists
- operational runbooks

### Claude owns first

- PRD refinements
- customer interview guide
- sales narrative
- pricing copy
- compliance questionnaire draft
- onboarding and change-management narrative

### Shared files

- `README.md`
- `ARCHITECTURE.md`
- `BACKLOG.md`

Shared files should be edited in short bursts with a narrow purpose. Do not rewrite the whole file to add one decision.

## Claim Protocol

Before starting work:

1. Pick one task in `BACKLOG.md`.
2. Mark the owner and status in place.
3. State the write surface you intend to touch.
4. If the task changes scope, update `BACKLOG.md` before continuing.

Example claim:

```text
Owner: Codex
Status: in_progress
Write surface: packages/canonical-model, docs/invoice-recon-mvp/ARCHITECTURE.md
```

## Handoff Protocol

When finishing a task, leave a compact handoff note:

```text
What changed:
- Added canonical invoice and audit event shapes
- Locked initial status enum and posting states

Open edges:
- Need decision on line-item tax representation
- Need final NetSuite external ID naming

Suggested next task:
- ERP adapter contract skeleton
```

## Conflict Avoidance

- Do not have both agents editing the same code package at once.
- If both need the same shared doc, split by section and timebox the edit.
- Prefer append-only decision notes over silent rewrites.
- If ownership is unclear, Codex takes implementation artifacts and Claude takes narrative artifacts until clarified.

## Decision Rule

Write a short decision entry in `BACKLOG.md` whenever one of these changes:

- target ICP
- MVP scope
- primary cloud
- wave-one ERP list
- pricing model
- any irreversible data-model choice

Format:

```text
Decision:
- Date:
- Owner:
- Change:
- Why:
- Impacted files:
```

## Suggested Immediate Split

### Codex

- define canonical entities and state machines
- draft repo layout and service boundaries
- break the technical MVP into mergeable epics
- scaffold the first technical plan and validation strategy

### Claude

- compress the research into a founder-ready PRD
- sharpen ICP and objection handling
- draft pricing and packaging narrative
- create customer interview and pilot success templates

## Definition Of Done

A task is done when:

- the artifact exists in the repo
- the artifact names its assumptions
- dependencies and open questions are visible
- another agent can continue without re-reading the full chat

If that last line is false, the task is not done yet.
