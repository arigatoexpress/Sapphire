---
name: Live-trade cap bump — operator-to-self decision documentation
audience: Operator (Ari) — self-documentation, not a sent comms
when_to_use: Before promoting from $5 to $50 (or $50 to $500). Documents the decision with the Sortino-soak evidence required by docs/products/live-trading-ramp-memo.md. This file becomes the audit trail for the cap change.
placeholders: ["{{decision_date}}", "{{from_cap}}", "{{to_cap}}", "{{soak_window_start}}", "{{soak_window_end}}", "{{sortino_value}}", "{{paper_drift_summary}}", "{{readiness_sweep_result}}", "{{kill_switch_status}}", "{{confirmation_firewall_status}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Live-trade cap bump: ${{from_cap}} → ${{to_cap}}

**Decision date**: {{decision_date}}
**Decided by**: Ari (operator, sole authority)
**Soak window evaluated**: {{soak_window_start}} → {{soak_window_end}} ({{soak_window_end | days_since_start}} trading days)

## Evidence

Per `docs/products/live-trading-ramp-memo.md` Phase 1/2 promotion gates:

- [ ] **14 trading-day Sortino > 1.5 at the tested strategy level**
  - Computed Sortino: {{sortino_value}}
  - Window: {{soak_window_start}} → {{soak_window_end}}
  - Source: `data/live_portfolio.jsonl` reconciled against `data/paper_portfolio.json`
- [ ] **No unreviewed hard-risk holds during the window**
  - HardRiskKernel hold count in window: <fill>
  - Each hold reviewed and resolved: yes / no
- [ ] **No confirmation-firewall bypass**
  - All ${{from_cap}}-rung orders required token: yes / no
  - All token uses logged in `data/live/confirmation_log.jsonl`: yes / no
- [ ] **No unexplained slippage or fill-shape mismatch**
  - Paper-to-live drift summary: {{paper_drift_summary}}
  - Largest unexplained slippage event in window: <fill or "none">
- [ ] **Production readiness sweep returns 0 FAIL**
  - Last run: <date>
  - Result: {{readiness_sweep_result}}
- [ ] **Kill switch inactive at decision time**
  - Status at {{decision_date}}: {{kill_switch_status}}
- [ ] **Confirmation firewall remains live-auto-approve disabled**
  - Status at {{decision_date}}: {{confirmation_firewall_status}}

## Decision

If all checkboxes above are checked AND no checkbox required a "no" answer:
- Cap bump APPROVED. Update the operator-side cap from ${{from_cap}} to ${{to_cap}}.
- Next soak window starts: {{soak_window_end}} (i.e. immediately).
- Next promotion eligible no earlier than: {{soak_window_end | plus_14_trading_days}}.
- File this document in `docs/audit/live-cap-bumps/{{decision_date}}-{{from_cap}}-to-{{to_cap}}.md`.

If ANY checkbox is unchecked or a "no" answer is required:
- Cap bump DENIED. Stay at ${{from_cap}}. Document the failing gate(s) and the remediation plan below.
- Re-evaluate after the gate is resolved — restart the 14-day clock from the resolution date, not the original window start.

## Remediation (only if denied)

<fill in: which gate failed, what specifically needs to happen to fix it, what's the realistic timeline>

## Notes

- This decision is operator-sole. No autonomous system or external party authorizes a cap bump.
- The $500 tier (if {{to_cap}} = 500) requires a separate PR plus operator-reviewed runbook update per the ramp memo. This document is necessary but NOT sufficient for that rung.
- A buyer or acquirer cannot inherit cap-bump authority by virtue of acquisition. The risk committee has to issue its own authorization.

—Ari (operator, sole signature)

## Notes for the operator (NOT part of the audit trail)

- Why this works: forces every promotion gate from the ramp memo to be checked individually, makes the "deny" path explicit (so "I think it's mostly fine" cannot pass as approval), and codes the audit trail location into the template itself so the document doesn't get lost.
- Common edits: if you add a new strategy to the live-trading book, the Sortino computation may need a per-strategy breakdown rather than aggregate. Update the Evidence section's first bullet to list per-strategy.
- Tone calibration: this is a cold legal-style audit doc, NOT a warm operator narrative. The point is auditability, not voice. Keep it formal.
- DO NOT use this template if {{to_cap}} > 500. The $500 rung is the documented ceiling. Anything above requires a new ramp memo phase, not a new template instance.
- DO file this even when DENIED. The denial trail is more valuable than the approval trail because it documents discipline.
