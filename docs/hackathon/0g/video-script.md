# Sapphire × 0G — 60-Second Pitch Video Script

**Target:** 60s hard cap, aim for 55s.
**Recording:** 1080p, browser zoom 110%, no music, narrator voice (Ari).
**Hackathon:** 0G APAC Hackathon · Track 2 — Agentic Trading Arena (Verifiable Finance).
**Deadline:** 2026-05-16 23:59 UTC+8.
**Companion:** the 3-minute deep-dive cut at `docs/hackathon-0g/demo-script-v2.md`.

This 60s cut is the judging-room cut. The 3-minute cut is the supplementary
README cut. They share footage; this script is the spine.

---

## [0:00] · Hook (5s)

**Voice:**
> "If a trading agent claims it predicted Bitcoin, three things must be true.
> The prediction existed before the move. The model wasn't tampered with.
> The operator can't backdate the inputs."

**On screen:**
- Black background. Three white text lines fade in word-by-word, one per claim.
- Bottom-right: small "Sapphire OS · 6,567 tests · live execution" badge.

---

## [0:05] · The property (5s)

**Voice:**
> "We make all three cryptographically provable on 0G. Not promised. Provable."

**On screen:**
- Cut to split-screen.
- **Left:** terminal showing `tail -1 data/signals/$(date +%Y-%m-%d).jsonl` (the
  operator-only private signal log, one JSON line scrolls in).
- **Right:** browser at `https://chainscan.0g.ai/address/<verifier addr>` —
  a `SignalPublished` event row visible.
- Pull-quote overlay (lower third): **"Cryptographic commitment. Not trust."**

---

## [0:15] · The integration (20s — three 0G primitives, three quick cuts)

**Voice (one breath per primitive):**
> "Three 0G primitives. 0G Compute — TEE-attested inference. 0G Storage —
> content-addressed signal envelope, merkle rootHash. 0G Chain — signal
> hash anchored on chain sixteen-six-six-one before market impact."

**On screen — three rapid cuts (~6s each):**

1. **0G Compute panel** — terminal command:
   ```
   $ python3 plugins/claw-sapphire/tools/og_publish.py --compute-only
   {"ok": true, "chat_id": "0g-tee-...", "verifiable": true}
   ```
   Yellow box on `verifiable: true`.

2. **0G Storage panel** — terminal command:
   ```
   $ python3 plugins/claw-sapphire/tools/og_publish.py
   {"root_hash": "0xabc123...", "anchor": {"signal_id": 42, ...}}
   ```
   Yellow box on `root_hash`.

3. **0G Chain panel** — browser hits `explorer_url`. `SignalPublished` event
   page renders. Cursor hovers `proofHash` field — visually compare to
   `root_hash` from panel 2. They match.

---

## [0:35] · The verifier round-trip (15s — the closing argument)

**Voice:**
> "Anyone in the world can re-derive the audit trail. og_verify reads chain,
> downloads the blob, re-verifies the merkle proof, re-verifies the TEE
> attestation. Four checks. No trust in Sapphire. Pure cryptography."

**On screen:**

```
$ echo '{"signal_id": 42}' | python3 plugins/claw-sapphire/tools/og_verify.py
{"ok": true,
 "on_chain": {"proof_hash": "0xabc123..."},
 "storage": {"merkle_proof_verified": true},
 "compute": {"attestation_verified": true},
 "envelope": {"strategy": "kronos_btc_24h", "symbol": "BTC-USD", ...},
 "verified": true}
```

- Walk through with yellow highlights, ~3s per check.

---

## [0:50] · Production proof (5s)

**Voice:**
> "Six thousand five hundred sixty-seven tests. Live execution on Hyperliquid
> and Robinhood Crypto. Eleven PRs landed for this one integration."

**On screen:**
- Three large bullets fade in:
  - **6,567 tests passing**
  - **Live capital — Hyperliquid + Robinhood Crypto**
  - **11 PRs · `label:0g-integration`**

---

## [0:55] · End card (5s)

**Voice:**
> "Track Two. Verifiable Finance. Sapphire on 0G."

**On screen (static end card, hold 5s):**

```
github.com/arigatoexpress/Sapphire
hack.sapphirealpha.xyz

SapphireSignalVerifier — chain 16661

#0GHackathon #BuildOn0G
```

---

## Director's notes

- **Property-first over process-first.** Open with what we prove, not what we
  do. (Why: criterion #1, "0G Technical Integration Depth & Innovation" —
  the verbatim wording from HackQuest is "innovative solutions to AI /
  on-chain pain points," not "feature count.")
- **Live mainnet is the killshot.** The real `SignalPublished` event in
  panel 3 is the single highest-information frame. If `publishSignal`
  takes >8s during the take, splice between command and result — never
  burn frames on a spinner.
- **Cut to fit 60s.** If running long, drop the production-proof scene
  from 5s to 3s (just the test count number) and keep the verifier
  round-trip at full length. The verifier round-trip is the criterion-#2
  ("Technical Implementation & Completeness") punchline.
- **End card has the contract address.** Judges will pause on it. Make sure
  it's the real mainnet (chain 16661) verifier address pulled from
  `data/chain/deployments.json`.

---

## Recording sequence

1. Pre-flight day before: run `scripts/hackathon_smoke.sh --network mainnet`
   end-to-end, confirm one real `publishSignal` lands.
2. Pre-publish 1 real signal so panel 3 opens an explorer tab that already
   has a `SignalPublished` row.
3. Record take 1 of all 6 segments back to back.
4. Watch take 1. If any segment fluffs, re-record that segment only.
5. Record take 2 of full 60s as backup.
6. Edit, splice, add overlays.
7. Final cut ≤60s. Upload to YouTube unlisted. Capture URL → HackQuest form.
