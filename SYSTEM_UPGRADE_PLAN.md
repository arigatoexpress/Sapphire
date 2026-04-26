# Sapphire OS — System Upgrade Plan
## Multi-Tier Inference: Windows GPU + Mac Local + Kimi Cloud + Pi (future)

**Date:** 2026-04-10 (updated 2026-04-14)  
**Status:** Phase 1-4 Complete — Pi tier live (rari1 + rari2), Kimi Cloud pending API key renewal  
**Author:** Architecture audit → implementation

---

## 1. Current State (Audit Findings)

### Inference Stack
```
hermes-agent (Telegram bot)
    └── inference-proxy:11435
            ├── Windows GPU Ollama:11434  ← primary (native /api/chat)
            └── Mac Local Ollama:11434    ← fallback (/v1/ compat)
```

### Dispatch Stack (claw-sapphire plugin)
```
sapphire_dispatch tool
    ├── T0: Nemotron GPU (free, analysis)   ← via inference-proxy
    ├── T1: Kimi CLI subprocess             ← BRITTLE (auth expires ~1h)
    ├── T2: Claw-code binary
    └── T3: Claude API
```

### Identified Gaps
| Gap | Impact | Priority |
|-----|--------|----------|
| Kimi CLI auth tokens expire ~1 hour | Manual `kimi login` needed constantly | HIGH |
| No Kimi Cloud HTTP fallback in inference-proxy | hermes fails if both GPU + Mac down | HIGH |
| `~/Code/kimi-tools` referenced but missing | Plugin config broken reference | MEDIUM |
| No Pi tier (decommissioned, no path back) | Loss of distributed compute | LOW |
| inference-proxy: no health dashboard | Blind to which tier is serving | LOW |

---

## 2. Target Architecture

```
hermes-agent (Telegram bot)
    └── inference-proxy:11435
            ├── T1: Windows GPU Ollama:11434    ← primary (native /api/chat) ~0.4s
            ├── T2: Pi rari1 (100.120.191.1)    ← fallback 1, nemotron-mini:latest, 90s timeout
            │   Pi rari2 (100.87.225.89)        ← fallback 1b, nemotron-mini:latest, 90s timeout
            ├── T3: Mac Local Ollama:11434       ← fallback 2 (/v1/ compat, CPU ~90s)
            └── T4: Kimi Cloud API               ← fallback 3 (Moonshot — needs API key renewal)

sapphire_dispatch (plugin router)
    ├── T0: Nemotron GPU (free, via inference-proxy)
    ├── T1: Kimi Cloud HTTP API (replaces CLI, no auth issues)
    ├── T2: Claw-code (Claude API, 300K/day)
    └── T3: Claude API direct (200K/day)

~/Code/kimi-tools/
    ├── kimi_client.py    ← Moonshot HTTP client (OpenAI-compat)
    ├── models.py         ← Kimi model catalog
    └── __init__.py
```

---

## 3. Implementation Plan

### Phase 1: kimi-tools repo ✅ → In Progress
**Goal:** Replace brittle CLI dependency with a proper HTTP client.

Files to create:
- `~/Code/kimi-tools/__init__.py`
- `~/Code/kimi-tools/kimi_client.py` — OpenAI-compat HTTP client
- `~/Code/kimi-tools/models.py` — model catalog

**Kimi API Endpoints:**
- Direct Moonshot: `https://api.moonshot.cn/v1` (requires `MOONSHOT_API_KEY`)
- Via OpenRouter: `https://openrouter.ai/api/v1` (requires `OPENROUTER_API_KEY`, model: `moonshotai/kimi-k2.5`)

**Auth strategy:** Use OpenRouter as primary (key likely already set for hermes) with Moonshot direct as secondary.

### Phase 2: inference-proxy upgrade ✅ Complete
**Goal:** Add Kimi Cloud as 3rd tier fallback so hermes-agent never goes dark.

Changes to `services/inference-proxy/app.py`:
- Add `KIMI_CLOUD` endpoint config
- Add `_call_kimi_cloud()` function (OpenAI-compat HTTP)
- Extend `do_POST()` fallback chain: GPU → Mac → Kimi Cloud
- Add `kimi-cloud` to health tracking dict
- Expose Kimi Cloud status in `/health` endpoint
- Add Pi stub (`PI_OLLAMA`) with `enabled: false` guard

**Model routing for Kimi Cloud:**
- `kimi`, `kimi-cloud` → `moonshot-v1-128k` (largest context)
- `cloud` → `moonshot-v1-32k` (balanced)

### Phase 3: router.py T1 upgrade ✅ → In Progress
**Goal:** Replace Kimi CLI subprocess with HTTP API call.

Changes to `plugins/claw-sapphire/lib/router.py`:
- Import `kimi_client` from `~/Code/kimi-tools/`
- Replace `execute_t1()` subprocess call with `kimi_client.complete()`
- Parse real token counts from API response (not TokenUsage output blocks)
- Remove `KIMI_BIN` dependency

### Phase 4: Configuration
**hermes-agent config additions:**
- Add `kimi-k2.5` to custom provider model list
- Document Kimi Cloud fallback in config comments

**Environment variables needed:**
```bash
# ~/.hermes/.env or ~/.sapphire/.env
MOONSHOT_API_KEY=<from platform.moonshot.cn>    # direct Kimi API
# OR (if using OpenRouter already):
OPENROUTER_API_KEY=<already set for hermes>     # via OpenRouter
```

---

## 4. Pi Tier — Active Production (2026-04-14)

Both Pis are live inference nodes on the Tailscale mesh:

| Node | IP | Status | Models | Agent |
|------|-----|--------|--------|-------|
| rari1 | 100.120.191.1 | ✅ ONLINE | nemotron-mini:latest, smollm2:1.7b, qwen2.5:0.5b, qwen3:0.6b | market-watchdog :19001 |
| rari2 | 100.87.225.89 | ✅ ONLINE | nemotron-mini:latest, nemotron-mini:4b, gemma2:2b, qwen2.5:0.5b, smollm2:1.7b, qwen3:0.6b | health-monitor :19002 |

```python
# inference-proxy — Pi T2 tier (both enabled)
PI_RARI1 = "http://100.120.191.1:11434"
PI_RARI2 = "http://100.87.225.89:11434"
PI_DEFAULT_MODEL = "nemotron-mini:latest"
PI_TIMEOUT = 90  # seconds (cold load ~72s on ARM)
```

LaunchAgent plist (com.sapphire.inference-proxy):
- `PI_RARI1_ENABLED=1` ✅
- `PI_RARI2_ENABLED=1` ✅

Notes:
- Cold model load on ARM takes ~72s (`load_duration=67.4s`). 90s timeout is sufficient.
- rari1 SSH port 22 refused — needs physical access to start sshd. Manage via Tailscale HTTP API only.
- rari2 local: 192.168.1.21, user: rari. ProtonVPN (proton0) breaks internet if tunnel dies.
- Health-monitor agent on rari2 checks 127.0.0.1-bound services as "down" — expected (security posture).

---

## 5. Token Budget (updated)

| Tier | Agent | Budget/day | Cost |
|------|-------|-----------|------|
| T0 | Nemotron GPU | ∞ unlimited | Free |
| T1 | Kimi Cloud API | 500K tokens | ~$0.015/1K (kimi-k2.5) |
| T2 | Claw-code | 300K tokens | ~$0.003/1K (Claude Haiku) |
| T3 | Claude API | 200K tokens | ~$0.015/1K (Claude Sonnet) |

---

## 6. Rollback Plan

If Kimi Cloud fallback causes issues in inference-proxy:
```bash
# Set env var to disable Kimi Cloud fallback
KIMI_CLOUD_ENABLED=false launchctl kickstart -k gui/$(id -u)/com.sapphire.inference-proxy
```

All changes are additive — existing Windows GPU → Mac Local path unchanged.

---

## 7. Implementation Status

| Component | File | Status |
|-----------|------|--------|
| kimi-tools repo | `~/Code/kimi-tools/` | ✅ Created |
| Kimi Cloud HTTP client | `kimi-tools/kimi_client.py` | ✅ Done |
| Model catalog | `kimi-tools/models.py` | ✅ Done |
| inference-proxy Kimi tier | `services/inference-proxy/app.py` | ✅ Done |
| Permanent API key auth | `inference-proxy/app.py:_call_kimi_cloud` | ✅ Done |
| Sensitivity classifier | `inference-proxy/app.py:_is_sensitive` | ✅ Existing |
| router.py T1 HTTP API | `plugins/claw-sapphire/lib/router.py:_kimi_http` | ✅ Done |
| Pi tier T2 (rari1 + rari2) | `inference-proxy/app.py` (PI_RARI1/PI_RARI2) | ✅ Active — nemotron-mini:latest, 90s timeout |

## 8. Activation Steps

To activate Kimi Cloud (takes 2 minutes):

```bash
# Option A: Moonshot direct (no markup, get key from platform.moonshot.cn)
echo "MOONSHOT_API_KEY=sk-..." >> ~/.sapphire/.env

# Option B: OpenRouter (OPENROUTER_API_KEY likely already set for hermes)
# No action needed — inference-proxy reads it from env automatically

# Then restart inference-proxy to pick up the new env var:
launchctl kickstart -k gui/$(id -u)/com.sapphire.inference-proxy

# Verify Kimi Cloud is now armed:
curl -s http://127.0.0.1:11435/health | python3 -m json.tool | grep kimi
```

Expected health output after activation:
```json
"kimi-cloud": "healthy",
"kimi_cloud": {
    "enabled": true,
    "moonshot_key": true,
    "openrouter_key": false
}
```

To test hermes-agent Kimi Cloud fallback (simulate both local nodes down):
```bash
# Temporarily block local Ollama:
sudo pfctl -e && echo "block out proto tcp to 127.0.0.1 port 11434" | sudo pfctl -f -

# Send a message to hermes via Telegram — it should route to Kimi Cloud
# Check inference-proxy logs:
tail -f /tmp/inference-proxy.log | grep kimi-cloud

# Restore local Ollama:
sudo pfctl -d
```
