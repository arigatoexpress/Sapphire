---
name: Contractor — integration memo share (post-reply)
audience: External contractor after their alignment reply lands
when_to_use: When the contractor replies and the boundary memo is ready to share. Forwards the memo with framing that asks for input BEFORE they write workspace structure.
placeholders: ["{{operator_name}}", "{{first_name}}", "{{business_app_name}}", "{{workspace_tool_name}}", "{{existing_system_name}}", "{{memo_url_or_attachment}}", "{{first_deliverable_date}}", "{{specific_contractor_reply_paraphrase}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# Re: {{business_app_name}} workspace build — integration memo + your first deliverable

Hi {{first_name}},

Thanks for the reply — that scope confirmation tracks with what I was guessing. {{specific_contractor_reply_paraphrase}}

Attaching / linking the integration memo I mentioned: {{memo_url_or_attachment}}.

This is how I think {{workspace_tool_name}} and {{existing_system_name}} should split. Short version:

- **{{workspace_tool_name}} owns**: internal-team operational state — onboarding, training docs, vendor relationships, partnership SOPs, marketing assets. Anything where "the team is the audience."
- **{{existing_system_name}} owns**: customer state, source-of-truth records, document-package generation, and anything that touches a real lead's data.
- **Hard rule, please**: do not duplicate customer records into {{workspace_tool_name}}. If the team needs visibility into a customer there, that's a page-references-the-customer pattern, not a workspace-stores-the-customer pattern.

Read the memo and tell me if anything looks wrong from your side BEFORE you write a single workspace structure for customer-related state. If the boundary makes sense, the workspace skeleton you're building should fall out of it cleanly.

The {{first_deliverable_date}} target you proposed works for me.

—{{operator_name}}

## Notes for the operator (NOT in the sent message)

- Why this works: gives the contractor the boundary up front (so they don't waste billable hours on duplicate-state architecture), frames the hard rule as "please" not as a directive (preserves autonomy on their deliverable), and accepts the proposed deliverable date without negotiation when one exists.
- Common edits:
  - If the reply DIDN'T propose a first-deliverable date, drop the last line and add: "Send me a proposed first deliverable date when you've digested the memo."
  - The {{specific_contractor_reply_paraphrase}} should reference one specific thing from the reply. Validates that you read it.
- Tone calibration: collaborative-but-bounded. The hard rule is non-negotiable but framed politely. If the contractor pushes back on the boundary later, that's a separate conversation — not one to pre-emptively negotiate in this mail.
- DO NOT add private relationship context or additional stakeholders unless the thread already includes them and the escalation is intentional.
- The memo SHOULD already exist before you send this. Sending the framing without the artifact is hand-waving.
