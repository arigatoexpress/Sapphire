---
name: Intro-call prep — 1-pager handed to operator before any new conversation
audience: Operator (Ari) — pre-call brief, not a sent comms
when_to_use: Before any new prospect / inbound / corp-dev / partner intro call. Read 5-10 minutes before the call. Forces explicit articulation of who they are, what each side wants, and what would make you walk.
placeholders: ["{{call_date}}", "{{their_name}}", "{{their_company}}", "{{their_role}}", "{{call_duration_min}}", "{{intro_source}}", "{{their_company_short_summary}}", "{{three_questions}}", "{{three_things_to_mention}}", "{{hard_pass_triggers}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Intro call prep: {{their_name}} ({{their_company}}) — {{call_date}}

**Call duration**: {{call_duration_min}} minutes
**Intro source**: {{intro_source}}
**Their role**: {{their_role}}

## Who they are

{{their_company_short_summary}}

(2-3 sentences. What does the company do? Public / private? Stage? Why does this person at this company plausibly care about Sapphire?)

## What they want

<Best-guess hypothesis for what {{their_name}} wants out of the call. Useful frames:
- They want to understand the system to evaluate buy / partner / pass.
- They want to extract information to inform a competitor or internal build.
- They're warming a relationship with a future deal in mind.
- They were asked to take this call by someone above them and have no agenda.
- They have a specific narrow ask (one engineer's hire, one license, one POC).

Pick the most likely. Be honest if "I genuinely don't know" — write that.>

## What we want

<Be specific. Examples:
- A second meeting with their engineering lead.
- An NDA-gated technical review.
- An introduction to their corp-dev team.
- An honest no, with reasons.
- Permission to use the conversation as a reference (e.g. "we're talking to {{their_company}}").

What we want is NOT necessarily an offer or money. Often it's a redirect or a yes/no on a narrow question.>

## Three questions we'll ask

1. {{three_questions}}
2. <continued>
3. <continued>

(One of these should be a "kill" question — something whose answer determines whether to keep investing time here. Examples: "What's the realistic timeline for a decision on something like this at {{their_company}}?" "If we did a POC, who would be the technical sponsor inside your team?" "What would have to be true for this to become a yes for you?")

## Three things we'll mention

1. {{three_things_to_mention}}
2. <continued>
3. <continued>

(One of these should be the strongest concrete proof point — the $5 BTC live fill, the 211 provenance-stamped artifacts, the 5,281 tests. Specific, not abstract. The other two should be tailored to what this specific company would care about.)

## Hard-pass triggers

<Things that, if they say or imply during the call, mean we walk. Examples:
- "We'd want to see the system running before any commercial conversation." (Translation: free trial / extraction.)
- "Our team would build this in 6 weeks anyway, but we're curious." (Translation: information-gathering.)
- "We don't pay for IP at the early-stage; we'd structure this as an acqui-hire only." (Hard pass only if Ari has not pre-decided acqui-hire is acceptable.)
- "We'd want to fold the IP into our existing platform under our license." (Without compensation discussion: hard pass.)
- Any indication they want a multi-week unpaid POC before commercial framing.

If a hard-pass trigger fires: politely close the call ("appreciate the time, doesn't sound like the right fit"), document in the post-call note, do NOT promise follow-up materials.>

## Post-call note (fill after)

- What they actually said vs. what we expected: <fill>
- Did any hard-pass trigger fire: yes / no
- Action items, with owners and dates: <fill>
- Next contact (if any): <date> — what's required from us before then

## Notes for the operator (NOT part of the prep doc)

- Why this works: forces explicit articulation BEFORE the call so you don't end up improvising in front of a corp-dev rep who absolutely has done their prep. The "what we want" section catches the most common operator failure — running calls without a clear self-ask, then over-investing in follow-up.
- Common edits:
  - For warm-intro calls (came through a mutual contact), the "intro source" matters — if the introducer cares about the relationship, that constrains what hard-pass triggers you'd act on. Sometimes you take the call all the way even when it's clearly going nowhere, to protect the introducer.
  - For inbound (they reached out to you), invert the hypothesis: assume they have an ask in mind and the questions section should pull it out earlier.
- Tone calibration: this is a self-document. Be honest, even uncharitable. "I genuinely don't know what they want" is more useful than a fabricated guess. Same for hard-pass triggers — write the ones you'd actually act on, not the ones that sound principled.
- DO read this 5-10 minutes before the call, not the day before. Day-before reading lets you forget specifics.
- DO write the post-call note within 30 minutes of hanging up. Memory degrades fast.
