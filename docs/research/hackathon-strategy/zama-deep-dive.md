# Zama Deep Dive — Programs, Winner Patterns, Sentinel Extensions

**Date:** 2026-05-02
**Author:** Sapphire research lane
**Branch:** `research/zama-deep-dive`
**Audience:** Sapphire core (decision-makers for hackathon dispatch)

---

## Table of Contents

1. [Programs available](#1-programs-available--2026-season-2-live)
2. [Pattern analysis from the winners corpus](#2-pattern-analysis-from-the-winners-corpus)
3. [Sapphire Sentinel-specific recommendations](#3-sapphire-sentinel-specific-recommendations)
4. [New Zama-flavored extensions worth considering](#4-new-zama-flavored-extensions-worth-considering)
5. [Bounty / grant application drafts](#5-bounty--grant-application-drafts)

---

## 1. Programs available — 2026 Season 2 (live)

The headline funding vehicle is **Zama Developer Program — Mainnet Season 2**, announced on the Zama blog and the developer hub. Total prize pool **15,000+ cUSDT** (confidential USDT, ERC-7984, settled on the Zama Protocol). Submission deadline: **May 10, 2026 (23:59 AOE)** for the timed tracks.

Source pages:
- Developer Hub: <https://www.zama.org/developer-hub#developer-program>
- Season 2 launch post: <https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier>
- Community announcement: <https://community.zama.org/t/zama-developer-program-mainnet-season-2-is-live/4379>

### 1.1 Tracks (Season 2)

| Track | Prize pool | Splits | Deadline | Form |
|---|---|---|---|---|
| **Builder** | 7,000 cUSDT | 7 × 1,000 | 2026-05-10 23:59 AOE | <https://forms.zama.org/developer-program-mainnet-season2-builder-track> |
| **Bounty** (AI Agent Skills) | 3,000 cUSDT | 1,500 / 1,000 / 500 | 2026-05-10 23:59 AOE | <https://forms.zama.org/developer-program-mainnet-season2-bounty-track> |
| **APAC × OpenBuild** | 5,000 cUSDT | 5 × 1,000 | 2026-05-10 23:59 AOE | <https://openbuild.xyz/learn/challenges/2095330503> |
| **Developer Bootcamp** | Certificate only | n/a | 4-week cohort, rolling | <https://forms.zama.org/developer-program-mainnet-season2-bootcamp> |
| **Startup Track** | Custom (rolling) | n/a | rolling | <https://forms.zama.org/developer-program-startup-track> |

Deliverables (Builder / APAC): confidential dApp with smart contract + frontend, clear documentation, **3-minute video pitch**, deployed on Sepolia testnet or Ethereum mainnet.

Deliverables (Bounty — AI Agent Skills): production-ready `SKILL.md` covering encrypted types, FHE operations, access control, input proofs, decryption patterns, frontend integration, testing, and anti-patterns. Plus a 3-minute demo video. Evaluation criteria: accuracy, completeness, agent effectiveness, code quality, error prevention. Theme is enabling Claude Code, Cursor, and Windsurf to write confidential smart contracts. (Source: Season 2 launch post, linked above.)

### 1.2 Continuous program: zama-ai/bounty-program

A separate, perpetual GitHub-issue-based bounty stream lives at <https://github.com/zama-ai/bounty-program>. Per-bounty rewards are listed inline on each issue — these target FHE library contributions (TFHE-rs, Concrete, Concrete ML) rather than fhEVM dApps. Worth tracking if our Pi cluster work or `lib.analytics.forecast` ever needs an FHE building-block contribution.

### 1.3 Hackathon partnerships and external sponsorships

OpenBuild APAC Special Track is the only currently-listed external partnership at $5,000. Earlier independent special bounty (also via OpenBuild, $5,000) is documented at <https://community.zama.org/t/zama-developer-program-special-bounty-track/4296>. Outside of OpenBuild, the "Zama at ETHGlobal" sponsorships have historically appeared in event-specific prize stacks but no live event listing was confirmed for the May 2026 cycle as of this writing.

### 1.4 What Zama doesn't have (worth knowing)

- **No standalone Grants page.** Grant-shaped funding flows through the Builder Track (7k) and Startup Track (custom). There is no `zama.org/grants` URL — we should stop describing this as a separate program.
- **No persistent "Champions" benefits page.** The developer hub copy mentions "Premium support & training," "Funding & resources," "Marketing & recognition," "Exclusive opportunities" — but these are program benefits, not a separate Champions tier.

---

## 2. Pattern analysis from the winners corpus

[written next]
