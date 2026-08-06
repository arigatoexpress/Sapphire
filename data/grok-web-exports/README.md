# Grok Web ↔ Local Plant Knowledge Bridge

Shared, versioned store so **Grok web**, **Claude/Codex on plant**, and **Gemini on Cloud Shell** exchange knowledge without manual copy-paste.

## Pipeline

```text
Grok web / Cloud Shell / agents
        │  web-export: … commits
        ▼
data/grok-web-exports/*.md   ← this folder (git truth)
        │  sync_grok_web_exports.sh
        ▼
~/Knowledge/0-Inbox/grok-web/
        │  densify / Ralph / overnight
        ▼
publish_operator_feeds.py → plant deck :8100 / API :8099
```

## Scripts (monorepo)

| Script | Purpose |
|---|---|
| [`scripts/ops/sync_grok_web_exports.sh`](../../scripts/ops/sync_grok_web_exports.sh) | Copy new/changed exports → Knowledge inbox (never deletes sources) |
| [`scripts/ops/grok_bridge_status.py`](../../scripts/ops/grok_bridge_status.py) | Inventory + frontmatter check + optional `MANIFEST.json` |

Plant may still wrap via:

```bash
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
# should call or mirror the monorepo script after Claude densifies
```

## Conventions

| Item | Rule |
|------|------|
| Filename | `YYYY-MM-DD_topic-slug.md` (optional `HHMM_`) |
| Commit | `web-export: <desc> [YYYY-MM-DD]` or `local-export: …` |
| Frontmatter | `source`, `date`, `topics`, `type`, optional `title` |
| Content | Clean Markdown; structured sections over raw dumps |
| Staging | **Never** `git add -A` — stage explicit paths only |

### Recommended frontmatter

```yaml
---
source: grok-web   # or: local-export | grok-cli | cloud-shell | claude-plant
date: 2026-08-06
type: architecture # research | handoff | alpha | ops | plant-status | masterplan
topics: [bridge, free-reign]
title: Short title
---
```

### Structured trade ideas (when applicable)

`instrument` · `venue` · `size` · `thesis` · `falsifier` · `confidence` · `horizon` · `risk notes`

## Status

```bash
python3 scripts/ops/grok_bridge_status.py
python3 scripts/ops/grok_bridge_status.py --write-manifest
bash scripts/ops/sync_grok_web_exports.sh --dry-run
bash scripts/ops/sync_grok_web_exports.sh --pull   # on plant
```

Lane coordination: [`docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md`](../../docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md)

## Why this path?

Per `STRUCTURE.md`, `data/` holds tracked reference data. Hot runtime stays gitignored. Sparse-checkout friendly monorepo source of truth — not a second private repo.

## Complementary stores

- **Google Drive** — long-form reports / media
- **Notion** — human boards (optional)
- **ops-state** — live free-reign, killswitch, finish-line (not git-only)

Git remains the zero-manual, versioned bridge for knowledge both sides need.
