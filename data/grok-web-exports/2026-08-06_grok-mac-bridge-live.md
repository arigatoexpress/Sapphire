---
source: local-export
date: 2026-08-06
type: architecture
topics: [bridge, mac-bridge, grok-cli, port-19998]
title: Mac Safari/CLI bridge (BR-04) implemented and live
---

# Mac bridge (port 19998) — implemented

Resolves alpha ledger **BR-04** ("Mac Safari bridge unreachable remotely /
known"): the bridge described in `2026-08-05_bridge-setup.md`'s transport
priority did not exist as code anywhere (Sapphire repo, `~/ops-state`, or the
`grok` CLI itself — it has no `serve`/bridge subcommand). Built it.

## What shipped

`services/grok-bridge/` in this repo — a stdlib `http.server` service (no new
deps, matches `services/inference-proxy` conventions):

- `GET /health` → `{"mode": "mac-bridge"}` once the `grok` CLI is on PATH and
  `~/.grok/auth.json` (SuperGrok OIDC session) exists. No network call, so
  health probes don't spend Grok cost.
- `POST /v1/query {"prompt": "..."}` → shells to `grok -p <prompt>
  --output-format json` (argv list, no shell injection surface) and returns
  its JSON verbatim.
- `away-sim` fallback mode (`GROK_BRIDGE_SIM=1`) for offline tests.
- Optional `GROK_BRIDGE_TOKEN` bearer auth for `/v1/query` if ever bound
  beyond `127.0.0.1` (Tailscale reachability for remote sandboxes/Cloud
  Shell).

Verified live 2026-08-06: `/health` returns `mode: "mac-bridge"`, and an
end-to-end `/v1/query` round-trip through the real `grok` CLI returned in
~4s.

`GROK_BRIDGE_URL=http://127.0.0.1:19998` exported in `~/.zshrc` for local
consumers. LaunchAgent plist included
(`services/grok-bridge/launchagent/com.sapphire.grok-bridge.plist`) but not
yet installed — currently running as a foreground/background process this
session, not persisted across reboot.

## Still open

- Not yet reachable from remote sandboxes (Cloud Shell) — that needs a
  Tailscale tunnel to the Mac plus `GROK_BRIDGE_TOKEN` set before widening
  the bind address past `127.0.0.1`.
- LaunchAgent not installed — `/health` will stop responding on reboot until
  `launchctl load` is run.
- No consumer code anywhere yet implements the full transport-priority
  fallback chain (mac-bridge → OIDC direct → XAI_API_KEY → away-sim) — this
  service is only the mac-bridge leg itself.

See `services/grok-bridge/README.md` for full usage.
