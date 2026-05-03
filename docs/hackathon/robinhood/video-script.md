# Sapphire Sentinel · Robinhood London — 60s Pitch Video Script

**Target:** 60s hard cap (the long-form 90s cut lives at
`docs/hackathon/london-demo-script.md`).
**Recording:** 1080p, browser zoom 110%, no music, narrator voice (Ari).
**Hackathon:** Arbitrum Open House London Buildathon
**Categories:** AI Agentic Category ($15K) + Robinhood Chain Innovation Award ($30K)
**Buildathon start:** 2026-05-25
**Deadline:** see Devfolio listing
**Submission anchors:** PRs [#544](https://github.com/arigatoexpress/Sapphire/pull/544), [#546](https://github.com/arigatoexpress/Sapphire/pull/546), [#547](https://github.com/arigatoexpress/Sapphire/pull/547), [#553](https://github.com/arigatoexpress/Sapphire/pull/553), [#555](https://github.com/arigatoexpress/Sapphire/pull/555), [#556](https://github.com/arigatoexpress/Sapphire/pull/556), [#567](https://github.com/arigatoexpress/Sapphire/pull/567), [#568](https://github.com/arigatoexpress/Sapphire/pull/568)

---

## [0:00] · Hook — the attack frame (8s)

**Voice:**
> "Watch this AI agent try to pay for an attack."

**On screen:**
- Browser at `http://localhost:8080/chain/sentinel` (or live demo URL).
- Cursor hovers over the "Evaluate" button on the right rail.
- Pull-quote (lower third):
  **"Sapphire Sentinel — agent safety on the chain Robinhood operates."**

---

## [0:08] · The attack lands and Sentinel blocks (15s)

**Voice:**
> "Sentinel screens every paid-intelligence request. Prompt injection,
> secret exfiltration, mandate violation. The attack never reaches the
> trading layer."

**On screen:**
- Cursor clicks Evaluate.
- Within ~1s, the policy panel updates:
  - Big **BLOCKED** stamp (red).
  - Stacked risk flags: `prompt_injection`, `secret_egress_risk`.
  - Reason text from `lib/hackathon/sentinel.py`:
    "payload contains prompt-injection language" + "payload appears to
    request or expose secret material."
  - Approved=False clearly visible.

**Toggle:** dashboard launched with `SENTINEL_DEMO_FORCE_INJECTION=1`
(PR #568 enables this in 1-line for demo days).

---

## [0:23] · The chain anchor — attestation forever (12s)

**Voice:**
> "Even the rejected attack is anchored on Robinhood Chain. Tamper-proof
> receipt of the attempt. Auditable forever."

**On screen:**
- Click the explorer link rendered in the dashboard's anchor panel.
- New tab opens at `https://explorer.testnet.chain.robinhood.com/tx/0x...`.
- The Blockscout page renders, showing the `recordPaymentEvaluation`
  transaction with the rejected receipt's `riskHash` field.
- Yellow box on `riskHash`.

---

## [0:35] · The chain-health twist (12s)

**Voice:**
> "Sentinel doesn't just check the attacker. It checks the chain state.
> USDM depegging on MegaETH? Aave reserve frozen on Arbitrum? Order
> refused. On-chain receipt issued."

**On screen:**
- Cut back to the dashboard.
- Click Evaluate again — this time with both `SENTINEL_DEMO_FORCE_INJECTION=1`
  *and* `SENTINEL_DEMO_FORCE_DEPEG=1` set (PR #555 toggle).
- BLOCKED stamp returns. Risk flags stack THREE deep:
  1. `prompt_injection`
  2. `secret_egress_risk`
  3. `chain_state_degraded` (`peg_divergence_bps: 500`)

---

## [0:47] · The novelty — privacy preserved (8s)

**Voice:**
> "Hidden basket weights stay encrypted. Sentinel returns a deterministic
> result-hash and risk-hash from a Zama fhEVM mock — proving the agent saw
> the data without ever exposing it."

**On screen:**
- Terminal:
  ```python
  $ python3 -c "from lib.hackathon.privacy_mock import \
      sealed_basket_query; print(sealed_basket_query('btc_basket'))"
  {"result_hash": "0xa1b2...", "risk_hash": "0xc3d4...", "verifiable": true}
  ```
- The hashes match between calls; the underlying weights never leave the
  enclave-mock.

---

## [0:55] · End card (5s)

**Voice:**
> "Sentinel — agent safety on the chain Robinhood operates."

**On screen (static end card, hold 5s):**

```
github.com/arigatoexpress/Sapphire
hack.sapphirealpha.xyz

SapphireSentinelRegistry — chain 46630 (Robinhood Chain testnet)
SapphirePaymentGate    — chain 46630

#OpenHouseLondon #RobinhoodChain
```

---

## Director's notes

- **Lead with the attack.** Per Lane R's research (PR #560), the
  prompt-injection-blocked beat is more visceral than the approve-flow
  beat. Open on it.
- **Live testnet tx is mandatory.** A real `recordPaymentEvaluation` tx
  landing on Robinhood Chain testnet during the recording is the single
  highest-value frame.
- **Pre-fund three keys.** Faucet outage on demo day is a real failure
  mode. The 90s cut's pre-recording checklist enforces this.
- **The privacy-mock beat is the differentiator.** Most submissions stop
  at "agent safety." We go one further — agent safety *with privacy
  preservation*. That's what the Innovation Award judges score.

---

## Recording sequence

1. Pre-flight day before: run `scripts/hackathon_smoke.sh --target robinhood`
   end-to-end (PR #556). Confirm `recordPaymentEvaluation` lands a real tx.
2. Pre-fund 3 separate operator keys via three faucets (official + Chainlink
   mirror + QuickNode mirror).
3. Test both env toggles separately first:
   - `SENTINEL_DEMO_FORCE_INJECTION=1` only → confirm 2-flag stack.
   - `SENTINEL_DEMO_FORCE_DEPEG=1` only → confirm chain_state_degraded.
4. Test combined toggle: confirm 3-flag stack.
5. Record take 1 of all 7 segments back to back.
6. Watch take 1. Re-record any fluffed segments.
7. Record take 2 of full 60s as backup.
8. Edit, splice, add overlays.
9. Final cut ≤60s. Upload to YouTube unlisted. Capture URL → Devfolio submission.
