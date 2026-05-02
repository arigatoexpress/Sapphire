# 0G APAC Hackathon — Demo Recording Script v2

**Target:** ≤3:00 total. Aim for 2:30 to leave buffer.
**Recording:** 1080p (1920x1080), no music, browser zoom 110% so explorer
addresses are readable, hide all unrelated tabs/notifications.
**Supersedes:** `docs/hackathon-0g/demo-script.md` (the v1 was a process
walkthrough; this v2 is a property-first pitch informed by Lane O's research
in `docs/research/hackathon-strategy/0g-deep-dive.md`).

---

## Director's overall notes (read once before recording)

- **Property-first framing.** Every scene leads with a guarantee, then shows
  the mechanism. Judges grading criterion #1 (0G Integration Depth) score
  *what each component proves*, not what each component does.
- **Live mainnet is mandatory.** Lane O's analysis: "winners consistently demo
  mainnet activity, not testnet promises." If `og_publish` lands a real
  `SignalPublished` event on chain 16661 during the recording, that is the
  single highest-value frame in the video.
- **Splice tolerance.** If `og_publish` takes >10s, splice it out — show the
  command going in, cut to the result. Don't burn 15s on a spinner.
- **Backup take.** Always record the entire 3 minutes twice. If take 1 has a
  network hiccup mid-`og_verify`, take 2 is your safety net.
- **Pull-quotes.** When a pull-quote is on screen, it stays for the entire
  scene — viewers should be able to pause and read it.

---

## 0:00 — 0:20 · Hook (property-first)

**Words to say (verbatim):**

> "When a trading agent claims it predicted BTC at sixty-five thousand,
> three properties must be true: the prediction existed before the move,
> the model that produced it wasn't tampered with, and the operator can't
> backdate the inputs. Sapphire on 0G makes all three properties
> cryptographically provable. Not promised. Provable."

**On screen:**

- Split-screen, 50/50.
- **Left half:** terminal showing `tail -1 data/signals/$(date +%Y-%m-%d).jsonl`
  — the operator-only private signal log, a single JSON line scrolls in.
- **Right half:** browser showing
  `https://chainscan.0g.ai/address/<SapphireSignalVerifier addr>` — the
  public on-chain anchor, with a `SignalPublished` event row visible.
- Pull-quote overlay (lower third, sans-serif, white-on-translucent-black):
  **"Cryptographic commitment. Not trust."**
- Bottom-right corner: small "6,567+ tests · live execution" badge.

**Commands to run / actions:**

- Pre-arrange the split-screen window layout before recording.
- Pre-warm the browser tab so the explorer renders instantly.

**Approximate duration:** 20s

**Director's note:** Don't speak over the moment the on-chain entry first
appears on the right half — let it land for one full beat before continuing.

---

## 0:20 — 1:00 · The integration (the meat — three 0G primitives in three panels)

**Words to say (verbatim, panel by panel):**

> "Three 0G primitives work together. First: 0G Compute. Inference happens
> inside a Trusted Execution Environment. The provider returns a chatID
> anyone can later verify against the enclave key."

> "Second: 0G Storage. The full signal envelope — input, reasoning, output,
> TEE attestation — gets uploaded and content-addressed. Notice the
> rootHash: that's a merkle commitment. Tamper one byte and the hash
> changes."

> "Third: 0G Chain. The rootHash is anchored on chain sixteen-six-six-one
> via SapphireSignalVerifier dot publishSignal. Public timestamp.
> Immutable. Published before anyone sees the signal."

**On screen (panel A — 0G Compute, ~13s):**

```
$ env | grep OG_COMPUTE
OG_COMPUTE_BASE_URL=https://provider.0g.ai/v1/proxy
OG_COMPUTE_API_KEY=app-sk-...
$ echo '{"prompt":"BTC 24h forecast","model":"glm-5"}' \
    | python3 plugins/claw-sapphire/tools/og_publish.py --compute-only
{"ok": true, "chat_id": "0g-tee-...", "provider": "0x...", "verifiable": true}
```

Highlight `chat_id` and `verifiable: true` with a yellow box overlay.

**On screen (panel B — 0G Storage, ~13s):**

```
$ echo '{"strategy":"kronos_btc_24h","symbol":"BTC-USD",...}' \
    | python3 plugins/claw-sapphire/tools/og_publish.py
{"ok": true,
 "root_hash": "0xabc123...",
 "anchor": {"signal_id": 42, "tx_hash": "0xdef456...",
            "explorer_url": "https://chainscan.0g.ai/tx/0xdef456..."}}
```

Highlight `root_hash` with a yellow box.

**On screen (panel C — 0G Chain, ~14s):**

- Open the `explorer_url` from panel B in a new browser tab.
- The tx page loads showing the `SignalPublished` event with fields:
  `strategyId`, `symbol`, `direction`, `confidence`, `proofHash`.
- Mouse-hover `proofHash` and visually compare it to the `root_hash` from
  panel B — they match.

**Commands to run:**

1. `env | grep OG_COMPUTE` (panel A header)
2. `python3 plugins/claw-sapphire/tools/og_publish.py --compute-only`
   (one-shot TEE call, returns chatID)
3. `python3 plugins/claw-sapphire/tools/og_publish.py` (the full pipeline:
   Compute → Storage → Chain)
4. Click into the explorer URL in the browser

**Approximate duration:** 40s

**Director's note:**
- If `og_publish` (the full pipeline) takes >10s end-to-end, splice between
  the command line going in and the JSON result coming out.
- Pre-fund the wallet at `OG_DEPLOY_KEY_PATH` before recording — if
  `publishSignal` reverts on insufficient gas mid-take, restart.
- The hash-match comparison in panel C is the visual punchline of the meat
  segment. Make sure both the browser explorer view and a terminal-side
  `root_hash` are visible at the same time for at least 2 seconds.

---

## 1:00 — 2:00 · Verifier round-trip (the *whole* reason — close the loop)

**Words to say (verbatim):**

> "Writing to chain isn't enough. Anyone in the world has to be able to
> re-derive the audit trail. Watch."

> "og_verify reads the on-chain entry. Downloads the blob from 0G Storage.
> Re-verifies the merkle proof. Re-verifies the TEE attestation. Four
> independent checks. No trust in Sapphire. No trust in 0G as a black box.
> Just cryptography."

**On screen (~60s):**

```
$ echo '{"signal_id": 42}' | python3 plugins/claw-sapphire/tools/og_verify.py
{"ok": true,
 "on_chain": {"signal_id": 42, "tx_hash": "0xdef456...",
              "block": 28341922, "proof_hash": "0xabc123..."},
 "storage": {"downloaded": true, "size_bytes": 2841,
             "merkle_proof_verified": true},
 "compute": {"chat_id": "0g-tee-...", "attestation_verified": true},
 "envelope": {"strategy": "kronos_btc_24h",
              "symbol": "BTC-USD", "direction": "long",
              "confidence": 0.74, "prompt_preview": "BTC 24h forecast..."},
 "verified": true}
```

- After the JSON appears, walk through it field by field with the cursor or
  a yellow highlight overlay:
  1. `on_chain.proof_hash` ← step 1 (read chain)
  2. `storage.merkle_proof_verified: true` ← step 2 (storage round-trip)
  3. `compute.attestation_verified: true` ← step 3 (TEE re-verification)
  4. `envelope.prompt_preview` ← step 4 (we got the original input back)
- Final overlay (lower third): **"Anyone. Anywhere. Re-derives the proof."**

**Commands to run:**

```
echo '{"signal_id": 42}' | python3 plugins/claw-sapphire/tools/og_verify.py
```

**Approximate duration:** 60s

**Director's note:** This is the segment that decides whether judges score
this submission as "infrastructure that does what it says" vs. "another
signal generator with a hash field." Take it slowly. Let each highlighted
field linger for 2 full seconds. If the recording feels rushed, splice in a
1-2 second pause before each highlight.

---

## 2:00 — 2:30 · Production-grade signals (the close)

**Words to say (verbatim):**

> "Sapphire isn't a hackathon prototype. Six thousand five hundred sixty-seven
> tests passing. Live execution on Hyperliquid and Robinhood Crypto.
> Eleven pull requests landed for the 0G integration alone. The integration
> is feature-flagged so the trading critical path keeps running even if 0G
> goes down. Hackathon-day rule: no flag, no flake."

> "Apollo Accelerator and Guild on 0G are the next milestones. The integration
> is the asset. The hackathon is the distribution event."

**On screen (large readable bullets, one per ~5s):**

- **6,567 tests** (with a cmd preview: `pytest tests/unit/ -q`)
- **Live execution** — small live capital on Hyperliquid + Robinhood Crypto
  (show one open position from `/api/portfolio`, redact size)
- **11 PRs landed** for the 0G integration (show the GitHub PR list filtered
  by `label:0g-integration`)
- **Apollo Accelerator + Guild on 0G** — next milestone

**Commands to run:**

- Pre-stage a paper-trade or live-trade screenshot — don't try to fetch live
  data during the recording.
- Pre-stage the GitHub PR list URL.

**Approximate duration:** 30s

**Director's note:** Don't actually run `pytest` — it takes too long. Show
the command, freeze on the `5995 passed` summary line. If the live position
size is sensitive, blur or redact the dollar amount; the *fact* of live
execution is the signal, not the size.

---

## 2:30 — 3:00 · Outro buffer

**Words to say (verbatim):**

> "Code at github.com/arigatoexpress/Sapphire, branch feat/0g-integration.
> Mainnet contract addresses in the README. Hashtag BuildOn0G."

**On screen (end card, hold for full 30s if take has run long, else cut at 2:45):**

```
github.com/arigatoexpress/Sapphire

SapphireSignalVerifier   0x...  (chain 16661)
SapphirePaymentGate      0x...
SapphireSentinelRegistry 0x...

#0GHackathon #BuildOn0G
@0G_labs @0g_CN @0g_Eco @HackQuest_
```

**Commands to run:** none — static end card.

**Approximate duration:** 0–30s buffer (cut to fit ≤3:00 total).

**Director's note:** This buffer absorbs over-runs from earlier scenes. If
the verifier round-trip ran 70s instead of 60s, drop the outro to 20s. The
hard ceiling is 3:00 — if any take exceeds that, re-cut.

---

## Recording sequence (do these in order)

1. Pre-flight: run `scripts/hackathon_smoke.sh --network mainnet` once
   end-to-end the day before — make sure deploy + publish + verify all work
   against the live network with the wallet you'll use during recording.
2. Pre-publish 1 real signal on mainnet so panel C in the meat segment can
   open an explorer tab that already has a `SignalPublished` row.
3. Record take 1 of all 5 segments back to back.
4. Watch take 1 in full. If any segment has a network hiccup, an audio
   stumble, or runs over its time budget, re-record that segment only.
5. Record take 2 of the full 3 minutes as backup — even if take 1 looked
   clean. (Networks are fickle.)
6. Edit, splice (where the director's notes flag splices), add overlays.
7. Final cut ≤3:00. Upload to YouTube unlisted. Capture the public URL.
8. Drop URL into the HackQuest submission form.
