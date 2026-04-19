# Invoice Recon MVP

This folder is the canonical execution pack for a mid-market invoice processing and payment reconciliation SaaS initiative being incubated inside Sapphire during repo consolidation.

The wedge is intentionally narrow:

```text
capture -> validate -> approve -> post -> reconcile -> audit
```

The product is not a full procure-to-pay suite, not an embedded-payments business, and not a general finance automation platform. It is a workflow-and-controls system of record for AP teams that need faster processing, fewer exceptions, stronger reconciliation, and defensible audit evidence.

## Why This Exists In Sapphire

Sapphire is currently the canonical repo during consolidation. The Codex workspace can still be used as operator scratchpad, but this folder is the durable source of truth for the initiative.

## Target Customer

- US-first companies in the $50M-$250M revenue band
- 3,000-25,000 invoices per month
- Multi-entity or multi-approver complexity
- Lean AP teams with manual email and PDF intake
- NetSuite or QuickBooks Online first, Business Central next

## What Ships In MVP

- Invoice intake from mailbox, upload, and simple file import paths
- OCR and structured extraction with confidence scoring
- Human review console with validation warnings
- Approval workflows based on amount, entity, department, and delegate rules
- ERP posting with idempotent retries and status sync
- Payment import and reconciliation workbench
- Immutable audit log and evidence export
- Basic analytics for cycle time, exception rate, queue aging, and match rate

## Explicit Deferrals

- Embedded payments, virtual cards, or payment execution
- Supplier portal and supplier onboarding network
- Procurement or PO suite expansion beyond basic matching hooks
- Multi-country tax automation and localization-heavy compliance
- Fully autonomous posting of low-confidence documents

## Product Rules

- No irreversible accounting action without deterministic checks.
- Low-confidence documents always land in human review.
- Every correction, approval, and outbound ERP action must be explainable later.
- The canonical invoice model sits above ERP-specific adapters.
- If a feature does not improve cycle time, exception rate, reconciliation, or auditability, it probably slips.

## Release Path

### Alpha

- Intake normalization
- OCR and extraction
- Review queue
- Bill creation in one ERP

### Beta

- Approval engine
- Duplicate detection
- Payment import and reconciliation
- Operational reporting

### GA

- Audit export pack
- Admin and role hardening
- Second ERP connector
- Implementation tooling

## Commercial Shape

- Pricing model: annual platform fee plus invoice-volume allowance and overage
- Initial packaging:
  - Core: one ERP, one to two entities, base workflow
  - Growth: multi-entity, higher volume, stronger reporting and controls
  - Enterprise: SSO, advanced controls, premium support, heavier implementation

## Success Metrics

- Time to first posted invoice
- Time to first reconciled payment
- Invoice cycle time
- Exception rate
- Straight-through rate
- Auto-match rate
- Audit export completeness
- ERP posting success rate

## How To Use This Pack

- [ARCHITECTURE.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/ARCHITECTURE.md): opinionated system design and repo shape
- [AGENT_SYSTEM.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/AGENT_SYSTEM.md): how Codex and Claude split work in parallel
- [BACKLOG.md](/Users/aribs/Code/Sapphire/docs/invoice-recon-mvp/BACKLOG.md): executable workstreams, dependencies, and near-term queue

## Working Assumption

This pack assumes the research memo that kicked off the initiative is directionally right and converts it into build and coordination artifacts. It does not re-litigate the market thesis; it operationalizes it.
