# Grok Chat Alpha Ledger — 2026-08-06

> Curated from recent Grok / Drive / Notion / overnight agent work, **most recent first**.
> Scope: trading systems · automations · Grok Bridge · merge into Sapphire.
> Status: **inert knowledge + client integration** — does **not** clear killswitches or arm live trading.

## 0. Operating invariants (always)

1. Killswitch / trading pauses stay engaged until an attended, content-addressed owner bundle.
2. Models propose; deterministic coordinator + first-party receipts authorize.
3. No live orders from Telegram. No `git add .`. No secret material in chat digests.
4. Paper / research / docs may advance; money paths refuse without exact gate.

---

## 1. Most recent — Grok Bridge (2026-08-06, remote session)

### Alpha

| ID | Insight | Why it matters | Sapphire merge target |
|----|---------|----------------|------------------------|
| BR-01 | **SuperGrok OIDC transport works** via `~/.grok/auth.json` → `api.x.ai` (model `grok-4.5`) | Agents can call Grok without a separate metered API key while CLI session is valid | `lib/intel/grok_bridge_client.py`, control-plane workers |
| BR-02 | Transport priority: `mac-bridge` → `supergrok-oidc` → `xai-api` → `away-sim` | Fail closed to sim; prefer Safari bridge when Mac tunnel present | env `GROK_BRIDGE_URL` in ops secrets, doctor probe |
| BR-03 | Live diagnostics suite **11/11** on OIDC path (`/api/bridge/test`, `/api/bridge/diagnostics`) | Contract for agent health gates before batch prompts | `scripts/ops/grok_bridge_probe.py` (optional); chassis verify row |
| BR-04 | Mac Safari bridge (`:19998`) **not reachable** from remote sandbox | Away-mode is expected; home path needs tunnel or LAN | LaunchAgent + Tailscale funnel notes in ops runbook |
| BR-05 | REST surface: `/health` `/chat` `/new` `/history` `/test` `/diagnostics` | Same shape agents already expect from local bridge scripts | document in CLAUDE.md satellite table |

### Action (inert)

- [ ] Point Mac `GROK_BRIDGE_URL` when home; keep OIDC as remote fallback.
- [ ] Wire `GrokBridgeClient` into research workers only (read/propose).
- [ ] Never grant bridge chat path authority over killswitch or broker writers.

---

## 2. Sovereign architecture (Drive: System Design R1, 2026-07-29)

### Alpha

| ID | Insight | Why it matters |
|----|---------|----------------|
| SV-01 | Local-first truth; models are proposal-only | Prevents authority drift from chat/Telegram/UI |
| SV-02 | One content-addressed attended bundle for any outward action | Replay-safe; expiry invalidates mid-flight authority |
| SV-03 | Windows = compute workhorse; Mac = canonical until switchover | Matches chassis + GPU layout |
| SV-04 | Trading still **paused**; D3 caps leave **$0 new-risk** | No size-up until census + caps clear |
| SV-05 | Drive/Sheets/Telegram are **projections**, not canonical | Alpha digests land in docs/data, not as live policy |

### Action

- Keep this ledger under `docs/alpha/` + `data/alpha/alpha_ledger.json`.
- Any live cutover remains Task 095-class attended work (out of scope here).

---

## 3. Trading intelligence pipeline (MOC + CLAUDE.md, Jul 2026)

### Alpha

| ID | Insight | Why it matters |
|----|---------|----------------|
| TR-01 | Path: TV/OHLCV/chain → analytics + chain intel → event_bus → dashboard / Telegram draft / paper-executor | Single spine for signal alpha |
| TR-02 | Five strategies: RegimeAwareRSI, FundingRateContrarian, CorrelationBreakout, MultiTFMomentum, SapphireComposite | Honest strategy set (base class is not a strategy) |
| TR-03 | Forecast: Kronos ↔ TA → `consensus` + `edge_score` | Contradict filter before size |
| TR-04 | Signal stream **stale** (last ~2026-07-16); paper portfolio **stale** (~2026-07-02) | Restore `market-pulse` / signal-logger only after paper-vs-live decision |
| TR-05 | Prediction scoring is **timeframe-aware** | Don’t score 24h forecasts early |
| TR-06 | Unknown `execution_stage` → position size **0** (paper) | Debug zero-size orders before “strategy broken” |
| TR-07 | OKX needs browser UA; Binance funding US geo-block → OKX fallback | Chain sources must keep fallbacks |
| TR-08 | Sentiment scorer can **fake-neutral 50** on upstream failure | Treat 50/neutral as null when provider failed |

### Action

- Prefer re-arming signal logger + paper path over live HL/RH.
- Staleness monitor already flags; treat reds as ops work, not model work.

---

## 4. Thesis / cluster alpha (overnight deep work Jul 25–26 + pulses)

### Alpha (research-only; killswitch held)

| ID | Insight | Falsifier / gate |
|----|---------|------------------|
| TH-01 | **LIT = perp-DEX, not privacy** — Cluster A with HYPE (combined cap) | Thesis OS cluster-risk |
| TH-02 | **HYPE unlock** date drift (Aug-6 → ~Jul-28 primary trackers) + large unstaking overhang | Re-underwrite Cluster A before any add |
| TH-03 | **LIT cliff ~2026-12-27** multi-source | Unlock calendar |
| TH-04 | **BMNR mNAV** discount deepened (~0.84x → ~0.61x) — structure risk | Equity marks overnight |
| TH-05 | **SPCX** theo EV favored longer-dated debit spreads — replace theo with live mid | Killswitch holds; no auto options |
| TH-06 | Paper-scalp rules DISARMED: max pos %, daily/weekly loss halt, Cluster A combined 20%, BOT max 5% | Load via `ops-state/thesis/` |
| TH-07 | Portfolio bot ranking distill: BTC core > regime ensemble > ETH selective > SOL underweight | Quant distill note |

### Action

- Ingest into vault / Thesis-Desk only; no size-up.
- Keep unlock calendar JSON as machine-readable source for pre-size-up checks.

---

## 5. Automations / fleet (runbook + overnight)

### Alpha

| ID | Insight | Why it matters |
|----|---------|----------------|
| AU-01 | Fund factory T12/T15 can run while killswitch engaged (correct no-ops) | Loops must journal refused actions |
| AU-02 | Only a **small subset** of documented scheduled tasks may be installed on Mac | Don’t assume market-pulse exists from CLAUDE.md alone |
| AU-03 | PM bot **built, not deployed** (webhook URL, polling break-glass, python path) | Telegram ownership still not PM bot |
| AU-04 | Chassis supervisor pointer cutover is **attended R3** (Task 091 blocked on 090) | No mixed-generation processes |
| AU-05 | Hyperliquid caps: $5/order, 3x lev, 5 positions, $25/day loss; mainnet refuses until signing verified | Live executor policy |
| AU-06 | Cloud routines are issue/PR only — good pattern for chat-mined alpha too | This ledger follows that inert pattern |

### Action

- Alpha desk in Grok Bridge app mirrors this ledger for remote review.
- Chassis/Sapphire doctor: optional Grok Bridge health row.

---

## 6. Merge map → Sapphire tree

| Artifact | Path |
|----------|------|
| This document | `docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md` |
| Machine ledger | `data/alpha/alpha_ledger.json` |
| Bridge client | `lib/intel/grok_bridge_client.py` |
| Bridge integration note | `docs/alpha/BRIDGE-INTEGRATION.md` |
| Unit tests | `tests/unit/test_grok_bridge_client.py` |

## 7. Explicit non-actions

- No killswitch clear, no live order, no credential rotation, no DNS/deploy, no Telegram auto-send.
- No secrets from `~/.grok/auth.json` or `~/.config/sapphire-secrets/` in this pack.
