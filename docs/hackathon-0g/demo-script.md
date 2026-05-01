# Demo video script (≤3 min)

Target: ≤3:00. Aim for 2:30 to leave buffer. Record at 1080p, no music.

---

## 0:00 — 0:20 · Hook

> "Most autonomous trading agents are black boxes. The operator says they predicted a move — and you have to trust them. Sapphire integrates 0G Storage, Compute, and Chain so every signal is cryptographically committed *before* the market moves."

**Show on screen:**
- Sapphire dashboard `/showcase` page — open trades, signals, paper portfolio.
- Pull-quote: *"PnL is king. Sortino over Sharpe. Verifiable."*

## 0:20 — 0:40 · The problem

> "When a trading agent claims it predicted BTC at $65,000, three things should be true: the prediction existed before the move, the model that produced it wasn't tampered with, and the inputs weren't backdated. Without 0G, none of those are publicly verifiable."

**Show on screen:**
- Diff between today's signal JSONL (private to operator) and the on-chain anchor (public, immutable).

## 0:40 — 1:30 · The integration (the meat)

> "Here's how Sapphire fixes it. When a signal is generated:"

1. **Sealed Inference (0G Compute / TEE)**
   ```
   $ env | grep OG_COMPUTE
   OG_COMPUTE_BASE_URL=https://provider.0g.ai/v1/proxy
   OG_COMPUTE_API_KEY=app-sk-...
   ```
   Show one inference call with `chat_id` returned. Mention: *"That chatID is signed by a TEE; anyone can re-verify it via the 0G broker."*

2. **0G Storage (envelope + merkle root)**
   ```
   $ echo '{"strategy":"kronos_btc_24h","symbol":"BTC-USD",...}' \
       | python3 plugins/claw-sapphire/tools/og_publish.py
   {"ok": true, "root_hash": "0x...", "anchor": {"signal_id": 42, "tx_hash": "0x...", "explorer_url": "..."}}
   ```
   Show the rootHash printed. Open the explorer URL in a browser tab — the tx is on 0G mainnet.

3. **0G Chain (anchor)**
   Open `https://chainscan.0g.ai/address/<SapphireSignalVerifier addr>` and show the `SignalPublished` event. Click into the tx — point out `proofHash` field on chain matches the Storage rootHash.

4. **Verifier path (the *whole reason*)**
   ```
   $ echo '{"signal_id": 42}' | python3 plugins/claw-sapphire/tools/og_verify.py
   ```
   Show output: blob downloaded from 0G Storage with `verified.merkle_proof: true`. Point out the recovered envelope, including the original prompt + TEE chatID.

## 1:30 — 2:15 · Why it matters

> "This unlocks three things you can't get without 0G:"

1. **Provable strategy edge** — a market maker can prove they predicted a move without revealing the model. The prompt stays sealed inside the TEE; only the rootHash is public.
2. **Front-running mitigation** — the on-chain anchor commits to the signal *before* anyone sees it. Counterparty bots can't peek.
3. **Auditable autonomy** — `SapphireSentinelRegistry` mandates limit how much an agent can spend; every payment receipt is on-chain. A regulator or DAO treasurer can audit the whole agent stack.

**Show on screen:**
- The relevant contract code on screen (`SapphireSignalVerifier.publishSignal`, `SapphireSentinelRegistry.recordPaymentEvaluation`).

## 2:15 — 2:45 · Production reality

> "Sapphire isn't a hackathon prototype. It's a 6,488-test, 50-page-dashboard, live-on-Hyperliquid trading OS. The 0G integration is feature-flagged so the trading critical path keeps running even if 0G goes down. Hackathon-day rule: no flag, no flake."

**Show on screen:**
- `make test` running 5,000+ tests.
- `grep is_enabled` showing the flag check.
- The fire-and-forget hook in `signal_logger.py` (lib/og/hooks.py).

## 2:45 — 3:00 · Close

> "Sapphire on 0G turns autonomous trading from a black box into a glass box. Code at github.com/arigatoexpress/Sapphire, branch feat/0g-integration. Mainnet contract address in the README."

**End screen:**
- Mainnet contract address.
- `#0GHackathon #BuildOn0G` overlay.
- `@0G_labs @HackQuest_` tags.

---

## Recording checklist

- [ ] Quiet room, headphones for audio capture
- [ ] 1080p screen recording (Loom or QuickTime)
- [ ] Hide all unrelated tabs / notifications
- [ ] Browser zoom at 110% so the explorer is readable
- [ ] Run `og_publish` against testnet (NOT mainnet) during the demo to avoid burning live gas
- [ ] Have a real signal pre-published on mainnet to show in the explorer tab
- [ ] Final cut ≤3:00; upload to YouTube unlisted; capture the public link
