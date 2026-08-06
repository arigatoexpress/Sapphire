# grok-bridge

Local HTTP front door to the Mac's authenticated `grok` CLI session (SuperGrok
OIDC — see `~/.grok/auth.json`). Lets environments that can't invoke the
`grok` CLI directly (remote sandboxes, GCP Cloud Shell, other hosts reached
over Tailscale) get Grok answers through the Mac's live session instead of
needing their own `XAI_API_KEY`.

Fills the "Mac bridge" leg of the transport priority described in
`data/grok-web-exports/2026-08-05_bridge-setup.md` and the alpha ledger
`BR-02`/`BR-04` entries: **Mac bridge → SuperGrok OIDC direct → XAI_API_KEY →
away-sim**. This service *is* the Mac-bridge leg; it has one real backend
(shelling out to the local `grok` CLI) plus a sim fallback for offline tests.

## Run

```bash
python3 services/grok-bridge/app.py            # foreground, port 19998
bash services/grok-bridge/start.sh              # loads ~/.sapphire/secrets.env first
```

Install as a LaunchAgent for persistence across reboots:

```bash
cp services/grok-bridge/launchagent/com.sapphire.grok-bridge.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sapphire.grok-bridge.plist
```

## Config (env vars)

| Var | Default | Purpose |
|---|---|---|
| `GROK_BRIDGE_HOST` | `127.0.0.1` | Bind address. Set `0.0.0.0` only behind Tailscale, never a public interface. |
| `GROK_BRIDGE_PORT` | `19998` | Listen port. |
| `GROK_BRIDGE_TOKEN` | unset | If set, `/v1/query` requires `Authorization: Bearer <token>`. `/health` stays open. |
| `GROK_BRIDGE_SIM` | `0` | `1` forces `away-sim` mode (no live grok CLI calls) — for offline tests. |
| `GROK_BRIDGE_TIMEOUT_S` | `150` | Per-query subprocess timeout. |

`GROK_BRIDGE_URL` (e.g. `http://127.0.0.1:19998`) is the var **consumers** of
this bridge read to find it — it is not read by this service itself. Exported
in `~/.zshrc` on this Mac.

## Endpoints

- `GET /health` → `{"mode": "mac-bridge" | "away-sim" | "unavailable", ...}`.
  `mac-bridge` means the `grok` binary is on PATH *and* `~/.grok/auth.json`
  exists — a cheap local check, no network call, so health probes don't burn
  Grok API cost.
- `POST /v1/query` `{"prompt": "...", "model": "<optional>"}` → shells to
  `grok -p <prompt> --output-format json` via an argv list (no shell string,
  no injection surface) and returns its JSON verbatim plus `latency_ms`.

## Security

No public exposure by default (`127.0.0.1`). If bound wider for Tailscale
reachability, set `GROK_BRIDGE_TOKEN` — otherwise `/v1/query` is an
unauthenticated relay that spends real Grok API cost per call.
