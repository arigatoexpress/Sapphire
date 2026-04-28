---
name: Etai contractor — integration memo share (post-reply)
audience: Etai Zilberman, after his 4-question reply lands
when_to_use: When Etai replies and the boundary memo (Project-Go-Forward PR #26 or equivalent) is ready to share. Forwards the memo with framing that asks for input BEFORE he writes Notion structure.
placeholders: ["{{first_name}}", "{{memo_url_or_attachment}}", "{{first_deliverable_date}}", "{{specific_etai_question_paraphrase}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Re: THO Notion build — integration memo + your first deliverable

Hi {{first_name}},

Thanks for the reply — that scope confirmation tracks with what I was guessing. {{specific_etai_question_paraphrase}}

Attaching / linking the integration memo I mentioned: {{memo_url_or_attachment}}.

This is how I think Notion and the existing Project-Go-Forward Document Center should split. Short version:

- **Notion owns**: internal-team operational state — onboarding, training docs, vendor relationships, partnership SOPs, marketing assets. Anything where "the team is the audience."
- **Project-Go-Forward owns**: customer state — the 1,963 customers in Firestore, the 63 PDF templates, the document-package generation, anything that touches a real lead's data.
- **Hard rule, please**: do not duplicate customer records into Notion. If the team needs visibility into a customer in Notion, that's a Notion-page-references-the-customer pattern, not a Notion-stores-the-customer pattern.

Read the memo and tell me if anything looks wrong from your side BEFORE you write a single Notion structure for customer-related state. If the boundary makes sense, the workspace skeleton you're building should fall out of it cleanly.

The {{first_deliverable_date}} target you proposed works for me.

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: gives Etai the boundary up front (so he doesn't waste billable hours on duplicate-state architecture), frames the hard rule as "please" not as a directive (preserves his autonomy on his own deliverable), and accepts his proposed deliverable date without negotiation (rewards his having proposed one — many contractors don't).
- Common edits:
  - If Etai's reply DIDN'T propose a first-deliverable date, drop the last line and add: "Send me a proposed first deliverable date when you've digested the memo."
  - The {{specific_etai_question_paraphrase}} should reference one specific thing from his reply — e.g. "Yeah, 'all 11' = the eleven THO staff makes sense, that's what I figured." Validates that you read it.
- Tone calibration: collaborative-but-bounded. The hard rule is non-negotiable but framed politely. If he pushes back on the boundary later, that's a separate conversation — not one to pre-emptively negotiate in this mail.
- DO NOT cc Celeste. She is the contract-holder but Etai's deliverable is between him and you per the existing thread setup. CC'ing her here would re-route his accountability through her, which is the opposite of what you want.
- The memo SHOULD already be in PR #26 (or wherever) before you send this. Sending the framing without the artifact is hand-waving.
