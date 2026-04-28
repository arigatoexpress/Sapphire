---
name: Partner marketing-site issue — broken link / CMS access
audience: Reporting partner plus copied stakeholders
when_to_use: Generic reply for marketing/website breakage — broken PDF link, broken landing page, missing image. Triages WITHOUT promising you can fix it if CMS access is unclear.
placeholders: ["{{operator_name}}", "{{broken_url}}", "{{site_domain}}", "{{site_platform_hint}}", "{{filename_or_page}}", "{{first_name}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# Re: {{filename_or_page}} — broken link

Hey {{first_name}},

Confirmed on my end — {{broken_url}} is 404'ing.

The {{site_domain}} site isn't in my app repo, so I don't have CMS admin to re-upload the file myself. Two questions to unblock:

1. Who has admin access to {{site_domain}}? ({{site_platform_hint}}?) If I can get access, I'll re-upload after confirming the source file.
2. Is the source file ({{filename_or_page}}) somewhere in our shared folder? If yes, send me the link and I'll be ready to upload the moment we have CMS access.

If neither has an obvious answer, no rush — I'll dig through old emails to find whoever set the site up originally. Just a heads-up that without CMS access this is a "nice to fix this week" not a "fix this morning."

—{{operator_name}}

## Notes for the operator (NOT in the sent message)

- Why this works: confirms the bug fast (validates the report), separates "things I CAN do" from "things blocked on someone else's access", sets clear next-step questions, and explicitly downgrades urgency since you can't single-handedly resolve it.
- Common edits:
  - If you actually DO have CMS access (operator: check before sending), drop the whole second paragraph and just say "fixing now, will confirm when live."
  - If there is only one recipient, drop "send me the link and I'll be ready to upload" — replace with "I'll just need ten minutes whenever you can pull it up."
- Tone calibration: partner-warm. The downgrade-the-urgency line ("nice to fix this week, not fix this morning") protects against scope creep.
- Do NOT volunteer to "look into who set up the site" as a commitment unless you're actually going to do it that day. Better to say "we should figure that out at some point" than commit and forget.
