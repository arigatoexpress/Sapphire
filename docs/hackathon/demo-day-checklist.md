# Hackathon Demo Day — Pre-Recording Checklist

This is the operator checklist for the day-of (or day-before) of recording
the 0G APAC and Arbitrum London Buildathon demo videos. It is meant to be
read top to bottom and ticked off in order. Total time-on-task: ~60-90
minutes if everything is already wired; up to 4 hours if you discover a
broken faucet or missing wallet balance.

**Companion docs:**
- `docs/hackathon-0g/demo-script-v2.md` — 0G APAC demo (≤3 min)
- `docs/hackathon/london-demo-script.md` — London Buildathon demo (≤90s)

---

## 1 · Wallets and funding

### 0G APAC (mainnet, chain 16661)

- [ ] **Mainnet deploy wallet** (`OG_DEPLOY_KEY_PATH`) is funded with
      enough native 0G token to deploy `SapphireSignalVerifier` +
      `SapphirePaymentGate` + `SapphireSentinelRegistry` AND publish at
      least 5 signals. Check balance:
      `cast balance --rpc-url <0G mainnet RPC> <addr>`
- [ ] Backup wallet (second funded key) ready in case primary nonces get
      tangled.
- [ ] Wallet keystore file is mode `0600` and lives at the path expected
      by `scripts/hackathon_smoke.sh` (default
      `~/.config/sapphire-secrets/og_deploy_key`).

### London Buildathon (Robinhood Chain testnet, chain 46630)

- [ ] **Testnet deploy wallet** funded via the official faucet at
      `https://faucet.testnet.chain.robinhood.com/`.
- [ ] **Backup wallet 1** funded via Chainlink Faucets mirror at
      `https://faucets.chain.link/robinhood-testnet`.
- [ ] **Backup wallet 2** funded via QuickNode Multi-Chain Faucet mirror
      at `https://faucet.quicknode.com/robinhood/testnet`.
- [ ] All three wallets have at least one Stock Token of each type
      (TSLA/AMZN/PLTR/NFLX/AMD) — the official faucet drops 5 of each
      per request, so one faucet pull per wallet covers it.
- [ ] All three wallet addresses recorded in
      `data/hackathon/wallets.json` (gitignored) so you can rotate
      between them mid-recording if a tx stalls.

### Live trading capital (only if showing it on screen)

- [ ] Hyperliquid live executor: confirm `HYPERLIQUID_TRADING_ENABLED`
      is set to its current operator value; do NOT change it for the
      demo. Demo screenshots only.
- [ ] Robinhood Crypto: confirm at least one open position exists for
      the production-grade signals scene; capture screenshot
      pre-recording (do not call live API on camera).

---

## 2 · Smoke test ran clean

Run the full smoke pipeline at least once, end-to-end, against each
target chain, the day before recording.

### 0G mainnet

- [ ] `bash scripts/hackathon_smoke.sh --network mainnet` exits 0
- [ ] Resulting `data/hackathon/submission_artifacts.md` has populated
      contract addresses + at least one explorer URL with a
      `SignalPublished` event visible
- [ ] `python3 plugins/claw-sapphire/tools/og_verify.py` round-trip
      against the just-published signal returns `verified: true`

### Robinhood Chain testnet

- [ ] `bash scripts/hackathon_smoke.sh --network testnet` exits 0
      (note: the smoke script's primary path targets 0G; Robinhood
      Chain deploys go through `scripts/deploy_robinhood_chain.py`
      separately — see `docs/hackathon/sapphire-sentinel-london-2026.md`
      step 2)
- [ ] `SapphireSentinelRegistry` is deployed; the address is recorded
      in `data/chain/deployments.json`
- [ ] At least one prior `recordPaymentEvaluation` tx is visible in
      the Blockscout explorer at
      `https://explorer.testnet.chain.robinhood.com/address/<addr>`

### Both env toggles tested

- [ ] `SENTINEL_DEMO_FORCE_INJECTION=1` only, click evaluate on
      `/chain/sentinel`, confirm `prompt_injection` AND
      `secret_egress_risk` both appear in the reason stack
- [ ] `SENTINEL_DEMO_FORCE_DEPEG=1` only, click evaluate, confirm
      `chain_state_degraded` AND `peg_divergence_bps=500` appear
- [ ] BOTH env toggles set, click evaluate, confirm all three risk
      flags stack in the order: `prompt_injection`,
      `secret_egress_risk`, `chain_state_degraded`

---

## 3 · Local services

- [ ] Dashboard is up at `http://localhost:8080` and responsive
      (latency <500ms on a refresh)
- [ ] Auth is set: `AUTH_PASSWORD=sapphire` in the dashboard process's
      environment (without it, the dashboard crashes on import per
      CLAUDE.md "Gotchas")
- [ ] For the London demo, restart the dashboard with both demo env
      vars set:
      ```
      SENTINEL_DEMO_FORCE_INJECTION=1 \
      SENTINEL_DEMO_FORCE_DEPEG=1 \
      AUTH_PASSWORD=sapphire \
      python3 services/dashboard/app.py
      ```
- [ ] `/chain/sentinel` page renders without console errors (open
      browser devtools, refresh, check console)
- [ ] `/api/hackathon/sentinel/evaluate` returns 200 to a manual
      `curl -X POST` test
- [ ] (0G demo only) `og_publish` and `og_verify` plugin tools both
      run without errors against the chosen network
- [ ] Inference proxy at `:11435` is up if any scene shows live
      inference (the meat segment of the 0G demo does not strictly
      require this — `og_publish --compute-only` calls 0G Compute
      directly)

---

## 4 · Browser + recording setup

- [ ] Browser zoom set to **110%** so explorer addresses, hash fields,
      and policy reasons are readable at 1080p
- [ ] All unrelated browser tabs closed
- [ ] Browser notifications disabled (`Settings → Notifications → Off`)
      — Slack, Linear, Telegram, Mail web all silenced
- [ ] OS notifications disabled (macOS: Focus → Do Not Disturb)
- [ ] Pre-warm tabs that will be opened during the demo so they render
      instantly when clicked:
  - `https://chainscan.0g.ai/address/<SapphireSignalVerifier addr>`
    (0G demo)
  - `https://explorer.testnet.chain.robinhood.com/address/<SapphireSentinelRegistry addr>`
    (London demo)
  - `https://explorer.testnet.chain.robinhood.com/tx/<recent tx hash>`
    (London demo, fallback if a fresh tx is still confirming)

### Recording tool

- [ ] Tested OBS / QuickTime / Loom (whichever you're using) on a
      throwaway 30-second clip — confirm:
  - Audio is being captured (talk during the test, play back, hear it)
  - Resolution is 1920x1080
  - Cursor capture is on (so the on-screen cursor is visible)
  - Frame rate is 30fps minimum
- [ ] Microphone level is set such that normal speech peaks at -12dB to
      -6dB (not clipping at 0dB)
- [ ] Quiet room. Headphones for monitoring if possible. AC/HVAC noise
      check (sometimes you don't notice until playback)

---

## 5 · Backup recording

- [ ] After take 1, immediately record take 2 of the full demo even if
      take 1 looked clean. Networks are fickle; on-camera one-take
      heroics are not how this gets done.
- [ ] Save both takes to disk before doing any editing — never
      overwrite take 1 with take 2 at the file-system level.

---

## 6 · Post-recording

- [ ] Edit the cleaner of the two takes (or splice the best segments
      from both per the director's notes in each script)
- [ ] Add overlays, pull-quotes, and end card
- [ ] Final length check: 0G demo ≤3:00, London demo ≤90s. If over,
      cut from the segments flagged in each script's director's notes
      (0G: outro buffer; London: multi-chain proof scene)
- [ ] Export at 1080p, .mp4, h.264 codec, ~5-10 Mbps bitrate
- [ ] Upload **unlisted** to YouTube. Privacy = Unlisted (NOT Private,
      not Public until the official submission)
- [ ] Capture the YouTube URL
- [ ] Sanity-check: open the YouTube URL in an incognito browser
      window. Confirm the video plays without requiring login.
- [ ] Save URLs:
  - 0G APAC video URL → `docs/hackathon-0g/submission-checklist.md`
    (the spot for the demo URL)
  - London Buildathon video URL → the HackQuest submission form +
    `docs/hackathon/sapphire-sentinel-london-2026.md`
- [ ] Submit to HackQuest forms before the respective deadlines:
  - 0G APAC: 2026-05-16 23:59 UTC+8
  - London Buildathon: 2026-06-14 15:54 UTC

---

## 7 · Last-minute sanity checks

Run through this list 5 minutes before you hit Record on take 1.

- [ ] Phone on silent
- [ ] Tab favicon notification badges all cleared
- [ ] Terminal prompt is short and doesn't leak any sensitive paths
      (consider `PS1='$ '` for the recording session)
- [ ] No secrets visible in the shell environment (`env | grep -i key`
      should not show plaintext keys; use `***REDACTED***` if any
      env var name needs to appear on screen)
- [ ] Recording tool is recording (sounds obvious, easy to forget — do
      a 5-second test clip first)
- [ ] You have a full glass of water within reach
- [ ] You've read both scripts' "Director's overall notes" once today
