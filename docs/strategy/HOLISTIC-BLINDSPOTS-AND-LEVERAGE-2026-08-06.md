# Holistic blindspots & leverage map — 2026-08-06

**Status:** research + monorepo-encoded gates  
**Companions:** `lib/grok/blindspots.py` · `lib/grok/playbooks.py` · `lib/grok/policy.py`  
**Plant rest:** Claude cleaning Mac · Gemini deploying site — this doc does not load the plant.

---

## 1) System truth (roles)

```text
Mac commander     → authority, densify, broker MCP, killswitch
Windows private DC → always-on GPU/research/workers (after P0)
GCP               → warehouse + public face + Cloud Shell (not sole writer)
Grok monorepo     → policy kernel, alpha, streamline, playbooks
```

Earn only on **designated rails** under dens, caps, grants, and attended gates.

---

## 2) Blindspot scoreboard

See live list in `lib/grok/blindspots.py`. Headline P0s:

| ID | Blindspot | Fix owner |
|---|---|---|
| BS-GATE-WIRE | Plant sole writer ≠ `gate_order` | Claude Prompt A |
| BS-GENOME-CLOSES | No lessons on closes | Claude Prompt B |
| BS-WIN-P0 | Win not green | Desk / Prompt D |
| BS-MOSS-GRANT | Grant expired | Operator renew |
| BS-DASHBOARD-SPA | Blank Mission Control until deploy | Gemini deploy `5ed4058+` |

P1 themes: Mac↔Win sync, process bloat, TA not gated, onchain dry-run, regime not live, HL signing, knowledge embeds, sparse schtasks.

P2: champion ladder, GCP cost, DNS orphan, thin dens addrs, publish loop, HYPE/LIT calendars.

---

## 3) Trading strategy stack (what to actually run)

### 3.1 Money rails (small, fenced)

| Playbook | Rail | Size doctrine |
|---|---|---|
| **AXTI options** | `rh_agentic` | Defined-risk premium; DTE 2–21; half at 2×; SL −40%; day premium cap |
| **L2 experimental** | `rh_l2` | ≤$10, max 1, dens permanent, no crisis snipes |
| **MOSS session** | `moss` | Grant hours_left > 0 only |
| **HL capped** | `hyperliquid` | Signing gate armed + notional cap (default disarmed) |
| **Dust** | exits only | Never free-reign re-buy IBIT/HOOD/PLTR/NVDA class |

### 3.2 Paper / research (Win DC after P0)

| Strategy (code) | Use |
|---|---|
| `RegimeAwareRSI` | Primary paper worker |
| Funding contrarian / multi-TF momentum / composite | Shadow only until walk-forward |
| GMM regime (`lib/analytics/regime.py`) | Feature for gates (`regime=` on proposals) |
| TV TA machine | Watchlists + work orders — **not** auto submit |

### 3.3 TA stack (aligned with `tradingview_ta_machine`)

EMA20 · RSI14 · MACD · Bollinger · Volume — TFs 15 / 60 / 240 / D  
Core: BTC, ETH, SOL, HYPE, ZEC + thesis clusters (crypto_risk_perp · ai_narrative · space · sound_money).

### 3.4 Onchain

- `onchain_intel` snapshot/status is **advisory**
- Feed spine as one source count when fresh
- Never public exact wallets; MOSS stays wallet-blind on public face
- Dens: append full `0x` from losses into `projects/grok/data/dens_permanent.json`

### 3.5 Late-cycle thesis (enforced in policy)

From `config/investment_thesis.yaml` posture **late_cycle_capital_preservation**:

- Day loss halt (default −$75 realized)
- Options premium day cap (default $150)
- Block L2 buys in `crisis` / `risk_off`
- Prefer defined-risk options over meme equity/L2

Invalidators (manual review, not auto FOMO): durable breadth expansion, stablecoin-adj BTC.D trend reverse, persistent liquidity easing.

---

## 4) Signal spine (TR-EDGE / TR-01)

```text
TV/OHLCV → regime → (optional) onchain snapshot → gate_order → confirmation_firewall → sole writer
         ↘ paper research worker / walk-forward
         ↘ genome lessons on close
```

Minimum sources configurable (`signal_spine.require_min_sources`). Default 1 so plant can wire gradually; raise to 2+ when TV+regime both live.

---

## 5) Highest-leverage GCP moves (ordered)

1. **Deploy** dashboard SPA fix (already coded)  
2. **min-instances=0** + memory right-size  
3. **BQ** paper outcomes / regime digests (batch)  
4. **GCS lifecycle**  
5. **Vertex batch only** — no always-on endpoints  
6. Weekly `cost_posture_report` + `gcp_ai_inventory`  
7. Public evidence from sanitized APIs only  
8. **Never** move sole writer to Cloud Functions  

Projects: `sapphire-479610` = site+DNS · `tho-ai-agent` = BQ/GCS/batch.

---

## 6) Local setup improvements (no thrash)

| Layer | Action |
|---|---|
| Mac | After cleanup: inventory LaunchAgents; keep densify 30m; one free-reign gate wire |
| Win | P0 only; then research_worker paper; then consider L2 schtasks |
| Bridge | Already green — don’t rewrite |
| Policy | Pull main — DTE, day caps, HL, regime L2 block |
| Alpha | Keep ledger; map actions to playbooks |

---

## 7) 14-day holistic program

| Day | Focus |
|---|---|
| 0–1 | Gemini: site deploy · Claude: Mac clean → gate_order |
| 2 | Genome closes · MOSS grant renew if desired |
| 3–4 | Win P0 · research_worker smoke |
| 5–7 | Paper RegimeAwareRSI shadow · densify outcomes to BQ (optional) |
| 8–10 | Raise signal spine min sources · couple TV regime |
| 11–14 | Champion/challenger criteria · publish one research post-mortem |

---

## 8) Non-goals

- Ambient LLM money  
- THO funds on Sapphire rails  
- Always-on Vertex  
- Unbounded meme snipes  
- Competing with Gemini on Cloud Run while deploy in flight  

---

**Encoded now in monorepo:** day loss halt, options day cap, AXTI DTE band, HL signing gate, regime L2 block, playbooks, blindspot registry.  
**Still human/plant:** wire, deploy, Win P0, grant renew, dens addr expansion from live losses.
