# Sapphire OS Hackathon Submissions

Live judge-grade landing page: **[hack.sapphirealpha.xyz](https://hack.sapphirealpha.xyz)**

This directory holds the per-submission video scripts, 5-slide pitch decks,
and criteria-mapping for Sapphire's four 2026 hackathon submissions.

## Submissions

| Hackathon | Status | Deadline | Deck | Video script |
|---|---|---|---|---|
| **0G APAC Hackathon** · Track 2 (Verifiable Finance) | submitted | 2026-05-16 23:59 UTC+8 | [`0g/deck.md`](0g/deck.md) | [`0g/video-script.md`](0g/video-script.md) |
| **MegaETH / Arbitrum** · Multi-chain Sentinel | live | rolling | [`megaeth/deck.md`](megaeth/deck.md) | [`megaeth/video-script.md`](megaeth/video-script.md) |
| **Robinhood London Buildathon** · AI Agentic + Innovation | submitted | 2026-05-25 (start) | [`robinhood/deck.md`](robinhood/deck.md) | [`robinhood/video-script.md`](robinhood/video-script.md) |
| **Zama AI Agent Skills bounty** | draft | 2026-05-10 23:59 | [`zama/deck.md`](zama/deck.md) | [`zama/video-script.md`](zama/video-script.md) |

## What each deck answers (per criterion mapping)

| Slide | Question |
|---|---|
| 1 | The 1-line pitch — what + why now |
| 2 | The technical novelty — what makes it impossible to copy in a weekend |
| 3 | Live demo URL + on-chain contract addresses + GitHub PRs |
| 4 | Sponsor judging criteria, verbatim, with our specific implementation |
| 5 | Roadmap post-hackathon — the integration is the asset, the hackathon is the distribution event |

## What each video script delivers (60-90s)

Each script is property-first (lead with what it proves, not what it does)
with timing markers at `[0:00] [0:05] [0:15] [0:35] [0:50] [0:55]`.
Director's notes cover splice points, fallbacks, and pre-recording
checklists.

## Long-form companions

| Submission | Long-form deep-dive |
|---|---|
| 0G | [`docs/hackathon-0g/demo-script-v2.md`](../hackathon-0g/demo-script-v2.md) — 3-minute property-first walkthrough |
| Robinhood | [`docs/hackathon/london-demo-script.md`](london-demo-script.md) — 90-second deep-dive |
| Zama | [`docs/grants/zama-ai-agent-skills/SUBMISSION.md`](../grants/zama-ai-agent-skills/SUBMISSION.md) — formal bounty submission, 3-minute demo |

## Internal research (the "why" behind each pitch)

| Sponsor | Research |
|---|---|
| 0G | [`docs/research/hackathon-strategy/0g-deep-dive.md`](../research/hackathon-strategy/0g-deep-dive.md) (Lane O) |
| MegaETH | [`docs/research/hackathon-strategy/megaeth-deep-dive.md`](../research/hackathon-strategy/megaeth-deep-dive.md) |
| Robinhood/Arbitrum | [`docs/research/hackathon-strategy/robinhood-arbitrum-deep-dive.md`](../research/hackathon-strategy/robinhood-arbitrum-deep-dive.md) (Lane R) |
| Zama | [`docs/research/hackathon-strategy/zama-deep-dive.md`](../research/hackathon-strategy/zama-deep-dive.md) |

## Criteria-match summary (one-screen overview)

### 0G APAC Hackathon — Track 2 (Verifiable Finance)
**Source:** HackQuest hackathon page · `docs/research/hackathon-strategy/0g-deep-dive.md`

| Criterion | Verbatim | Our match |
|---|---|---|
| 0G Technical Integration Depth & Innovation | "Extent of adoption of 0G components, and innovative solutions to AI / on-chain pain points." | Compute + Storage + Chain — round-trip verifier is the novelty |
| Technical Implementation & Completeness | "Functional integrity, code quality, and mandatory on-chain deployment." | Mainnet 16661 + 56 unit tests + 6,567 repo-wide |
| Product Value & Market Potential | "Market fit, problem-solving capability, user value, and growth roadmap." | $T trading-agent-provability gap; Apollo Accelerator → Guild on 0G |
| User Experience & Demo Quality | "Intuitiveness and user-friendliness of UI/UX; clarity and persuasiveness of pitch and demo." | One-CLI verify; one-page judge view; 60s + 3-min cuts |
| Team Capability & Documentation | "Team background, quality of open-source code and README." | Solo founder; 6 supporting docs in `docs/hackathon-0g/` |

### MegaETH `awesome-megaeth-ai` (rolling)
**Source:** [`CONTRIBUTING.md`](https://github.com/megaeth-labs/awesome-megaeth-ai/blob/main/CONTRIBUTING.md)

| Criterion | Verbatim | Our match |
|---|---|---|
| Active maintenance + docs | "Active maintenance + docs" | 6,567 tests, daily commits, 4 architecture docs |
| Clear value to MegaETH developers | "Clear value to MegaETH developers (chain ID 4326 / 6343)" | First Python wrapper on chain 4326 |
| Open source / publicly accessible API | "Open source or publicly accessible API" | MIT-licensed public repo |

### Arbitrum Open House London Buildathon
**Source:** [Arbitrum Foundation announcement](https://blog.arbitrum.foundation/open-house-london-registration-is-now-open/)

| Category | Prize | Our match |
|---|---|---|
| Open Category | $70K (1st $40K) | Robinhood-Chain-anchored project; reserved spot |
| AI Agentic Category | $15K (Robinhood Chain spot) | Sentinel runs on Robinhood Chain (46630) AND Arbitrum (42161) |
| Robinhood Chain Innovation Award | $30K | Sentinel + Payment Gate deployed on chain 46630; privacy-mock + chain-health twist IS the innovation |

### Zama AI Agent Skills (bounty deadline 2026-05-10)
**Source:** [Zama Mainnet Season 2 launch post](https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier)

| Criterion | Our match |
|---|---|
| Accuracy | All 5 footguns covered with positive + negative examples |
| Completeness | All 8 areas (encrypted types, FHE ops, ACL, input proofs, decryption, frontend, testing, anti-patterns) |
| Agent effectiveness | YAML frontmatter triggers in real Claude Code sessions |
| Code quality | Structured Markdown; positive examples are real working Solidity |
| Error prevention | 10-point pre-write self-check |

## Sources

- [HackQuest 0G APAC Hackathon page](https://www.hackquest.io/hackathons/0G-APAC-Hackathon)
- [Arbitrum Open House London announcement](https://blog.arbitrum.foundation/open-house-london-registration-is-now-open/)
- [Zama Developer Program Mainnet Season 2](https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier)
- [Zama community thread — fhevm-skill bounty](https://community.zama.org/t/fhevm-skill-portable-fhevm-skill-for-ai-coding-agents/4405)
- [MegaETH `awesome-megaeth-ai`](https://github.com/megaeth-labs/awesome-megaeth-ai)
- [Devfolio judging guide](https://guide.devfolio.co/docs/guide/judging)
