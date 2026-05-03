# Arbitrum Open House London Buildathon — Demo Recording Script

**Target:** ≤90s total. Aim for 75s to leave buffer.
**Recording:** 1080p (1920x1080), no music, browser zoom 110% so
explorer addresses and policy reasons are readable, hide all unrelated
tabs/notifications.
**Source pitch:** `docs/hackathon/sapphire-sentinel-london-2026.md`
**Source research:** `docs/research/hackathon-strategy/robinhood-arbitrum-deep-dive.md`
(Lane R, PR #560) — recommends opening with the prompt-injection-blocked
+ on-chain-anchored beat as the "holy shit" moment.
**Toggle env vars used:**
- `SENTINEL_DEMO_FORCE_INJECTION=1` (Lane Inject, PR #568)
- `SENTINEL_DEMO_FORCE_DEPEG=1` (Lane E, PR #555)

---

## Director's overall notes (read once before recording)

- **Lead with the attack.** Lane R's analysis: the prompt-injection-blocked
  beat is more visceral than the approve-flow beat. Open on it. Don't
  waste 15s on context — the attack lands in the first 8 seconds.
- **Live testnet tx is mandatory.** A real `recordPaymentEvaluation` tx
  landing on Robinhood Chain testnet during the recording is the single
  highest-value frame. Lane R: "judges have learned to spot fake demos."
- **Pre-fund three keys.** Faucet outage on demo day is a real failure
  mode. The pre-recording checklist enforces this.
- **Pause/breath markers** are written as `[breath]` in the script — these
  are 0.4-0.6s natural pauses for diction, not silent gaps.
- **Backup take.** Always record the entire 90 seconds twice. 90 seconds
  is short enough that re-recording is cheap; a single fluffed line in
  take 1 is much faster to fix by re-recording the whole thing.

---

## 0:00 — 0:08 · Hook (the attack frame)

**Words to say (verbatim):**

> "Watch this AI agent try to pay for an attack." [breath]

**On screen:**

- Browser at `http://localhost:8080/chain/sentinel`.
- The right-rail "evaluate" button is visible (anchor location:
  `services/dashboard/templates/pages/sentinel.html` line 296).
- Cursor hovers over the evaluate button.
- Pull-quote overlay (lower third):
  **"Sapphire Sentinel — agent safety on the chain Robinhood operates."**

**Commands to run / actions:**

- Pre-export: `export SENTINEL_DEMO_FORCE_INJECTION=1`
  (do this before the browser is in front; the env must be in the dashboard
  process's environment, not just your shell).
- The dashboard must already be running with this env set. Restart with:
  `SENTINEL_DEMO_FORCE_INJECTION=1 AUTH_PASSWORD=sapphire python3 services/dashboard/app.py`

**Approximate duration:** 8s

**Director's note:** The cursor must be on the evaluate button before the
narration ends so the click that follows in the next scene is one
continuous motion, not a separate "now where's the button" search.

---

## 0:08 — 0:30 · The attack hits (the holy-shit beat)

**Words to say (verbatim):**

> "Sentinel screens every paid-intelligence request — prompt injection,
> [breath] secret exfiltration, [breath] mandate violation. The attack
> never reaches the trading layer."

**On screen:**

- Cursor clicks the evaluate button.
- Within ~1s, the Policy screening panel updates to show:
  - **BLOCKED** (red/amber color, large)
  - Risk flags stacked: `prompt_injection`, `secret_egress_risk`
  - Reason text from `lib/hackathon/sentinel.py` line 483-484:
    "payload contains prompt-injection language" and
    "payload appears to request or expose secret material"
- Approved=False clearly visible.
- Mandate, spend cap, and budget rows render but the BLOCKED stamp
  dominates.

**Commands to run / actions:**

- Single click on the evaluate button. The `evaluateResource()` JS handler
  (defined at sentinel.html line 372) calls
  `POST /api/hackathon/sentinel/evaluate`.

**Approximate duration:** 22s

**Director's note:** The two risk flags stacking is the visual punchline —
make sure both `prompt_injection` AND `secret_egress_risk` are on screen at
the same time. Per the test in
`tests/unit/test_dashboard_sentinel_demo_inject.py` (case 4), they trip
together when `SENTINEL_DEMO_FORCE_INJECTION=1` is set, so you don't need
to engineer this — but verify it before recording.

---

## 0:30 — 0:50 · The chain anchor (attack attestation forever)

**Words to say (verbatim):**

> "Even the rejected attack is anchored on Robinhood Chain. [breath]
> Tamper-proof receipt of the attempt. Auditable for ever."

**On screen:**

- Click through to the chain anchor preview / explorer link rendered in
  the dashboard's anchor panel (the demo response includes
  `anchor.tx_hash` and `anchor.explorer_url`).
- New tab opens at
  `https://explorer.testnet.chain.robinhood.com/tx/0x...`.
- The Blockscout page renders showing `recordPaymentEvaluation`
  transaction with the rejected receipt's hash fields visible.
- Highlight (yellow box overlay) the `riskHash` field on chain.

**Commands to run / actions:**

- Click on the explorer link in the dashboard (no terminal command).
- Pre-warm this tab: open a real prior `recordPaymentEvaluation` tx in a
  background tab so when you click the live link, you have a fallback if
  the new tx is still confirming.

**Approximate duration:** 20s

**Director's note:** This is Lane R's core "holy shit" beat verbatim:
"attestation that an attack happened, anchored on Robinhood Chain
forever." Do not rush the on-screen pause when the explorer page lands —
let the tx hash render fully for at least 2 full seconds before
narrating.

---

## 0:50 — 1:10 · The chain-health twist (multi-chain wedge)

**Words to say (verbatim):**

> "Sentinel doesn't just check the attacker. It checks the chain state of
> every protocol the alpha references. [breath] USDM depegging on
> MegaETH? Aave reserve frozen? Order refused, on-chain receipt issued."

**On screen:**

- Cut back to the dashboard. Cursor on the evaluate button again.
- Status text overlay (briefly, ~1s, top-right): "+ chain-health gate"
- Click evaluate.
- Within ~1s, the BLOCKED stamp returns — but now the reason stack ALSO
  includes `chain_state_degraded` AND a numeric peg-divergence reading
  (per the test in `tests/unit/test_dashboard_sentinel_chain_health.py`
  case 3, this is `peg_divergence_bps=500` when both env toggles are on).
- Reason stack visible in this order:
  1. `prompt_injection`
  2. `secret_egress_risk`
  3. `chain_state_degraded` (peg_divergence_bps: 500)

**Commands to run / actions:**

- Pre-export both: `export SENTINEL_DEMO_FORCE_INJECTION=1` AND
  `export SENTINEL_DEMO_FORCE_DEPEG=1`.
- Restart the dashboard with both env vars set:
  `SENTINEL_DEMO_FORCE_INJECTION=1 SENTINEL_DEMO_FORCE_DEPEG=1 AUTH_PASSWORD=sapphire python3 services/dashboard/app.py`
- Click the evaluate button.

**Approximate duration:** 20s

**Director's note:** The narration question rhythm
("USDM depegging? [pause] Aave reserve frozen? [pause]") needs to land
naturally — practice this line aloud 3 times before recording. The on-
screen `peg_divergence_bps: 500` matches the question; let the viewer
make the connection.

---

## 1:10 — 1:25 · Multi-chain proof (three chains in one view)

**Words to say (verbatim):**

> "Three chains. Two protocol categories. One agent-safety primitive."

**On screen (quick cuts, ~5s each):**

1. **MegaETH (chain 4326)** — chain-health verdict panel showing USDM peg
   reading + Aave reserve health (from `lib/hackathon/chain_health_gate.py`
   reading via the MegaETH access layer at `lib/chains/megaeth/`).
2. **Arbitrum (chain 42161)** — placeholder panel showing the same
   verifier pattern would port (annotation: "GMX V2 + Aave port — Q3
   2026 roadmap"). If a live read isn't wired yet, show the planned
   surface area only.
3. **Optimism (chain 10)** — same pattern, placeholder for cross-DEX
   alpha.

**Commands to run / actions:**

- These can be a pre-rendered slide if the live multi-chain panel doesn't
  fully ship by recording day. Lane R explicitly accepts a "static
  diagram for the README that shows it on one page" as the artifact
  that lifts the Innovation/Creativity score.

**Approximate duration:** 15s

**Director's note:** If one of the three chains can't render a live
verdict by recording day, label it explicitly as "roadmap" on screen —
don't fake a live read. Honest "Q3 2026 roadmap" labeling scores better
than a faked panel that judges spot.

---

## 1:25 — 1:30 · Close

**Words to say (verbatim):**

> "Sapphire Sentinel — agent safety on the chain Robinhood operates."

**On screen (end card, hold for 5s):**

```
github.com/arigatoexpress/Sapphire

SapphireSentinelRegistry  0x... (chain 46630, Robinhood Chain testnet)

Robinhood Chain explorer:
https://explorer.testnet.chain.robinhood.com/address/0x...

Best Agentic Project · Robinhood Chain reserved slot
```

**Commands to run / actions:** none — static end card.

**Approximate duration:** 5s

**Director's note:** Hard ceiling is 90s. If the take has run long, drop
the multi-chain proof scene from 15s to 8s (cut from three chain panels
to two) — that's the safest place to recover time. Never cut the close.

---

## Recording sequence (do these in order)

1. Pre-flight (day before): run
   `scripts/hackathon_smoke.sh --network testnet` end-to-end. Make sure
   `recordPaymentEvaluation` lands a real tx on Robinhood Chain testnet
   from your demo wallet, and that the explorer page renders.
2. Pre-fund 3 separate operator keys via the three faucets (official +
   Chainlink mirror + QuickNode mirror) — Lane R's "faucet outage
   insurance."
3. Test both env toggles separately first:
   - `SENTINEL_DEMO_FORCE_INJECTION=1` only → evaluate → confirm
     prompt_injection + secret_egress_risk both flag.
   - `SENTINEL_DEMO_FORCE_DEPEG=1` only → evaluate → confirm
     chain_state_degraded + peg_divergence_bps=500.
4. Test the combined toggle: both env vars set → evaluate → confirm all
   three risk flags stack.
5. Record take 1 of all 6 segments back to back (no editing breaks).
6. Watch take 1 in full. If any segment fluffs, re-record the entire 90
   seconds — it's faster than splicing at this length.
7. Record take 2 of the full 90 seconds as backup.
8. Edit, add the four pull-quote overlays, add the end card, polish.
9. Final cut ≤90s. Upload to YouTube unlisted. Capture the public URL.
10. Drop URL into the HackQuest London Buildathon submission form.
