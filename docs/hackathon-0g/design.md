# Sapphire × 0G — Verifiable Autonomous Trading on the AI L1

**Hackathon:** 0G APAC Hackathon (Mar–May 2026)
**Track:** 2 — Agentic Trading Arena (Verifiable Finance), with Track 1 crossover
**Submission deadline:** 2026-05-16

## TL;DR

Sapphire is a production-grade autonomous trading + intelligence OS (6,488+ tests, 50 dashboard pages, 7 quant strategies, live Hyperliquid + Robinhood Crypto execution). For the 0G hackathon we add a **cryptographic settlement layer** on top:

1. Every trading signal is generated through a **TEE-attested 0G Compute** inference call.
2. The signed signal blob (input + reasoning + output + TEE attestation) is uploaded to **0G Storage**, returning a content-addressed merkle `rootHash`.
3. The `rootHash` is anchored on **0G Chain** via `SapphireSignalVerifier.publishSignal(...)`, producing an immutable, timestamped, on-chain commitment to the prediction.
4. Anyone — counterparty, auditor, regulator, judge — can later fetch the on-chain signal, download the blob from 0G Storage, verify the merkle proof, and re-verify the TEE attestation.

This gives Sapphire **verifiable finance**: a strategy can prove it predicted a move *before* the market priced it, without leaking the model or prompt.

## Why this matters for Track 2

Track 2 explicitly calls out: *"We specifically support the use of Sealed Inference and TEE-based execution to ensure execution privacy and mitigate front-running, creating a more secure environment for proprietary trading strategies."*

Sapphire's existing inference proxy (`services/inference-proxy/`) and signal pipeline (`services/alpha/`) already produce a stream of trading signals from a 4-tier LLM stack. Today those signals exist only in private JSONL — they have no provenance to anyone outside the operator. With 0G integration:

- **Sealed Inference** removes the operator's ability to retroactively rewrite history.
- **0G Storage** provides cheap, content-addressed blob storage for the full reasoning trace.
- **0G Chain anchoring** turns each signal into a publicly-verifiable claim with a wall-clock timestamp.
- **Front-running mitigation**: the `proofHash` on chain commits to the full prediction *before* it's revealed; only the on-chain entry is public until the operator chooses to disclose the underlying blob (via 0G Storage rootHash).

## Architecture

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │                       Sapphire trading critical path                │
   │                                                                     │
   │   TradingView webhook  ─►  signal_logger  ─►  paper_trader / Hyper  │
   │           │                     │                                   │
   │           │              [SAPPHIRE_OG_ENABLED=1]                    │
   │           │                     │                                   │
   │           ▼                     ▼                                   │
   │   ┌──────────────┐      ┌──────────────────────┐                    │
   │   │ 0G Compute   │ ───► │  signal blob         │                    │
   │   │ (TEE-sealed) │      │  {input, reasoning,  │                    │
   │   │              │      │   output, TEE attn}  │                    │
   │   └──────────────┘      └──────────┬───────────┘                    │
   │                                    │                                │
   │                                    ▼                                │
   │                         ┌────────────────────┐                      │
   │                         │  0G Storage        │                      │
   │                         │  (content-addressed)│                     │
   │                         └──────────┬─────────┘                      │
   │                                    │ rootHash                       │
   │                                    ▼                                │
   │                         ┌────────────────────────────┐              │
   │                         │ SapphireSignalVerifier     │              │
   │                         │   .publishSignal(          │              │
   │                         │     strategyId, symbol,    │              │
   │                         │     direction, confidence, │              │
   │                         │     proofHash=rootHash)    │              │
   │                         │ on 0G Chain (16661)        │              │
   │                         └────────────────────────────┘              │
   └─────────────────────────────────────────────────────────────────────┘
```

## 0G components used

| Component | How Sapphire uses it |
|-----------|----------------------|
| **0G Storage** | Persists signal blobs, Kronos prediction outputs, daily intelligence briefs as content-addressed objects. Returns merkle `rootHash` that we anchor on-chain. |
| **0G Compute** | Runs the inference step that produces a trading signal under a TEE-attested provider. Returns a `chatID` we keep alongside the signal blob; verifiable later via `broker.inference.processResponse()`. |
| **0G Chain (mainnet, chainId 16661)** | Hosts `SapphireSignalVerifier`, `SapphirePaymentGate`, `SapphireSentinelRegistry`. Every signal has an on-chain commitment; payment access and agent mandates anchor here too. |
| **Sealed Inference / TEE** | The signal-generation prompt and the model output are sealed inside the TEE — operator cannot rewrite history. Front-running window is closed: by the time anyone learns the signal exists on-chain, the prediction is already committed. |
| *(Optional)* **0G Agent ID** | Each Sapphire agent (signal-logger, kronos-daily, hermes-agent) registers an Agent ID for identity-bound action attribution. |

## Component map (new code in this PR)

| Path | Purpose |
|------|---------|
| `lib/og/__init__.py`, `lib/og/config.py` | Endpoint + chain-id constants for 0G testnet (16602) and mainnet (16661). |
| `lib/og/storage.py` | Python facade for 0G Storage upload/download. Subprocesses a small Node helper (`lib/og/_ts/og_storage.mjs`) that calls the official `@0gfoundation/0g-ts-sdk`. |
| `lib/og/chain.py` | web3.py client targeting 0G Chain. Wraps `SapphireSignalVerifier.publishSignal(...)`. |
| `lib/og/compute.py` | OpenAI-compatible client that points at a 0G Compute provider proxy; carries `chatID` for TEE attestation verification. |
| `lib/og/_ts/og_storage.mjs` | Node helper invoked by `lib/og/storage.py` over stdio. JSON in/out. |
| `lib/og/_ts/package.json` | Pins `@0gfoundation/0g-ts-sdk` + `ethers`. |
| `scripts/deploy_og_chain.py` | Adapted from `deploy_robinhood_chain.py`; supports `--testnet` and `--mainnet`. |
| `plugins/claw-sapphire/tools/og_publish.py` | stdin-JSON tool: `{signal: {...}}` → uploads to 0G Storage + anchors on chain. |
| `plugins/claw-sapphire/tools/og_verify.py` | stdin-JSON tool: `{signal_id}` or `{root_hash}` → fetches blob, verifies merkle proof, re-checks TEE attestation. |
| `tests/unit/og_integration/` | Mocked-SDK tests. |
| `services/alpha/src/signal_logger.py` (modified) | Optional `og_publish` hook gated by `SAPPHIRE_OG_ENABLED=1`. Fire-and-forget so the trading critical path is unaffected if 0G is degraded. |
| `scripts/og_publish_kronos.py` | Anchors today's Kronos predictions on-chain — one signal per watchlist asset. Designed to be invoked by a follow-on scheduled task after `kronos-daily` completes. |
| `scripts/hackathon_smoke.sh` | Single-command end-to-end smoke test against 0G testnet (preflight → deploy → publish → verify). |

## Safety / blast-radius

- **All 0G code is gated behind `SAPPHIRE_OG_ENABLED=1`.** When unset (default), Sapphire's trading critical path is byte-identical to today.
- **No private keys ever cross the Python ↔ Node boundary in plain text.** Node helper reads `OG_PRIVATE_KEY` from its own process env, set by `lib/og/storage.py` for the subprocess only.
- **0G publish is fire-and-forget** in the live signal path. A failed publish logs to `data/system_events.jsonl` but does not delay or block trade execution.
- **Mainnet deploy is two-step**: `--check` (read-only preflight) then `--deploy --network mainnet`, identical to the Robinhood Chain pattern that's already in production.
- **Existing contracts are reused unchanged.** The `proofHash` field on `SapphireSignalVerifier` was already designed for "future zk-verifiable computation" — we repurpose it to carry the 0G Storage `rootHash`. No new contracts required for Track 2 baseline.

## Submission deliverables checklist

- [ ] **0G mainnet contract address** — `SapphireSignalVerifier` deployed on chainId 16661
- [ ] **0G Explorer link** — `https://chainscan.0g.ai/address/<addr>` showing publishSignal txs
- [ ] **0G integration proof** — Storage rootHash + Chain anchor + Compute TEE attestation
- [ ] **Public GitHub repo** — feature branch merged to main, hackathon README at root pointer
- [ ] **Demo video** (≤3 min) — see `docs/hackathon-0g/demo-script.md`
- [ ] **Hackathon README** — `docs/hackathon-0g/README.md` (architecture, repro steps, faucet/test-account notes)
- [ ] **X post** with `#0GHackathon #BuildOn0G @0G_labs @0g_CN @0g_Eco @HackQuest_`
- [ ] **HackQuest submission** — title, 30-word description, links

## Out of scope (intentionally)

- We do not migrate Sapphire's primary state store away from local JSONL/Redis. 0G Storage is an additive **public** layer for proofs, not a replacement for hot operational state.
- We do not move live trading execution to 0G. Live execution stays on Hyperliquid / Robinhood / paper. 0G is the **settlement and proof** layer.
- We do not fine-tune models on 0G Compute in this iteration. Inference only. Fine-tuning is a v2 follow-up if time allows.
