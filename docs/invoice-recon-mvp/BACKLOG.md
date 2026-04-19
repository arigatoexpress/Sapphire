# Backlog

Use this file as the live queue and decision log for parallel work.

## Status Legend

- `todo`
- `in_progress`
- `blocked`
- `done`

## North Star

Ship a beta-ready AP workflow system that can ingest invoices, extract and validate fields, route approvals, post to one ERP, reconcile payments, and export a defensible audit trail.

## Workstreams

| ID | Workstream | Owner | Status | Write surface | Depends on | Done when |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | Product brief and PRD compression | Claude | todo | `docs/invoice-recon-mvp/README.md` or sibling PRD docs | None | MVP scope, ICP, KPI set, and deferrals are crisp enough to guide build |
| W2 | Canonical data model and state machine spec | Codex | todo | `docs/invoice-recon-mvp/ARCHITECTURE.md`, future schema files | None | Core entities, statuses, and event model are locked for alpha |
| W3 | Technical repo scaffold proposal | Codex | todo | future `invoice-recon/` tree, infra notes | W2 | Repo shape, service boundaries, and initial package contracts are defined |
| W4 | Operator workflow and review UX brief | Claude | todo | new UX doc or product doc sections | W1 | Review queue, correction loop, approvals, and reconciliation workflow are specified |
| W5 | ERP connector strategy for NetSuite and QBO | Codex | todo | adapter spec docs, future packages | W2 | Required objects, auth model, retry rules, and idempotency plan are written |
| W6 | Reconciliation rules and matching policy | Codex | todo | architecture or dedicated recon doc | W2 | Match states, evidence model, and manual override policy are defined |
| W7 | Pricing, pilot packaging, and GTM narrative | Claude | todo | new GTM docs | W1 | Pilot offer, packaging, pricing model, and objections are reusable |
| W8 | Security and compliance pack outline | Claude | todo | new security and compliance docs | W1, W2 | DPA and security questionnaire outline plus control narrative exist |
| W9 | Alpha implementation plan | Codex | todo | roadmap or build-plan doc | W2, W3, W5 | First 8-12 engineering slices are sequenced with dependencies |
| W10 | Beta onboarding and success playbook | Claude | todo | onboarding docs | W4, W7 | Pilot timeline, success criteria, and rollout checklist are usable |

## Immediate Sprint

### Codex lane

| Task | Status | Notes |
| --- | --- | --- |
| Lock canonical entities and status transitions | todo | Keep the initial model narrow |
| Define the extraction-to-review contract | todo | Include confidence and correction semantics |
| Define ERP posting idempotency strategy | todo | Must survive retries and partial failures |
| Define reconciliation match states | todo | Separate suggested, confirmed, and rejected states |

### Claude lane

| Task | Status | Notes |
| --- | --- | --- |
| Turn the research memo into a founder-readable PRD | todo | Keep it under 3-5 pages |
| Draft buyer objection handling by persona | todo | CFO, controller, AP manager, finance systems lead |
| Draft pilot success scorecard | todo | Include time-to-value and control metrics |
| Draft pricing narrative for Core, Growth, Enterprise | todo | Volume-based, not seat-based |

## Joint Review Gates

These require both agents to align before implementation spreads:

| Gate | Status | Decision needed |
| --- | --- | --- |
| G1 | todo | AWS-first vs Azure-first default |
| G2 | todo | Exact alpha ERP choice: NetSuite, QBO, or both in parallel |
| G3 | todo | Degree of line-item depth in alpha |
| G4 | todo | Whether reconciliation includes direct bank data in beta or stays ERP-payment-first |

## Decision Log

### D1

- Date: 2026-04-19
- Owner: Codex
- Change: Promoted the invoice recon execution pack into Sapphire as canonical initiative docs
- Why: The initiative needs one durable source of truth during repo consolidation and parallel agent work
- Impacted files:
  - `docs/invoice-recon-mvp/README.md`
  - `docs/invoice-recon-mvp/ARCHITECTURE.md`
  - `docs/invoice-recon-mvp/AGENT_SYSTEM.md`
  - `docs/invoice-recon-mvp/BACKLOG.md`
  - `services/control-plane/app/data/tracked_projects.json`
  - `services/control-plane/app/data/agentic_board.json`

## Open Questions

- Should the first live pilot optimize for NetSuite-heavy customers even if QBO is easier technically?
- How much PO matching is required in alpha versus beta?
- Should the first implementation package include bank file imports or only ERP payment reconciliation?
- Does the team want a dedicated product name now, or should the work stay descriptive until GTM sharpens?
