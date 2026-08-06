# Grok Bridge ↔ Sapphire Integration

## Purpose

Expose SuperGrok (CLI OIDC or Mac Safari bridge) as a **bounded research worker** for Sapphire agents — never as a broker, signer, or killswitch authority.

## Transports (priority)

1. **mac-bridge** — `GROK_BRIDGE_URL` (e.g. `http://127.0.0.1:19998` or tunnel) when Safari inject is live on the Mac.
2. **supergrok-oidc** — Grok CLI session in `~/.grok/auth.json` → `https://api.x.ai/v1`.
3. **xai-api** — `XAI_API_KEY` if injected.
4. **away-sim** — deterministic local fallback (tests / offline).

## Client

```python
from lib.intel.grok_bridge_client import GrokBridgeClient

client = GrokBridgeClient(base_url="http://127.0.0.1:8080")  # remote lab or tunnel
health = client.health()
if not health.get("ok"):
    raise RuntimeError("bridge down")
text = client.chat("Summarize funding skew risks for BTC perps in 40 words.", timeout=90)
```

Default `base_url` resolution:

1. `GROK_BRIDGE_APP_URL` (this app / remote lab)
2. `GROK_BRIDGE_URL` (classic Safari bridge host — chat at `/chat` not `/api/bridge/chat`)
3. `http://127.0.0.1:8080` with `/api/bridge/*` paths

## Allowed call sites

| Allowed | Forbidden |
|---------|-----------|
| Research briefs, thesis critique, Pine review, doc distill | Order placement, pause clear, credential mutation |
| Paper strategy commentary | Telegram live send without approval |
| Overnight agent reports | Silent retries that expand scope |

## Health gate pattern

```bash
mode=$(curl -sf "$BRIDGE/api/bridge/health" | jq -r '.mode')
ok=$(curl -sf "$BRIDGE/api/bridge/health" | jq -r '.ok')
test "$ok" = "true" || exit 1
```

## Security

- Tokens never leave server-side OIDC loader / env.
- Bridge responses are **claims** until written to local evidence with content hash.
- Rate-limit: user-initiated or scheduled with max_tokens caps; no per-keystroke.
