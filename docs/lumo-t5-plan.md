# Lumo AI — T5 Integration

**Status**: MVP shipped (2026-04-15) — **Note:** `lumo-api` repo was archived 2026-05-12.
If re-enabling, clone fresh from `carlostkd/Lumo-Api-V2` or restore from `_Archive_2026-05-12/repo-quarantine-2026-05-12/lumo-api`.  
**Author**: Sapphire autonomous session (Night 2 → Night 3)

---

## What Was Built

Lumo AI T5 is live. It uses **Lumo-Api-V2** (carlostkd) — a Node.js + Playwright Firefox
server that automates `lumo.proton.me` headlessly on the Mac. No Windows CDP required.

### Actual Architecture

```
Hermes /cyber|/cve|/threat
        │
        └─► plugins/claw-sapphire/tools/lumo_research.py
                │
                POST http://localhost:3333
                │
                ~/Code/lumo-api/lumo.js  (Node.js + Playwright Firefox)
                │
                lumo.proton.me  (Proton E2E encrypted session)
                │
                Lumo AI response (plain text) ◄── returned
```

### Component Map

| Layer | Component | Path |
|-------|-----------|------|
| Trigger | hermes skills | `~/.hermes/skills/sapphire/cyber-intel/SKILL.md` |
| Plugin tool | `lumo_research.py` | `plugins/claw-sapphire/tools/lumo_research.py` |
| API server | `lumo.js` | `~/Code/lumo-api/lumo.js` |
| Browser | Playwright Firefox (headless) | port 3333 |
| AI | Lumo (Proton) | lumo.proton.me |
| Dashboard | SOC Security Research card | `/soc` → `/api/soc/cyber-research` |

---

## Setup (One-Time, Manual)

```bash
# 1. Clone Lumo-Api-V2 (already done at ~/Code/lumo-api)
git clone https://github.com/carlostkd/Lumo-Api-V2.git ~/Code/lumo-api
cd ~/Code/lumo-api
npm install playwright

# 2. Authenticate (opens Firefox for Proton login — do this once)
node generate_auth.js
# Browser opens → log in to lumo.proton.me → press ENTER in terminal
# Creates auth.json (session cookies — keep safe)

# 3. Start the API server
node lumo.js
# Output: ✅ Lumo UI ready · 🐈 Lumo API V2 running on http://localhost:3333
```

### Persistent Operation

A disabled LaunchAgent is at:
```
~/Code/Sapphire/infra/launchagents/com.sapphire.lumo-api.plist.disabled
```

To activate once `auth.json` is configured:
```bash
cp ~/Code/Sapphire/infra/launchagents/com.sapphire.lumo-api.plist.disabled \
   ~/Library/LaunchAgents/com.sapphire.lumo-api.plist
launchctl load ~/Library/LaunchAgents/com.sapphire.lumo-api.plist
```

---

## Plugin Tool (`lumo_research.py`)

Stdin JSON → stdout JSON. Three actions:

```bash
# Check if Lumo API server is running
echo '{"action":"status"}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/lumo_research.py

# General security question
echo '{"action":"ask","query":"What is CVE-2026-1340?","web_search":true}' | python3 ...

# Structured security brief (standard = 5 sections, deep = 8 sections + MITRE)
echo '{"action":"security_brief","topic":"CVE-2026-1340","depth":"deep","web_search":true}' | python3 ...
```

**Sensitivity gate**: Auto-redacts `api_key`, `password`, `bearer`, `-----BEGIN`, SSN, Visa/MC
patterns before sending to Lumo.

**Fallback**: Returns `{"status":"offline","fallback":"..."}` if port 3333 unreachable — caller
handles gracefully.

---

## Hermes Skills (`/cyber`, `/cve`, `/threat`)

File: `~/.hermes/skills/sapphire/cyber-intel/SKILL.md`

| Command | Route | Use case |
|---------|-------|----------|
| `/cyber <query>` | `lumo_research.py ask` | General security question |
| `/cve CVE-XXXX-NNNN` | cyber-threat-bot brief + lumo_research.py security_brief deep | Full CVE analysis |
| `/threat <topic>` | `lumo_research.py security_brief standard` + CTB scan | Threat actor / malware |

---

## SOC Dashboard Integration

- **Card**: "Lumo Security Research" on `/soc` page
- **Endpoint**: `POST /api/soc/cyber-research` (requires auth)
- **Status check**: `GET /api/soc/lumo-status` — TCP ping to port 3333
- Badge updates every 60s: `ONLINE` (green) / `OFFLINE` (red)
- Supports Enter-to-submit, web search toggle, Ask/Brief/Deep modes

---

## Inference Tier Assignment

| Tier | Route | Use |
|------|-------|-----|
| T1 | Windows GPU (RTX 5070 Ti) | Code, general |
| T2 | Pi rari1/rari2 | Fast inference |
| T3 | Mac Ollama | Balanced/local |
| T4 | Kimi cloud | Non-sensitive general research |
| **T5** | **Lumo (Proton)** | **Security: CVE, threat intel, compliance, MITRE** |

---

## Security Properties

- **Local Firefox session** — Playwright headless Firefox, no visible browser window
- **Proton E2E encryption** — queries encrypted on Proton servers, not stored in plain text
- **Sensitivity gate** — regex classifier strips secrets before transmission (same patterns as T4 gate)
- **Tailscale-local** — API server on localhost:3333, not exposed beyond the machine
- **Safe to send**: CVE IDs, system names, architecture descriptions, redacted logs
- **Not safe to send**: raw API keys, JWT tokens, passwords, private keys (auto-redacted)

---

## Known Limitations

- First query after cold start may be slow (~30-60s, Playwright browser init)
- Lumo API server must be started manually until LaunchAgent is activated
- `auth.json` session expires — re-run `node generate_auth.js` if Lumo returns 401/redirect
- No concurrent requests — `lumo.js` serializes with a `busy` flag (queue one at a time)
- Ghost mode (memory-less sessions) supported via `node lumo.js ghost:true` or per-request

---

## Original CDP Approach (Superseded)

The original scoping document proposed CDP to Brave on Windows (port 9223). That approach
was **not implemented** — Lumo-Api-V2 running locally on Mac is simpler, requires no Windows
dependency, and uses Proton's native E2E encryption rather than CDP over Tailscale.
