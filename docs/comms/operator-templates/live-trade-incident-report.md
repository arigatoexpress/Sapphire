---
name: Live-trade incident report — structured 5-section
audience: Operator self-documentation; second audience is any acquirer reviewing the trade audit trail
when_to_use: When something unexpected happens with a live trade — fill outside expected slippage, partial fill, exchange weirdness, confirmation-token mishap, kill-switch trigger near a live order. Structured so future-you (or an acquirer) can reconstruct what happened.
placeholders: ["{{incident_date}}", "{{order_id}}", "{{symbol}}", "{{notional}}", "{{filed_by}}", "{{filed_at}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# Live-trade incident: {{order_id}} ({{symbol}}, ${{notional}})

**Incident date / time**: {{incident_date}}
**Order ID**: {{order_id}}
**Symbol / notional**: {{symbol}} / ${{notional}}
**Filed by**: {{filed_by}}
**Filed at**: {{filed_at}}

---

## 1. What happened

<Plain-English description of the actual sequence of events. Timestamps where possible. Include the order draft, the confirmation token use, the submit, the fill (or absence), and the moment something looked wrong.>

<Example structure:
- <timestamp> UTC — quote read; spread <fill> bps; bid <fill>; ask <fill>
- <timestamp> UTC — order draft created (limit <buy/sell> <size> {{symbol}} at <limit price>)
- <timestamp> UTC — confirmation token issued, operator entered token in active terminal
- <timestamp> UTC — order submitted through the approved execution endpoint
- <timestamp> UTC — fill confirmation: <size> {{symbol}} at <fill price>, fee <fill>
- <timestamp> UTC — observed: fill price <fill> away from limit price; expected near-limit fill
>

## 2. What should have happened

<What the system was designed to do; what the runbook says; what a clean execution would have looked like.>

<Example: per the governing live-trading ramp memo, a confirmed limit order at the current rung should fill at or near the quoted limit price. Sub-limit fills may be favorable, but any unexplained magnitude above the documented threshold warrants explanation.>

## 3. The gap

<The delta between actual and expected. Be specific about magnitude. Distinguish "favorable to operator" from "unfavorable" — both are gaps; only one is a problem.>

<Example: fill came in <amount> below limit. This is FAVORABLE. But: the magnitude (<bps>) is consistent with market-liquidity gaps in the execution window, not with the spread observed at quote-read time (<bps>). Implication: the spread we read is NOT the spread we got.>

## 4. The fix

<What you did or are going to do, immediately, to prevent this incident from recurring before the next live order.>

<Example: tighten the just-in-time quote re-read to the documented submit window; flag any quote-to-fill spread delta above the reviewed threshold for post-trade review. Add a liquidity-window warning to the dry-run output when market conditions require extra acknowledgement.>

## 5. The prevention

<The systemic / non-tactical change. What test, what telemetry, what guardrail, what runbook update prevents this entire class of issue, not just this specific one.>

<Example: add a `liquidity_window` metric to the order-draft envelope. Any draft with a flagged liquidity window must require operator double-confirmation (token + verbal acknowledgement of the window). Land via a PR; do not modify in production-only.>

---

## Disposition

- [ ] Filed in `docs/audit/live-incidents/{{incident_date}}-{{order_id}}.md`
- [ ] Ramp memo updated if the gap reveals a missing gate
- [ ] Confirmation firewall reviewed (was it correctly engaged at incident time?)
- [ ] Kill switch reviewed (was it correctly idle at incident time?)
- [ ] Any code change tied to this incident lands as a PR with a reference back to this file
- [ ] If the cap bump audit trail exists for this rung, link this incident from there

—{{filed_by}}, {{filed_at}}

## Notes for the operator (NOT part of the audit trail)

- Why this works: 5 sections force you to separate description, intent, gap, tactical fix, systemic prevention. Most incident reports collapse 4 and 5; that's how the same incident recurs in slightly mutated form.
- Common edits:
  - For confirmation-token mishaps specifically (token entered for wrong order, etc.), Section 1 should include EVERY token issuance + use in the surrounding 60 seconds, not just the involved one. Pattern matters.
  - For exchange-side weirdness (5xx, partial fill, unexpected order rejection), Section 2 should cite the relevant endpoint contract directly.
- Tone calibration: factual, not narrative. "The fill came in below limit" not "I was surprised when the fill came in below limit." Future-you and an acquirer don't care about your surprise; they care about the gap.
- DO file even for FAVORABLE gaps. A favorable gap of a given size can become an unfavorable gap of the same size next time. Pattern data is the point.
- DO NOT skip Section 5 even when the fix in Section 4 feels sufficient. The whole reason the ramp memo has 14-day Sortino soaks is that single-incident fixes don't catch class-of-issue problems.
