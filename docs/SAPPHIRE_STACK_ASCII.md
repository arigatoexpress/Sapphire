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
│                           CLOUD RUN: sapphire-alpha (Engine)                                        │
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
│                                                                                                      │
│  Control-plane wedge:                                                                                 │
│  - `/sapphire …` Telegram updates are proxied to `sapphire-control` (no webhook move)                │
└───────────────────────────────┬───────────────────────────────────────────────┬──────────────────────┘
                                │                                               │
                                │ trade commands                                │ API + health
                                ▼                                               ▼
          ┌─────────────────────────────────┐                     ┌───────────────────────────────────┐
          │ CLOUD RUN: sapphire-aster       │                     │ Firebase Hosting: sapphirealpha.xyz│
          │ Venue executor (ASTER)          │                     │ Vue UI (read-only control surface) │
          └─────────────────────────────────┘                     │ - SapphireBook                     │
                                                                  │ - SapphireTrade                    │
          ┌─────────────────────────────────┐                     │ - Sapphire Alpha                   │
          │ CLOUD RUN: sapphire-lighter     │                     │ cache policy: index no-store       │
          │ Venue executor (LIGHTER)        │                     │ build-stamped + force refresh      │
          └─────────────────────────────────┘                     └───────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ CLOUD RUN: openclaw-gateway (AI Agent Gateway)                   │
                                │ Agents: SAPPHIRE / OBSIDIAN / EMERALD                             │
                                │ Skills: Sapphire-focused set + scout/moltbook integrations        │
                                │ Ingress: internal + IAM-invoker only                               │
                                └──────────────────────────────────────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ CLOUD RUN: sapphire-control (Ops Control Plane)                   │
                                │ - /sapphire (dashboard HTML)                                      │
                                │ - /sapphire/app.js (CSP-safe JS)                                  │
                                │ - /sapphire/api/status|directive (bearer token)                   │
                                │ - /internal/telegram (bearer token + chat-id allowlist)           │
                                │ Served at: https://sapphirealpha.xyz/sapphire (Firebase rewrite)  │
                                └──────────────────────────────────────────────────────────────────┘

                                ┌──────────────────────────────────────────────────────────────────┐
                                │ CLOUD RUN: sapphire-gateway + sapphire-github-webhook-relay       │
                                │ GitHub webhook plumbing (invoker IAM + signature verification)     │
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
3. `sapphire-control` is the `/sapphire` namespace owner (dashboard + directive state).
4. Venue bots execute only via guarded routing decisions.
5. Frontend is observability and workflow UI, not public prompt ingress.
6. Skill security is defense-in-depth via VirusTotal scanning + policy gating.
