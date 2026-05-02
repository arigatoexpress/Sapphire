# Zama Bounty — AI Agent Skills Submission

> Status: scaffold. Ari to review SKILL.md content + finalize this memo before submitting.
> Deadline: **2026-05-10 23:59 AOE**. First-prize reward: **1,500 cUSDT**.

## Project

**Name:** `write-fhevm-contracts` (Anthropic skill format)

**One-line description (≤30 words):** A Claude / Cursor / Windsurf skill that teaches LLMs to write fhEVM contracts correctly the first time — covers the 5 silent-failure footguns and ships a 10-point self-check.

## How the SKILL was built

Sapphire OS (the project this skill ships from) already runs **14 hermes skills** in production for its Telegram agent (`~/.hermes/skills/sapphire/`) and exposes a **109-tool plugin registry** (`infra/tool-registry.yaml`) for its claw-code agent runtime. Skill-as-data is core infrastructure for us — we eat the format every day.

The `write-fhevm-contracts` skill is built the same way our internal trading-brain, threat-intel, and tho-operations skills are: terse YAML frontmatter for trigger discovery, body sections that load only when the trigger fires, and a self-check appendix the model is told to run before returning.

## How to install / use

### Anthropic Claude Code
```bash
mkdir -p ~/.claude/skills
cp docs/grants/zama-ai-agent-skills/SKILL.md ~/.claude/skills/write-fhevm-contracts.md
```
Claude Code surfaces it automatically when the user mentions FHE / fhEVM / `@fhevm/solidity` / `@zama-fhe/relayer-sdk`.

### Cursor / Windsurf
Drop the same file into the project's `.cursor/rules/` or `.windsurf/rules/` directory. Both editors honor the YAML frontmatter trigger description for selective loading.

### Generic LLM (any model with a system prompt)
Concatenate the SKILL body into the system prompt with the heading "When the user asks about fhEVM, follow this skill exactly:".

## Demo: rebuild `SapphireSentinelBasket.sol` from scratch

The demo contract is a confidential portfolio-basket aggregator: users deposit encrypted weights (basis points, `euint16`), the contract sums them into an `euint32` aggregate, and only the basket owner can decrypt the total to confirm it equals 10000 bp.

The full transcript is in [`EXAMPLE_REBUILD.md`](./EXAMPLE_REBUILD.md). Decision points where the SKILL guides the LLM:

1. **Type choice** — LLM proposes `euint256` for weights; SKILL section 1 nudges to `euint16` (basis points fit in 0–10 000).
2. **Inheritance** — LLM imports `FHE` but forgets `ZamaEthereumConfig`; SKILL footgun 5 catches it.
3. **Input handling** — LLM accepts `euint16` directly from the user; SKILL footgun 3 forces the `(externalEuint16, bytes inputProof)` + `FHE.fromExternal` pattern.
4. **ACL grants** — LLM returns the aggregate handle without `FHE.allow`; SKILL footgun 2 + self-check item 4 catch it.
5. **Reveal flow** — LLM writes a synchronous `FHE.decrypt`; SKILL footgun 4 forces the request/callback split.
6. **Self-check** — LLM runs the 10-item checklist before returning; catches a missing `FHE.allowThis` on the running aggregate.

## Test plan — three example prompts that exercise the SKILL

1. **"Write a confidential vote contract where each voter submits an encrypted ballot (yes/no) and only the final tally is revealed once voting closes."**
   - Should trigger the skill (mentions "encrypted").
   - Expected behavior: `ebool` per ballot, running `euint32` tally, `FHE.requestDecryption` on close, callback verifies `msg.sender == FHE.gateway()`.
2. **"Review this fhEVM contract for ACL bugs"** + paste a contract that calls `FHE.add` then returns the handle without any `FHE.allow`.
   - Should trigger on "fhEVM".
   - Expected behavior: flag footgun 2 specifically; suggest `FHE.allowThis(result)` + `FHE.allow(result, msg.sender)`.
3. **"Port this plaintext counter to encrypted state"** + paste a 20-line `Counter.sol`.
   - Should trigger on "encrypted state".
   - Expected behavior: introduce `euint32` storage, replace `+=` with `FHE.add`, add `ZamaEthereumConfig` inheritance, restructure `getCount()` as request-decryption + callback.

If all three prompts produce contracts that pass the SKILL's own 10-item self-check, the skill is working.

## Why we win

- **Dogfooding.** Sapphire ships 14 hermes skills + 109 plugin tools using the exact same skill format internally. We're not guessing what works — this is the format we already trust to drive a Telegram trading bot in production.
- **Production-credibility.** Sapphire OS is a real autonomous trading + intelligence stack (5 chains, 50 dashboard pages, 6,488 tests). When we say "the LLM also needs `FHE.allowThis`," it's because we actually wrote and tested a Sentinel basket contract that broke without it (`lib/hackathon/privacy_mock.py` is the Python-side mirror of the same shape).
- **Open-source signal.** The SKILL ships in our public monorepo (`arigatoexpress/Sapphire` → `docs/grants/zama-ai-agent-skills/`). Anyone can fork, extend, and submit improvements via PR — the skill itself is a living artifact, not a one-shot deliverable.

## Files in this submission

- [`SKILL.md`](./SKILL.md) — the skill artifact (233 LOC, 10-item self-check)
- [`SUBMISSION.md`](./SUBMISSION.md) — this memo
- [`EXAMPLE_REBUILD.md`](./EXAMPLE_REBUILD.md) — illustrative LLM transcript

## Open items for Ari before submission

- [ ] Polish SKILL.md sections 3 (canonical patterns) and 4 (FHE-vs-alternatives decision tree) — currently TODOs
- [ ] Replace EXAMPLE_REBUILD with an actual Claude Code transcript (current is illustrative)
- [ ] Drop the SKILL into Claude Code locally and verify trigger fires on the three test prompts
- [ ] Confirm the contract examples compile against the latest `@fhevm/solidity` version
- [ ] Write Solidity for the three canonical patterns in section 3
- [ ] Decide whether to also publish the SKILL as a standalone repo (better discoverability for the bounty judges)
