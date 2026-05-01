# Operator runbook — 0G hackathon submission

Step-by-step for the parts I cannot do for you. Total wall-clock: **~45 min** if everything's smooth.

> Submission deadline: **2026-05-16, 23:59 UTC+8.** Today: 2026-04-30.

---

## Step 0 · One-time setup (~5 min)

```bash
cd ~/Code/Sapphire
git pull --ff-only origin main          # PR #525 already merged

# Node deps for the 0G Storage bridge — once-per-machine
cd lib/og/_ts && npm install --no-audit --no-fund && cd ../../..

# Verify the SDK loads
OG_RPC_URL=https://evmrpc-testnet.0g.ai \
OG_INDEXER_URL=https://indexer-storage-testnet-turbo.0g.ai \
node lib/og/_ts/og_storage.mjs   # expect: usage error JSON
```

The contract ABIs are already pre-compiled and in `data/chain/*.abi.json` — no need to install solc just to verify.

---

## Step 1 · Testnet wallet + smoke test (~10 min)

You need a hot wallet that holds **0.1+ 0G testnet** for gas. Don't reuse a wallet that holds real funds.

```bash
# 1a. Generate a fresh hot key (or paste an existing one)
python3 -c "from eth_account import Account; a = Account.create(); print('addr:', a.address); print('key:', a.key.hex())"

# 1b. Save the private key (mode 0600) — pick ONE of these
mkdir -p ~/.config/sapphire-secrets
chmod 700 ~/.config/sapphire-secrets
echo '<HEX_KEY_NO_0X_PREFIX>' > ~/.config/sapphire-secrets/og_deploy_key
chmod 600 ~/.config/sapphire-secrets/og_deploy_key
# OR just export
export OG_PRIVATE_KEY=0x<HEX_KEY>

# 1c. Fund from the 0G testnet faucet
#     → see https://docs.0g.ai for the current faucet URL (usually requires a tweet)

# 1d. Run the one-shot smoke test. Deploys + publishes + verifies.
export SAPPHIRE_OG_ENABLED=1
export SAPPHIRE_OG_NETWORK=testnet
bash scripts/hackathon_smoke.sh
```

If the smoke test passes, you've proved the integration end-to-end on testnet. Save the testnet contract addresses from `data/chain/deployments.json`.

**Common failure modes:**
- `cannot connect to 0G RPC` — testnet is down, retry in 5 min.
- `deployer balance ... < 0.1 0G minimum` — faucet wasn't credited yet; check the tx on chainscan-galileo.0g.ai.
- `OG_PRIVATE_KEY must be set` — env didn't propagate to subprocess. Re-export and rerun.

---

## Step 2 · Mainnet deploy + one real signal (~10 min)

This is the gradable artifact. Judges will look at the on-chain activity here.

```bash
# 2a. Fund the wallet on 0G MAINNET. ~0.05 0G is enough (≈$0.10 at current prices).
#     The same wallet from Step 1 is fine if you accept the OPSEC implications.

# 2b. Preflight
export SAPPHIRE_OG_NETWORK=mainnet
python3 scripts/deploy_og_chain.py --check --network mainnet
#   expect 4 [ OK ] lines

# 2c. Deploy
python3 scripts/deploy_og_chain.py --network mainnet
#   contracts land at addresses written to data/chain/deployments.json

# 2d. Publish ONE real signal so the explorer has a SignalPublished event
echo '{
  "strategy": "kronos_btc_24h",
  "symbol": "BTC-USD",
  "action": "buy",
  "score": 83,
  "signal": {"price": 65000, "horizon_h": 24, "source": "hackathon-mainnet-debut"}
}' | python3 plugins/claw-sapphire/tools/og_publish.py

# 2e. Verify it round-trips
echo '{"signal_id": 0}' | python3 plugins/claw-sapphire/tools/og_verify.py
```

Save the **SapphireSignalVerifier mainnet address** and the **publishSignal tx hash**. You'll need both for the submission form.

---

## Step 3 · Update README placeholders (~2 min)

Open [`docs/hackathon-0g/README.md`](README.md) and replace the placeholders:

```diff
-| `SapphireSignalVerifier` | `0x...` | https://chainscan.0g.ai/address/0x... |
+| `SapphireSignalVerifier` | `0xYOUR_ADDR` | https://chainscan.0g.ai/address/0xYOUR_ADDR |
```

(Repeat for the two other contracts. Their addresses are in `data/chain/deployments.json` under `og_mainnet.contracts`.)

```bash
git add docs/hackathon-0g/README.md
git commit -m "docs(0g): pin live mainnet contract addresses for hackathon submission"
git push
```

---

## Step 4 · Demo video (~15 min)

Read [`docs/hackathon-0g/demo-script.md`](demo-script.md) end-to-end first. It's beat-for-beat. Then:

1. Quiet room, headphones for audio.
2. 1080p screen recording (Loom or QuickTime).
3. Hide unrelated tabs / notifications.
4. **Run the smoke flow against TESTNET** during the demo (not mainnet — don't burn live gas on the recording).
5. Have ONE real mainnet tx already in the explorer to point at near the end.
6. Final cut ≤3:00; upload to YouTube **unlisted**; copy the public link.

---

## Step 5 · X post (~3 min)

Open [`docs/hackathon-0g/x-post.md`](x-post.md). Both single-tweet and 2-tweet thread variants are drafted. Replace the placeholders (`youtu.be/...`, the mainnet address). Required tags are already in the draft:

> `#0GHackathon #BuildOn0G @0G_labs @0g_CN @0g_Eco @HackQuest_`

After posting, **save the X URL** — HackQuest needs it.

---

## Step 6 · HackQuest submission (~5 min)

[`docs/hackathon-0g/submission-checklist.md`](submission-checklist.md) has every form field pre-filled. Open the HackQuest submission page and copy-paste from that doc.

After submitting, take a screenshot for your records.

---

## What I left in the repo for you

| Path | Purpose |
|------|---------|
| `lib/og/{config,storage,chain,compute,envelope,hooks}.py` | The Python core of the integration |
| `lib/og/_ts/og_storage.mjs` | Node bridge to the official 0G TS SDK |
| `plugins/claw-sapphire/tools/og_publish.py` | Publish a signal: stdin JSON → on-chain anchor |
| `plugins/claw-sapphire/tools/og_verify.py` | Verify a signal end-to-end (read-only, no key) |
| `scripts/deploy_og_chain.py` | Compile + deploy contracts to 0G testnet/mainnet |
| `scripts/hackathon_smoke.sh` | Single-command end-to-end testnet smoke test |
| `scripts/og_publish_kronos.py` | Anchor today's Kronos predictions on-chain |
| `data/chain/*.abi.json` | Pre-compiled ABIs (no solc required at deploy time) |
| `tests/unit/og_integration/` | 83 unit tests, gated by CI |
| `docs/hackathon-0g/` | All submission materials |

## What I did NOT do (and why)

| Step | Reason |
|------|--------|
| Push to your fork from your account | Already done — branch + PR are pushed to `arigatoexpress/Sapphire` |
| Generate / fund a wallet | Your private key, your funds — never an agent's |
| Deploy contracts to mainnet | Costs real gas, needs your signing |
| Record the demo video | Requires you on screen / on mic for credibility |
| Post on X | Authorship rule + your X account |
| Submit on HackQuest | Authenticated to your account; agreeing to terms is gated by you |

If you want me to script any of these into a single command (e.g. `make hackathon`), say the word.
