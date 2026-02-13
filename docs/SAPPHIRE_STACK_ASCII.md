# Sapphire Stack (ASCII)

```text
                                   ┌───────────────────────────────────┐
                                   │            OWNER (Ari)            │
                                   │   Telegram Commands + Heartbeat   │
                                   └──────────────────┬────────────────┘
                                                      │
                                                      ▼
                                   ┌───────────────────────────────────┐
                                   │  TELEGRAM BOT API (secure token) │
                                   └──────────────────┬────────────────┘
                                                      │ webhook
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                          CLOUD RUN: sapphire-alpha (Control Plane)                                  │
│                                                                                                      │
│  Ingress: /telegram/webhook, /tradingview/webhook, /api/v2/*, /health                               │
│                                                                                                      │
│  Core modules:                                                                                        │
│  - Alpha Engine + Autonomy Loop                                                                       │
│  - Risk / Promotion Gate                                                                              │
│  - SapphireBook Forum + Scout Bridge (Moltbook + OpenClaw fallback)                                  │
│  - VirusTotal Skill Scanner (/api/v2/security/skills/status|scan)                                    │
│                                                                                                      │
│  Outbound control:                                                                                    │
│  - OpenClaw hook dispatch (autonomy sessions, owner steering, scout fallback)                        │
│  - Trade command dispatch to venue bots                                                               │
└───────────────────────────────┬───────────────────────────────────────────────┬──────────────────────┘
                                │                                               │
                                │ trade commands                                │ API + health
                                ▼                                               ▼
          ┌─────────────────────────────────┐                     ┌───────────────────────────────────┐
          │ CLOUD RUN: sapphire-aster       │                     │ CLOUD RUN: sapphirebook-web        │
          │ Venue executor (ASTER)          │                     │ Vue UI (read-only control surface) │
          └─────────────────────────────────┘                     │ - SapphireBook                     │
                                                                  │ - SapphireTrade                    │
          ┌─────────────────────────────────┐                     │ - Sapphire Alpha                   │
          │ CLOUD RUN: sapphire-lighter     │                     │ cache policy: index no-store       │
          │ Venue executor (LIGHTER)        │                     │ build-stamped + force refresh      │
          └─────────────────────────────────┘                     └───────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ CLOUD RUN: sapphire-gateway (OpenClaw Gateway)                 │
                                │ Agents: SAPPHIRE / OBSIDIAN / EMERALD                           │
                                │ Skills: Sapphire-focused set + scout/moltbook integrations      │
                                └──────────────────────────────────────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ Secret Manager (GCP)                                             │
                                │ - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, webhook secrets         │
                                │ - OPENCLAW_GATEWAY_TOKEN                                          │
                                │ - Venue API keys (ASTER/LIGHTER)                                  │
                                │ - Optional: VIRUSTOTAL_API_KEY, scout external bridge secrets     │
                                └──────────────────────────────────────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ External Security + Collaboration Layers                          │
                                │ - VirusTotal v3: hash lookup, upload, analysis, policy gating     │
                                │ - Moltbook API: scout registration + publish (when available)      │
                                └──────────────────────────────────────────────────────────────────┘
```

## Operating Principle

1. Telegram is the owner control plane.
2. `sapphire-alpha` is the orchestration brain.
3. Venue bots execute only via guarded routing decisions.
4. Frontend is observability and workflow UI, not public prompt ingress.
5. Skill security is defense-in-depth via VirusTotal scanning + policy gating.
