---
source: local-export
date: 2026-08-06
type: plant-status
topics: [bridge, plant-wire, launchagent, receipt]
title: Plant grok-bridge sync wired
---

# Plant wire-up receipt

Per `docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md` §3 checklist — plant
side is green.

## What landed

- `~/ops-state/finish-line/scripts/sync_grok_web_exports.sh` replaced with a
  thin wrapper (`exec bash ~/Code/Sapphire/scripts/ops/sync_grok_web_exports.sh
  "$@"`) delegating to the canonical monorepo script per §4 ownership rules.
  Previous standalone version kept alongside as `.bak-20260806`.
- `--dry-run` verified (18 would-copy, 2 skipped: README.md/MANIFEST.json).
- Live sync run: `pull=1 copied=18 skipped=2 failed=0` — confirmed present in
  `~/Knowledge/0-Inbox/grok-web/`.
- `publish_operator_feeds.py` chained and ran (`ideas=27 stories=25 marks=6`).
- `infra/launchagents/com.sapphire.grok-web-bridge.plist` added (30 min
  `StartInterval`, `RunAtLoad=true`, `ThrottleInterval=300`) and loaded via
  `launchctl load` — densify beat is now scheduled, not manual-only.
- `MANIFEST.json` refreshed via `grok_bridge_status.py --write-manifest`;
  `--check` passes (all required topic hints present).
- Smoke: plant deck `:8100` → 200, API `:8099/healthz` → `{"status":"ok",...}`.

## Also (separate lane — mac-bridge, port 19998)

Unrelated to this file-sync lane but shipped the same session:
`services/grok-bridge/` — an HTTP front door to the Mac's authenticated `grok`
CLI session, `GET /health` returns `mode: "mac-bridge"`. See
`2026-08-06_grok-mac-bridge-live.md` for detail. `GROK_BRIDGE_URL` exported in
`~/.zshrc`.

## Not touched

Free-reign, L2 ARM, and money paths — out of scope for this lane, untouched.

## Next

- `~/ops-state/finish-line/scripts/publish_operator_feeds.py` still owns feed
  publish; no change made there.
- LaunchAgent will self-heal on next boot (`RunAtLoad=true`); no cron/manual
  trigger needed going forward.
