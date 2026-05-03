# Zama AI Agent Skills · write-fhevm-contracts — 60s Pitch Video Script

**Target:** 60s — bounty calls for a 3-minute demo, but 60s is the
judging-room cut. The 3-minute deep-dive is at
`docs/grants/zama-ai-agent-skills/SUBMISSION.md` and is a separate take.
**Recording:** 1080p, no music, screen-recording driven by an actual LLM
session (Claude Code or Cursor) so judges see the skill *firing*.
**Bounty:** Zama Developer Program Mainnet Season 2 — Bounty Track · AI Agent Skills
**Prize:** 1st 1,500 cUSDT · 2nd 1,000 · 3rd 500 (3,000 cUSDT total)
**Deadline:** 2026-05-10 23:59 (still ahead — 8 days from 2026-05-02)
**Submission anchor:** PR [#564](https://github.com/arigatoexpress/Sapphire/pull/564)

---

## [0:00] · Hook (8s)

**Voice:**
> "Five silent-failure footguns in fhEVM. We taught Claude to catch all
> five before the contract compiles."

**On screen:**
- Black background, five red-text footgun names fade in:
  1. `FHE.select` doesn't exist on plain bools
  2. ACL grants must be re-issued post-decryption
  3. Input proofs need encrypted-input registration
  4. Async decryption returns via callback, not return value
  5. `ZamaEthereumConfig` inheritance is silent if missed

---

## [0:08] · The skill in action — round 1 (15s)

**Voice:**
> "User asks Claude to write a confidential basket-weight contract. Claude
> sees the prompt mentions 'private', triggers the skill, and applies the
> ten-point pre-write checklist before writing a line of code."

**On screen:**
- Real screen capture of a Claude Code session.
- User types: *"Write me a confidential basket-weight contract on fhEVM."*
- Skill auto-activates — sidebar shows "fhevm-skill loaded."
- Claude writes the contract preamble, including the
  `ZamaEthereumConfig` inheritance that 8/10 LLM-written drafts miss.

---

## [0:23] · The skill in action — round 2 (15s)

**Voice:**
> "User asks for a public-result accessor. Claude knows public results
> require an async decryption callback. It doesn't return a euint
> directly. It registers a callback. The skill catches the footgun
> before the contract compiles."

**On screen:**
- User types: *"Add a `getPublicWeight()` view function."*
- Claude writes:
  ```solidity
  // FOOTGUN: cannot return euint directly from view.
  // Use FHE.requestDecryption() with callback pattern.
  function requestPublicWeight() external {
      FHE.requestDecryption(weight, this.fulfillPublicWeight.selector);
  }
  function fulfillPublicWeight(uint256 requestId, uint256 result, ...)
      external onlyGateway { ... }
  ```
- Yellow box on the `// FOOTGUN:` comment line.

---

## [0:38] · The 10-point self-check (12s)

**Voice:**
> "Before returning, the skill runs a ten-point self-check. ACL re-grants?
> Yes. Input-proof registration? Yes. ZamaEthereumConfig inheritance? Yes.
> Decryption pattern correct? Yes. The skill answers all ten before the
> response renders."

**On screen:**
- Animated checklist with 10 green ticks fading in one at a time.
- Each tick is one line from `docs/grants/zama-ai-agent-skills/SKILL.md`'s
  pre-return checklist.

---

## [0:50] · The credibility (5s)

**Voice:**
> "Sapphire ships fourteen production agent skills today. We eat this
> format daily."

**On screen:**
- Terminal:
  ```
  $ ls ~/.hermes/skills/sapphire/ | wc -l
  14
  ```
- Plus a screenshot of the registered Sapphire plugin tool list (109 on
  disk, 17 manifest entries).

---

## [0:55] · End card (5s)

**Voice:**
> "fhevm-skill — a portable AI Agent Skill for Zama. PR five-six-four."

**On screen (static end card, hold 5s):**

```
docs/grants/zama-ai-agent-skills/

Bounty: Zama Developer Program Mainnet Season 2
PR #564 · github.com/arigatoexpress/Sapphire
hack.sapphirealpha.xyz

#Zama #fhEVM #AIAgentSkills
```

---

## Director's notes

- **Real LLM session, not a screencap mock.** The Zama bounty page
  explicitly judges "agent effectiveness" — that means the skill must
  fire in a real coding-agent session. Use Claude Code with the
  bounty-targeted skill loaded.
- **Five footguns is the structural beat.** Each footgun is a separate
  test case in `docs/grants/zama-ai-agent-skills/EXAMPLE_REBUILD.md`.
  When recording, pick the one that lands fastest visually (likely
  ZamaEthereumConfig inheritance — easiest to show as a one-line miss).
- **The 10-point self-check is the defensibility.** It's what separates
  this skill from a "long prompt." A skill that runs a deterministic
  pre-return checklist on its own output is the criterion-3 ("agent
  effectiveness") match.
- **Zama explicitly asks for a 3-minute demo.** The 60s cut is the
  judging-room trailer. The 3-min cut at
  `docs/grants/zama-ai-agent-skills/SUBMISSION.md` is the formal deliverable.

---

## Recording sequence

1. Pre-flight: load `docs/grants/zama-ai-agent-skills/SKILL.md` into a
   fresh Claude Code session. Confirm skill auto-activates on the
   trigger phrase ("confidential", "fhEVM", "encrypted basket").
2. Pre-write the example user prompts so they paste cleanly without typos.
3. Pre-warm the screen-recording app; full-screen the editor.
4. Record take 1 of all 6 segments back to back (60s).
5. Watch take 1. If the skill fails to auto-activate in any segment,
   debug the YAML frontmatter and re-record that segment.
6. Record take 2 of full 60s as backup.
7. Edit, splice, add overlays.
8. Final cut ≤60s — for judging-room use.
9. Separately: cut the formal 3-minute submission video using the same
   takes plus 2 additional footgun walkthroughs. That's the asset for
   the Zama submission form.
10. Upload both to YouTube unlisted. 60s URL → README + frontend; 3-min
    URL → Zama bounty submission.
