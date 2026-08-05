---
source: grok-web
date: 2026-08-05
topics: [knowledge-bridge, sapphire, cli, integration]
type: architecture
title: Grok Web ↔ Local CLI bridge setup
---

# Grok Web ↔ Local CLI bridge setup

## Goal

Eliminate manual file drops between Grok web and the local densify / Ralph loop by using the Sapphire monorepo as a shared, versioned store.

## Shared path

`data/grok-web-exports/` inside `arigatoexpress/Sapphire`.

Per STRUCTURE.md, `data/` is tracked reference data — correct home for the bridge (not hot runtime state).

## Conventions

- Filename: `YYYY-MM-DD_HHMM_topic-slug.md` or `YYYY-MM-DD_topic-slug.md`
- Commit: `web-export: <desc> [date]` or `local-export: ...`
- Frontmatter: source, date, topics, type, title

## Local loop

1. `git pull` (or sparse-checkout of this folder)
2. Copy new/changed `.md` into `~/Knowledge/0-Inbox/grok-web/`
3. Trigger densify / plant processing on inbox only
4. Optional phase-2: push densified notes back as `local-export:` commits

## Status (Aug 5)

- Architecture agreed; README + this sample landed via web connector after write re-auth.
- Free-reign / Ralph local loop should register pull → inbox → densify.
- Web automatic exports can now target this path with `contents:write`.

## This file

This file itself is the first export demonstrating the pattern.
