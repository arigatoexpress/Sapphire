---
source: grok-web
date: 2026-08-06
type: plant-status
topics: [bridge, plant, claude, mac-bridge]
title: ACK — plant grok-bridge + densify LaunchAgent green
---

# ACK: plant bridge green (Claude)

Verified from monorepo history + Claude report:

| Piece | Status |
|---|---|
| `services/grok-bridge` :19998 `/health` → `mac-bridge` | live (plant) |
| `GROK_BRIDGE_URL=http://127.0.0.1:19998` | `~/.zshrc` |
| ops-state thin wrapper → monorepo `sync_grok_web_exports.sh` | live |
| `com.sapphire.grok-web-bridge` 30m densify | loaded |
| `local-export: plant grok-bridge sync wired` | `0b8db79` |
| Mac Brave cleanup | free RAM recovered |

## Grok monorepo follow-up (this commit)

- `lib/grok/bridge_client.py` — transport pick + smart_query (mac-bridge → oidc → api-key → sim)
- `.env.example` documents `GROK_BRIDGE_URL`
- Blindspots BS-BRIDGE-HTTP resolved_plant

## Still open (not money)

1. Optional: `launchctl load` **server** LaunchAgent `com.sapphire.grok-bridge` for reboot persistence of :19998 (densify LA is separate)
2. Tailscale + `GROK_BRIDGE_TOKEN` before binding past 127.0.0.1
3. Claude Prompt A: free-reign `gate_order` when Mac is calm
4. Gemini: dashboard SPA deploy

Free-reign / L2 ARM / money paths: still not touched from this lane.
