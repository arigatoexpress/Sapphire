---
source: local-export
date: 2026-08-05
type: research
topics: [telegram, oss]
title: TG terminal OSS mine
---

# Mine: PenguBot · BonkBot · OSS high-alpha systems → Ari plant

**Date:** 2026-08-05T23:25Z  
**Goal:** Professional autonomous **mobile trading terminal** + **separate command center** telemetry.

## What those systems get right (UX patterns)

### BonkBot / Trojan / Banana Gun class (Telegram DEX)
| Pattern | Why it wins | Ours |
|---|---|---|
| **One-tap buy/sell in chat** | Latency + mobile | Free-reign + /pending ✅; RH MCP for options |
| **Paste CA → trade card** | Zero friction | L2 dens + proposals; keep dens (BINGBONG lesson) |
| **Settings: slip / MEV / prio / auto-buy** | Control without leaving TG | Extend /bots FREE-REIGN panel |
| **Position list with TP/SL/trail** | Manage bag on phone | /skin + risk loop TP/SL (AXTI: scale 2×) |
| **Token intel in-card** | MC, liq, age | shield dens + VPIN |
| **Non-custodial / session keys** | Trust | MOSS session grants · never keys in TG |

### PenguBot (agentic multi-chain TG companion)
| Pattern | Why | Ours |
|---|---|---|
| **Agentic companion** not just swap UI | Research → trade | /do · /orch Grok · free-reign |
| **Self-custodial multi-chain wallet** | Custody clarity | Designated rails only; no TG custody |
| **Chat-native status** | Away desk | Dual surface terminal (this ship) |

### Open source to mine as skills (not unscoped brokers)
| Project | Mine |
|---|---|
| **Freqtrade** | Strategy lifecycle, backtest, Telegram remote control patterns |
| **OctoBot** | Web + Telegram dual control; multi-strategy dashboard |
| **Ninjabot / Hummingbot** | Grid/MM patterns, exchange abstraction |
| **Privy TG recipes** | Bot-first vs app-first wallet UX (we stay bot-first + OS custody) |
| **Coinbase tg-trading-bot** | Minimal command schema for mobile |

**Reject:** closed snipers that imply seed phrases in chat; auto-snipe without dens.

## Architecture we adopted (two surfaces)

```
┌─────────────────────┐     ┌──────────────────────────┐
│  ⚡️ TRADE TERMINAL  │     │  🖥 COMMAND CENTER        │
│  ARM / FREE-REIGN   │     │  plant healthz · GPU     │
│  Positions · Pending│     │  orch · VPIN · overnight │
│  Dens · AXTI playbook│    │  MOSS hours · telemetry  │
└──────────┬──────────┘     └────────────┬─────────────┘
           │  Telegram Central           │
           └─────────────┬───────────────┘
                         │
         free-reign · RH MCP · L2 · MOSS · plant :8100
```

**Web command center (separate from TG):**  
- Plant deck `http://127.0.0.1:8100/`  
- API `:8099/healthz`  
- `ops-state/command-center/` HTML  
- Do **not** mix trade buttons into telemetry-only views (BonkBot clarity).

## Alpha doctrine (from our AXTI win + their speed UX)

1. **Defined-risk options first** (AXTI 8/7 80c: +$175, scale-out before expiry).  
2. **Gamma exits > theta holds.**  
3. **L2 free-reign ≤$10** with dens — never unbounded meme snipes.  
4. **In-chat positions + risk** — ship automated TP ladder next (half @ 2× premium).  
5. **Self-learning:** genome.lessons already seeded; wire outcomes wins/losses next.

## Shipped this pass

- Telegram **dual home**: Trade Terminal + Command Center (`menu:trade` / `menu:cc`)  
- Reply keyboard reordered for mobile trade vs telemetry  
- Research receipt: this file + bridge export  

## Next (Opus / Grok)

| Priority | Item |
|---|---|
| P1 | Position cards with one-tap **TP / SL / close** (BonkBot positions UX) |
| P1 | Wire risk loop marks → RH option close on TP/SL |
| P2 | Mini “paste thesis → proposal” NL path via /do |
| P2 | Command center live JSON feed for remote HTML (when VPN/Tailscale) |
| P3 | Freqtrade-style strategy status row in /tracks |

## Sources (inspected via web search, 2026-08-05)

- bonkbot.io product surface (speed, Jupiter routing, MEV, limit/trail, token intel)  
- CoinGecko: common TG bot features (auto buy/sell, copy, limit, DCA)  
- PenguBot / Pudgy: agentic multi-chain TG companion (Apr 2026 news)  
- OctoBot OSS: dual web+Telegram control  
- Privy / Coinbase TG bot recipes: custody + agentic patterns  
- Local broker truth: AXTI fills on RH agentic `703758144`
