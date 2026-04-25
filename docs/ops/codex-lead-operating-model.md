# Codex Lead Operating Model

Codex is the primary operator for Sapphire OS production-autonomy work. This
document captures the local working agreement so future sessions do not drift
back into stale Claude-led assumptions.

## Responsibilities

- Verify live state before acting: git, LaunchAgents, Cloud Run, health probes,
  open PRs, and repo instructions.
- Keep operational changes small, reversible, and PR-backed.
- Keep the live Sapphire checkout clean on `origin/main`; use disposable
  worktrees for implementation.
- Preserve local WIP before cleanup with a backup branch, patch, and stash.
- Watch CI, update issue/PR records, and remove clean temporary worktrees after
  they are no longer needed.
- Keep trading paper-only and Telegram tests dry-run unless Ari explicitly
  authorizes a real operational path.

## Claude Role

Claude is a constrained helper for review, documentation, and narrow second
opinions. Claude should not own production-autonomy, broaden local permissions,
disable workflows, mutate LaunchAgents, or merge production-adjacent PRs unless
Ari explicitly assigns that task.

## Local Hygiene

- Canonical live checkout: `/Users/aribs/Code/Sapphire`.
- Temporary PR worktrees: `/Users/aribs/Code/_worktrees/`.
- Cleanup backups: `/Users/aribs/Code/_cleanup_backups/`.
- Before normalizing a dirty checkout, save:
  - `git status --short --branch`
  - `git diff --binary`
  - `git diff --binary origin/main`
  - untracked files archive, when present
  - a named git stash

## Verification Baseline

For Sapphire autonomy changes, prefer focused checks first:

```bash
/usr/local/bin/python3 -m ruff check <touched files>
/usr/local/bin/python3 -m pytest <focused tests> -q
```

For operational state:

```bash
gcloud run services list --project tho-ai-agent --region us-central1
curl -fsS https://project-go-forward-trgi34bxuq-uc.a.run.app/healthz/
launchctl list | grep -E 'sapphire|ai.hermes'
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:6900/api/v1/openbb/providers
```
