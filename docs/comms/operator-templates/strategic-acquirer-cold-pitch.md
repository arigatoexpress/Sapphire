---
name: Strategic acquirer first-touch cold pitch
audience: Strategic acquirer team lead, corp-dev, product lead, or equivalent target
when_to_use: First-touch outreach after verifying that every proof point is current, non-sensitive, and appropriate for the recipient.
placeholders: ["{{operator_name}}", "{{first_name}}", "{{their_team}}", "{{target_company}}", "{{target_platform_or_program}}", "{{system_name}}", "{{proof_point_summary}}", "{{execution_endpoint_summary}}", "{{cap_ladder_summary}}", "{{performance_summary}}", "{{diligence_pr_url}}", "{{microsite_url}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# {{system_name}} operational-trust stack — possible {{target_platform_or_program}} / corp-dev fit?

Hi {{first_name}},

I'm a solo engineer running {{system_name}} — an operational control plane for research, risk-gated autonomy, and intelligence work. The current verified proof point I would lead with is: {{proof_point_summary}}.

I think there's a {{their_team}}-shaped fit at {{target_company}}. The pitch:

1. **Operational trust at the model layer.** Every artifact (signal, prediction, draft order) is provenance-stamped — generator, source hashes, prompt hash, model, time, TTL. The risk kernel evaluates a versioned decision envelope before any mutation. Live execution is dry-run by default; one-order confirmation tokens unlock single fills, not loops.
2. **Domain-native by build, not bolt-on.** The system is hardened for {{execution_endpoint_summary}} and uses {{cap_ladder_summary}}. It should read as a system with a safety posture first, not a demo that learned controls later.
3. **Continuous intelligence surface.** {{performance_summary}}. Paper-mode and dry-run evidence remain the default evidence source; any live-capital language should stay limited to verified, approved proof points.

The primary ask is an integration POC — does {{target_platform_or_program}} want a partner who's already built the operational guardrails {{target_company}} would otherwise have to build internally for any third-party signal venue? IP licensing or acqui-hire are second-order paths if the technical review lands.

Diligence packet (10 docs covering architecture, security, data, ops, financials, roadmap): {{diligence_pr_url}}.

Acquirer microsite: {{microsite_url}}.

I'm one person with a working system that respects safety. That's both the strength and the structural reality the conversation has to address.

—{{operator_name}}

## Notes for the operator (NOT in the sent message)

- Why this works: leads with a concrete proof point without hard-coding private trade data, company-specific claims, or stale performance numbers. It addresses the solo-engineer reality up front rather than hiding it.
- Common edits: swap the team and program placeholders based on the actual recipient. If the recipient is corp-dev rather than product, make the second paragraph capability-focused instead of product-focused.
- Tone calibration: direct and evidence-led. Avoid abstraction-first opening lines; lead with the verified proof point and then the control posture.
- Do NOT include dollar amounts, trade IDs, endpoint names, accuracy percentages, test counts, or artifact counts unless you have just verified them and they are appropriate for this recipient.
