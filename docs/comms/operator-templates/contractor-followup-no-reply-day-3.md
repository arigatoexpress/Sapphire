---
name: Contractor — day-3 nudge if no reply to alignment email
audience: External contractor assigned to a partner-ops build
when_to_use: 3 days after the 4-question email if no reply. Gentle nudge with a soft re-state of why the questions matter — avoids the integration-boundary problem getting worse via parallel work.
placeholders: ["{{operator_name}}", "{{date_original_sent}}", "{{first_name}}", "{{business_app_name}}", "{{workspace_tool_name}}", "{{existing_system_name}}", "{{existing_system_context}}", "{{alternate_contact_channel}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# Re: {{business_app_name}} workspace build — quick nudge

Hi {{first_name}},

Following up on my email from {{date_original_sent}} — no rush, but flagging this because the 4-question reply matters more than usual:

The reason I asked about scope and the integration boundary is that {{existing_system_name}} already owns {{existing_system_context}}. If the {{workspace_tool_name}} workspace duplicates customer state, we'll end up with two sources of truth — exactly the kind of mess that's expensive to unwind later. So before you start writing workspace structure, I want to make sure we're aligned on what lives in {{workspace_tool_name}} vs. what lives in the existing system.

If you've started building already, that's fine — just send me a screenshot of the workspace skeleton so I can flag any duplication risks before you go deeper. If you haven't started, the 4 questions still stand.

{{alternate_contact_channel}} works too if email's not the right channel for you.

—{{operator_name}}

## Notes for the operator (NOT in the sent message)

- Why this works: doesn't repeat the original questions (he has them), but explains WHY they matter — contractors often ignore questions they don't understand the rationale for. Offers a concrete fallback ("send a screenshot") if he's already started, which handles the "I started without waiting" case gracefully.
- Common edits:
  - If there is no already-established alternate channel, drop the {{alternate_contact_channel}} line entirely.
  - If the contractor already started building per a side channel, pivot to the screenshot ask first instead of the 4-question reminder.
- Tone calibration: contractor management voice — direct, not friendly-buddy. Treat the contractor as a vendor with deliverables so the contract stays clean. "Hi" not "Hey." First-person singular throughout.
- DO NOT include private hiring context, personal relationship context, or stakeholder names in this nudge.
- DO NOT cc additional stakeholders unless the original thread already included them and the escalation is intentional.
