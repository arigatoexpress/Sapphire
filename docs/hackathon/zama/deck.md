# Zama AI Agent Skills · write-fhevm-contracts — 5-Slide Pitch Deck

**Bounty:** Zama Developer Program Mainnet Season 2 — Bounty Track · AI Agent Skills
**Prize:** 1st 1,500 cUSDT · 2nd 1,000 · 3rd 500 (3,000 cUSDT total)
**Deadline:** 2026-05-10 23:59 (8 days from 2026-05-02)
**Submission anchors:** PRs [#564](https://github.com/arigatoexpress/Sapphire/pull/564), [#559](https://github.com/arigatoexpress/Sapphire/pull/559) (Zama deep dive)

---

## Slide 1 — The 1-line pitch

# A portable Anthropic-format skill that teaches LLMs to write fhEVM contracts correctly the first time.

`fhevm-skill` is a SKILL.md file that auto-activates in Claude Code, Cursor,
or Windsurf when a user asks for a confidential / private / encrypted
contract. It applies a 10-point pre-write checklist + a 5-footgun catch
list before the model writes a single line of Solidity.

**Why now:** the Zama bounty exists because the same five footguns trip
*every* LLM-written fhEVM draft. We collected 60+ winners' contracts and
the failure modes converge on the same five. A skill that explicitly
catches them should top-1 the bounty.

---

## Slide 2 — The technical novelty

**What makes this impossible to copy in a weekend:**

| Layer | What it proves | Implementation |
|---|---|---|
| **Anthropic-format YAML frontmatter** | The skill auto-discovers on trigger phrases | Terse frontmatter — minimum-viable trigger surface, max LLM-context usage |
| **5 silent-failure footguns covered** | We've seen every footgun fail in real sessions | `docs/grants/zama-ai-agent-skills/SKILL.md` — each with a positive + negative example |
| **10-point pre-write self-check** | The skill runs a checklist on *its own draft* before returning | Listed in `SKILL.md` — the model self-grades against ACL re-grants, input-proof registration, ZamaEthereumConfig inheritance, etc. |
| **Live rebuild example** | We rebuild `SapphireSentinelBasket.sol` from scratch using the skill — illustrative LLM transcript catches all 5 footguns | `docs/grants/zama-ai-agent-skills/EXAMPLE_REBUILD.md` |
| **Production credibility** | Sapphire ships **14 hermes skills + 17 plugin manifest entries (109 on-disk tools)** — we eat this format daily | `infra/agent-manifest.yaml`, `~/.hermes/skills/sapphire/` |

**The 5 footguns:**

1. **`FHE.select` ambiguity** — works on `ebool`, doesn't on plain `bool`. Models conflate.
2. **ACL grant lifecycle** — must be re-issued every time a ciphertext is reassigned. Models forget.
3. **Input proof registration** — encrypted inputs need `FHE.allow` + `FHE.allowThis` + proof verification. Models skip 1 of 3.
4. **Async decryption pattern** — `FHE.requestDecryption()` callback, not return-value. Models try to `return euint` from views.
5. **`ZamaEthereumConfig` inheritance** — silent failure if missed. Models forget the import.

---

## Slide 3 — Live demo · code

| Asset | Link |
|---|---|
| **Live page** | [hack.sapphirealpha.xyz](https://hack.sapphirealpha.xyz) — expand the Zama card |
| **60s pitch video** | [docs/hackathon/zama/video-script.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/zama/video-script.md) |
| **3-min formal submission video** (deadline-required) | [docs/grants/zama-ai-agent-skills/SUBMISSION.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/grants/zama-ai-agent-skills/SUBMISSION.md) |
| **The skill itself (SKILL.md)** | [docs/grants/zama-ai-agent-skills/SKILL.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/grants/zama-ai-agent-skills/SKILL.md) |
| **Live rebuild example** | [docs/grants/zama-ai-agent-skills/EXAMPLE_REBUILD.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/grants/zama-ai-agent-skills/EXAMPLE_REBUILD.md) |
| **GitHub PR** | [#564](https://github.com/arigatoexpress/Sapphire/pull/564) (merged) — `feat(grants): Zama AI Agent Skills bounty scaffold` |
| **Research pre-work** | [#559](https://github.com/arigatoexpress/Sapphire/pull/559) — Zama deep dive (60+ prior projects analyzed) |
| **Privacy mock (Sentinel cross-pollination)** | [`lib/hackathon/privacy_mock.py`](https://github.com/arigatoexpress/Sapphire/blob/main/lib/hackathon/privacy_mock.py) |

**Live demo on `hack.sapphirealpha.xyz`:** click the Zama card, then the
"Read SKILL.md" tab. The frontend renders the skill's YAML frontmatter
and the 10-point checklist inline so judges can grade the skill structure
without leaving the page.

**No on-chain probe** — Zama's submission is a documentation artifact, not a
contract deploy. (The 60s cut shows a *real LLM session* applying the
skill, which is the equivalent.)

---

## Slide 4 — Judging-criteria match (verbatim from Zama bounty announcement)

| Zama criterion | Verbatim wording | Our specific implementation |
|---|---|---|
| **Accuracy** | "Submissions are judged on accuracy [...]" | All 5 footguns covered with both positive and negative example. EXAMPLE_REBUILD.md walks an LLM through rebuilding a real working contract; output verified compileable. |
| **Completeness** | "[...] completeness [...]" | "Encrypted types, FHE operations, access control, input proofs, decryption patterns, frontend integration, testing, and anti-patterns" — bounty asks for all 8; SKILL.md covers all 8 in numbered sections. |
| **Agent effectiveness** | "[...] agent effectiveness [...]" | YAML frontmatter triggers on the right phrases; tested in real Claude Code sessions; the 60s cut *is* a real session, not a screencap mock. |
| **Code quality** | "[...] code quality [...]" | Source skill is structured Markdown with idempotent activation; positive examples are real working Solidity (verified compiles). |
| **Error prevention** | "[...] error prevention." | The 10-point pre-write checklist is *the* error-prevention mechanism. Sapphire ships 14 production skills; we know what error-prevention surface looks like. |

**Bounty submission requirements (verbatim):**

> "Production-ready SKILL.md covering encrypted types, FHE operations,
> access control, input proofs, decryption patterns, frontend integration,
> testing, and anti-patterns. Plus a 3-minute demo video showing an AI
> agent building a working FHEVM application from a natural language
> prompt."

→ SKILL.md ✅ · 3-minute demo ✅ (separate from the 60s judging-room cut)

---

## Slide 5 — Roadmap post-hackathon

**Week 1 (post-deadline):** if we win, 1,500 cUSDT funds the first
real-fhEVM port of `lib/hackathon/privacy_mock.py`. Cross-pollinates
directly with the Robinhood London submission.
**Week 2:** publish the skill to the Anthropic skill marketplace +
Cursor's skill registry — same SKILL.md, two distribution channels.
**Month 1:** add a 6th footgun (when one shows up — there will be one).
The skill is versioned; Zama developers `npm i fhevm-skill@latest`.
**Month 3:** instrument the skill — when an LLM session uses it,
emit a telemetry event so we can measure whether the skill *actually*
catches the footguns in the wild. Today we have qualitative confidence;
tomorrow we have data.
**Quarter 2:** publish the *meta-skill*: how to write portable skills.
Sapphire's 14 hermes skills + 17 plugin entries gives us a corpus; the
fhEVM skill is one data point on a much bigger pattern.

**The skill is the asset. The bounty is the distribution event.**

---

**Sources:**
- Zama Mainnet Season 2 launch post: https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier
- fhevm-skill submission thread: https://community.zama.org/t/fhevm-skill-portable-fhevm-skill-for-ai-coding-agents/4405
- Internal: `docs/research/hackathon-strategy/zama-deep-dive.md`
