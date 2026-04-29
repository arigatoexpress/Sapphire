# Showcase Unification Closeout — 2026-04-29

## Objective

Make the current Sapphire ecosystem easier to show: polished front doors,
professional READMEs, durable documentation, and a clear boundary between what
has landed and what still needs human approval.

No live trading, Telegram sends, secret rotation, data deletion, or production
infrastructure mutation was performed.

## Landed

### Sapphire OS

- PR: <https://github.com/arigatoexpress/Sapphire/pull/481>
- Status: merged to `main`
- Head: `56855995 feat(dashboard): add unified showcase front door [skip ci]`
- Main outcome: authenticated `/showcase` dashboard route that acts as a
  unified product front door for the autonomy stack.

The route curates dashboard pages, operating loops, safety posture, companion
repos, demo paths, and buyer/operator/engineer views without activating any
live execution behavior.

### Regional Intelligence Workbench

- PR: <https://github.com/arigatoexpress/regional-intel-workbench/pull/11>
- Status: merged to `main`
- Head: `6bfd111 docs: add regional showcase docs index [skip ci]`
- Main outcome: the already polished README now points to a compact docs index
  and `docs/SHOWCASE.md` with demo path, CLI snippets, visual assets, and
  provenance guardrails.

### Project Go Forward / THO

- PR: <https://github.com/arigatoexpress/Project-Go-Forward/pull/27>
- Status: open draft by repo policy
- Branch: `docs/showcase-readme`
- Main outcome: polished THO showcase README, SVG hero card,
  `docs/SHOWCASE.md`, docs index update, and stale Notion-integration wording
  cleanup.

This repo auto-deploys from `main`, and its `AGENTS.md` requires human approval
before merge. The PR is clean and ready for review, but intentionally not
merged by Codex.

## Verification Snapshot

Sapphire PR #481 recorded:

- `pytest tests/unit/test_dashboard_showcase_routes.py tests/unit/test_dashboard_public_demo_readiness.py -q`
- broader dashboard route suite: 66 passing tests
- `python scripts/ops/test_inventory.py --check-readme`
- `python scripts/ops/dashboard_public_demo_readiness.py --no-write --pretty`
- `python scripts/validate_tool_registry.py`
- `python scripts/ops/production_readiness_sweep.py --no-external`
- Playwright smoke of `/showcase` with no console errors

Regional PR #11 recorded:

- `uv run --python 3.11 python -m unittest discover -s tests -v`
- `pre-commit run --files README.md docs/README.md docs/SHOWCASE.md`
- `git diff --check`
- local UI smoke against `127.0.0.1:8768`

PGF PR #27 recorded:

- live `/health`, `/healthz/`, and inventory-context probes
- `python3 -m pytest tests/test_healthz.py tests/test_api_v1.py -q`
- `pre-commit run --files ...`
- `npm --prefix frontend ci`
- `npm --prefix frontend run build`
- SVG parse check
- `git diff --check`

## Current Follow-Ups

- Human review and merge decision for PGF PR #27.
- Leave PGF draft PRs #25 and #26 untouched unless their owners ask for
  consolidation.
- Preserve Sapphire `.claude/worktrees/*`, including the locked Hyperliquid
  worktree, until explicitly triaged.
- Existing PGF npm audit findings remain pre-existing dependency hygiene, not a
  showcase-docs regression.
