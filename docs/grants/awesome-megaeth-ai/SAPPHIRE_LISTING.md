# awesome-megaeth-ai — Sapphire listing draft

Draft entries for Sapphire to add upstream at
[`megaeth-labs/awesome-megaeth-ai`](https://github.com/megaeth-labs/awesome-megaeth-ai).

Authoring context: Lane M of the MegaETH Mafia 2.0 ecosystem-presence push
(see PR #561 for the full lane plan). The upstream README is the canonical
surface where the MegaETH Foundation team finds non-cohort builders.

**Watchdog status:** docs-only. Single commit with `[skip ci]`.
**Submission:** only Ari can file the upstream PR (his GitHub account).

---

## Schema check (verify before pasting)

The upstream README at the time of this draft has this structure:

```
## AI Coding Skills
   ### General
   ### Payments
   ### DeFi
   ### Identity & Content
   ### Agents
## Developer Tools
## Learning Resources
## Contributing
```

Existing entries are mostly **AI coding skills** (SKILL.md / AGENTS.md
convention — drop-in for Claude Code, Cursor, Windsurf, OpenClaw). Sapphire
isn't packaged as a coding skill — it's a Python access layer + an autonomous
agent. The cleanest fit is two entries: one under **DeFi** (the multi-protocol
SDK) and one under **Agents** (Sentinel). Optionally the SDK could double-list
under **Developer Tools** if the maintainer prefers.

Ari should re-read the live README before pasting in case categories have
shifted.

---

## Section 1 — Listing entries (paste into upstream README)

### Under `### DeFi`

```markdown
- [Sapphire MegaETH SDK](https://github.com/arigatoexpress/Sapphire/tree/main/lib/chains/megaeth) - Typed Python access layer for MegaETH protocols. Covers Aave V3 (lending), Kumbaya DEX (UniV3 fork — quote, swap, liquidity, pools), USDM (peg health + circuit breaker), and GMX V2 perps (funding/OI/price reads). Includes a Blockscout-first ABI auto-fetcher with Sourcify fallback, proxy-aware versioning, recorded mainnet fixtures for deterministic CI, and a unified `protocols` facade. 118 unit tests + 22 ingest tests + live mainnet integration tests against `mainnet.megaeth.com/rpc`. Read-only stable; write paths land fail-closed pending activation gates.
```

### Under `### Agents`

```markdown
- [Sapphire Sentinel](https://github.com/arigatoexpress/Sapphire/tree/main/lib/hackathon) - Agent-safety policy layer with prompt-injection screening, secret-egress detection, mandate/budget enforcement, and multi-chain alpha-source verification. The MegaETH chain-health gate blocks alpha that references a degraded chain (sequencer stall, USDM depeg, Aave oracle drift) even when the agent has accepted the underlying x402 payment. Composes with Aave V3 reads on MegaETH / Arbitrum / Optimism and an FHEVM privacy mock for the encrypted-basket demo path.
```

### Under `## Developer Tools` (optional secondary entry — skip if maintainer pushes back on double-listing)

```markdown
- [Sapphire OS](https://github.com/arigatoexpress/Sapphire) - Multi-chain Python operating system for autonomous trading + research agents. MegaETH integration (chain 4326) ships an ABI auto-fetcher, typed protocol wrappers (Aave V3, Kumbaya, USDM, GMX V2), a real-time block + log streaming service, and a `megaeth_protocols` plugin tool that exposes the access layer to any agent runtime. Live integration tests run against MegaETH mainnet on every push.
```

---

## Section 2 — Fork-and-PR runbook (Ari executes)

1. Visit https://github.com/megaeth-labs/awesome-megaeth-ai
2. Click **Fork** → fork to your account (`arigatoexpress`).
3. In your fork, edit `README.md`:
   - Re-read the section structure (it may have drifted since this draft on
     2026-05-02). Currently the relevant headings are `### DeFi`, `### Agents`,
     and `## Developer Tools`.
   - Paste the entries from Section 1 above into the matching sections,
     keeping alphabetical/logical order with neighbours.
   - If the maintainer's style is one entry per project, drop the optional
     "Sapphire OS" Developer Tools entry and keep only Sentinel + SDK.
4. Commit on a branch:
   ```bash
   git checkout -b add-sapphire-listing
   git add README.md
   git commit -m "Add Sapphire MegaETH SDK + Sentinel"
   git push origin add-sapphire-listing
   ```
5. Open the upstream PR:
   - Title: `Add Sapphire MegaETH SDK + Sentinel`
   - Body (suggested):

     > Adding two MegaETH-touching projects from the Sapphire ecosystem:
     >
     > - **Sapphire MegaETH SDK** (DeFi) — typed Python wrappers for Aave V3, Kumbaya DEX, USDM, and GMX V2 on MegaETH mainnet. ABI auto-fetcher (Blockscout + Sourcify), recorded fixtures for deterministic CI, ~140 tests covering the access layer.
     > - **Sapphire Sentinel** (Agents) — agent-safety policy layer with prompt-injection screening, mandate/budget enforcement, and multi-chain alpha-source verification. The MegaETH chain-health gate blocks alpha that references a degraded chain.
     >
     > Open-source. Live integration tests run against `mainnet.megaeth.com/rpc`.
     > Repo: https://github.com/arigatoexpress/Sapphire
     > Integration overview: https://github.com/arigatoexpress/Sapphire/blob/main/docs/integrations/megaeth.md

6. Drop the upstream PR link back into the Mega Mafia 2.0 application thread
   (PR #566 / Lane M tracker in PR #561).

---

## Verified counts used in this listing

| Claim | Source | Verified? |
|---|---|---|
| Chain ID 4326 | `lib/chains/megaeth/registry.py` | yes |
| 118 unit tests under `tests/lib/chains/megaeth/` | `find tests/lib/chains/megaeth -name 'test_*.py' \| xargs grep -c '^\s*def test_'` (2026-05-02) | yes |
| 22 ingest tests under `tests/services/megaeth_ingest/` | same method | yes |
| Live integration tests in `tests/integration/megaeth/` (Aave V3, Kumbaya, USDM, smoke) | directory listing | yes |
| Protocols covered (Aave V3, Kumbaya, USDM, GMX V2) | `docs/integrations/megaeth-protocol-map.md` §2 + `lib/chains/megaeth/protocols.py` | yes |
| ABI fetcher: Blockscout primary, Sourcify fallback | `docs/integrations/megaeth-protocol-map.md` §4.1 | yes |
| Read-only stable / write paths fail-closed | `docs/integrations/megaeth.md` "What we built" | yes |
| Sentinel features (injection, secret egress, mandate, alpha verification) | `lib/hackathon/sentinel.py` + PRs #546 / #553 / #555 | yes |
| MegaETH chain-health gate | `lib/hackathon/chain_health_gate.py` + PR #546 | yes |

Repo-wide test/tool counts (5,995+ unit / 493 plugin / 109 plugin-tool scripts) were
**not** quoted in the entries themselves — those are repo-level metadata that
would clutter an awesome-list bullet. The MegaETH-specific subset (118 + 22)
is what's load-bearing here, and that's verified above.
