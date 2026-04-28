---
name: Etai contractor — day-3 nudge if no reply to 4-question email
audience: Etai Zilberman (Upwork contractor for THO Notion build)
when_to_use: 3 days after the 4-question email if no reply. Gentle nudge with a soft re-state of why the questions matter — avoids the integration-boundary problem getting worse via parallel work.
placeholders: ["{{date_original_sent}}", "{{first_name}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Re: THO Notion build — quick nudge

Hi {{first_name}},

Following up on my email from {{date_original_sent}} — no rush, but flagging this because the 4-question reply matters more than usual:

The reason I asked about scope and the integration boundary is that THO already has a Document Center (Cloud Run app, 1,963 customers in Firestore, 63 PDF templates). If the Notion workspace duplicates customer state, we'll end up with two sources of truth — exactly the kind of mess that's expensive to unwind later. So before you start writing Notion structure, I want to make sure we're aligned on what lives in Notion vs. what lives in the existing system.

If you've started building already, that's fine — just send me a screenshot of the workspace skeleton so I can flag any duplication risks before you go deeper. If you haven't started, the 4 questions still stand.

Signal number on file too if email's not the right channel for you.

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: doesn't repeat the original questions (he has them), but explains WHY they matter — contractors often ignore questions they don't understand the rationale for. Offers a concrete fallback ("send a screenshot") if he's already started, which handles the "I started without waiting" case gracefully.
- Common edits:
  - If you actually exchanged Signal numbers in earlier mail, drop the last line — re-asking signals you weren't paying attention.
  - If Etai already started building per a side channel (e.g. Celeste mentioned it), pivot to the screenshot ask first instead of the 4-question reminder.
- Tone calibration: contractor management voice — direct, not friendly-buddy. Etai is paid by the hour. Treating him like a peer collaborator makes the contract muddier; treating him like a vendor with deliverables keeps it clean. "Hi" not "Hey." First-person singular throughout.
- DO NOT mention that Celeste hired him through her first Upwork project. He knows. Mentioning it implies amateur hour.
- DO NOT cc Celeste on the nudge. The 4-question email was direct-line per the original setup; cc'ing her now is escalation that undermines Etai's autonomy on his own deliverable.
