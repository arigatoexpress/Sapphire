# Grok web ↔ local plant bridge

**Canonical shared knowledge plane** for high-value trade ideas, research
distillations, chat summaries, and architecture notes between:

- **Grok web** (browser chats / research)
- **Grok CLI / densify / Ralph** (local plant on Ari's Mac)

## Path

```
data/grok-web-exports/     ← this folder (git-tracked reference data)
        ↓  sync_grok_web_exports.sh (densify + Ralph)
~/Knowledge/0-Inbox/grok-web/
        ↓  publish_operator_feeds.py
http://127.0.0.1:8100/     ← plant command deck
```

## Conventions

| Item | Rule |
|---|---|
| Filename | `YYYY-MM-DD_topic-slug.md` or `YYYY-MM-DD_HHMM_topic-slug.md` |
| Commit (web→local) | `web-export: <short desc> [YYYY-MM-DD]` |
| Commit (local→web) | `local-export: <short desc> [YYYY-MM-DD]` |
| Content | Clean structured Markdown — not raw chat dumps |
| Frontmatter | Optional YAML: `source`, `date`, `topics`, `type` |

## Flow v1 (live — unidirectional web→local)

1. Web (or any agent with write) adds timestamped `.md` here.
2. Local loop: `git pull` → copy new/changed `*.md` → `~/Knowledge/0-Inbox/grok-web/` (copy, never delete remote).
3. `publish_operator_feeds.py` mines inbox into operator-feeds → plant deck.

Script: `~/ops-state/finish-line/scripts/sync_grok_web_exports.sh`  
Hooked from: `densify_dream_plant.sh`, `ralph_plant_loop.sh`

## Flow v2 (optional — local→web)

Local densified outputs may land here with `local-export:` prefix commits so web
agents can read plant state. Enable when GitHub write path is authorized.

## Complementary

- Google Drive — external news ingest / large media
- Notion — optional structured trade DB
- Local session mines — `~/.grok/sessions`, `~/.codex` (prefer over web scrape)

## Operator

```bash
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
open http://127.0.0.1:8100/
```

Do **not** use :8098 / :8085. Canonical UI is :8100; API is :8099.

## Status (2026-08-05)

- Folder + sync loop **live on Mac** (densify / Ralph / overnight hooks).
- GitHub **MCP write** may still be 403 until connector re-auth (`contents:write`).
- Local `git push` from this machine is the fallback publish path.
