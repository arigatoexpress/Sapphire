---
name: THO marketing-site issue — broken link / CMS access
audience: Celeste (mom), CC's likely include Mark, Ben, Mike at manufacturedhomes.com, Lee
when_to_use: Generic reply for marketing/website breakage on texashomeoutlet.com — broken PDF link, broken landing page, missing image. Triages WITHOUT promising you can fix it (operator may not have CMS access).
placeholders: ["{{broken_url}}", "{{filename_or_page}}", "{{first_name}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Re: {{filename_or_page}} — broken link

Hey {{first_name}},

Confirmed on my end — {{broken_url}} is 404'ing.

The texashomeoutlet.com site isn't in any of my repos (the Cloud Run app is the customer-facing app, not the marketing site), so I don't have CMS admin to re-upload the file myself. Two questions to unblock:

1. Who has admin access to the texashomeoutlet.com site? (Squarespace? Wix? Something else?) If I can get login I'll re-upload tonight.
2. Is the source file ({{filename_or_page}}) somewhere in our shared Drive? If yes, send me the link and I'll be ready to upload the moment we have CMS access.

If neither has an obvious answer, no rush — I'll dig through old emails to find whoever set the site up originally. Just a heads-up that without CMS access this is a "nice to fix this week" not a "fix this morning."

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: confirms the bug fast (validates the report), separates "things I CAN do" from "things blocked on someone else's access", sets clear next-step questions, and explicitly downgrades urgency since you can't single-handedly resolve it.
- Common edits:
  - If you actually DO have CMS access (operator: check before sending), drop the whole second paragraph and just say "fixing now, will confirm when live."
  - If Celeste is the only recipient, drop "send me the link and I'll be ready to upload" — replace with "I'll just need ten minutes whenever you can pull it up."
- Tone calibration: family-warm. "Hey Celeste" not "Hi Celeste" if it's just to her. The downgrade-the-urgency line ("nice to fix this week, not fix this morning") protects against scope creep — partners sometimes treat marketing-site issues as Cloud Run priority. They aren't.
- Do NOT volunteer to "look into who set up the site" as a commitment unless you're actually going to do it that day. Better to say "we should figure that out at some point" than commit and forget.
