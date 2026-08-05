# Grok Web ↔ Local CLI Knowledge Bridge

This folder is the **shared store** that lets Grok web (chat, research, trade ideas, architecture notes) and the local Grok CLI / densify / Ralph loop exchange knowledge without manual copy-paste.

## Purpose

- **Web → Local**: High-value outputs from Grok web sessions are pushed here as timestamped Markdown files.
- **Local → Web** (optional, phase 2): Local densified plant reports, new research notes, or operator summaries can be pushed back under the same path (or a `local-exports/` sibling) so the web agents stay current with plant state.

## Conventions

| Item | Rule |
|------|------|
| Filename | `YYYY-MM-DD_HHMM_topic-slug.md` or `YYYY-MM-DD_topic-slug.md` |
| Commit message | `web-export: <short description> [YYYY-MM-DD]` or `local-export: ...` |
| Frontmatter | Optional YAML with `source`, `date`, `topics`, `type` (trade-idea, research, architecture, chat-summary, etc.) |
| Content | Clean Markdown. Prefer structured sections over raw chat dumps. |

## Local Consumption

Recommended local flow (implemented by a free-reign / Ralph loop):

1. `git pull` (or sparse-checkout of `data/grok-web-exports/`) inside the Sapphire clone.
2. Copy new or changed `.md` files into `~/Knowledge/0-Inbox/grok-web/`.
3. Trigger densify / plant / Ralph processing on the inbox folder.
4. (Optional) After densify, push any new local knowledge back here.

## Why this path?

Per `STRUCTURE.md`, `data/` is the correct home for tracked reference data. Hot runtime state stays gitignored. This keeps the bridge inside the existing monorepo instead of a separate private repo.

## Complementary stores

- **Google Drive**: External news ingest, long-form reports, media assets (via daily-holistic-ingest skill).
- **Notion** (optional): Structured trade idea DB, status boards.

Git remains the zero-manual, versioned, bidirectional bridge for knowledge that both sides need.
