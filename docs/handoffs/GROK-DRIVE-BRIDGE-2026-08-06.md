# Grok web × Google Drive densify bridge

**Date:** 2026-08-06  
**Drive root:** [Sapphire / Grok Bridge](https://drive.google.com/drive/folders/1CQiAUpKC5tbK166XOKEF2SgvbDHbheoz)

## Architecture

```text
Grok monorepo (github)
  data/grok-web-exports/     ──┐
  docs/handoffs/             ──┼─► data/grok-drive-pack/  ──► Google Drive
  projects/grok/*            ──┘         │                    Sapphire/Grok Bridge/
                                         │                    01-exports …
  plant densify 30m ──► Knowledge inbox  │
  Grok connector ──► list/search/read Drive; create folders
```

## What we set up

| Lane | Drive folder | Content |
|---|---|---|
| 01-exports | densify markdown | grok-web-exports |
| 02-handoffs | Gemini/Claude/Grok prompts | docs/handoffs |
| 03-briefs-and-rules | SYSTEM_BRIEF, operating rules | public-safe JSON/MD |
| 04-audits | public surface audit, desk example | audits |
| 05-operator-index | INDEX.md | how to use |

Folder IDs: `projects/grok/data/drive_bridge_folders.json`

## Commands

```bash
python3 scripts/ops/grok_drive_pack.py --write
# Upload pack → Drive (plant): rclone / Drive desktop / connector file create when available
```

## Connector limits (Grok web)

Available now: **search, list, read, create folder, trash** — not bulk file create/upload in this connector set.  
So: monorepo builds pack; **plant/rclone** (or future upload tool) fills Drive; Grok chat **reads** Drive for operator context.

## Fences

- No wallets, balances, positions, SA keys, tokens  
- No trading authority via Drive  
- Secretish content auto-skipped by packer  

## Plant optional LaunchAgent

After pack works, thin wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/Code/Sapphire"
git pull --ff-only origin main || true
python3 scripts/ops/grok_drive_pack.py --write
# rclone sync data/grok-drive-pack/ "gdrive:Sapphire/Grok Bridge/" --exclude '.git/**'
```

Cadence: after densify or hourly — **not** a money path.
