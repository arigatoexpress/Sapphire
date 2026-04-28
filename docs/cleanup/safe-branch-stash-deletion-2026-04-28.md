# Safe Branch and Stash Deletion Execution - 2026-04-28

Scope: Agent B overnight cleanup for `/Users/aribs/Code/Sapphire`.

This pass executed only the deletion candidates that were provably safe from
live git state. Anything tied to an active worktree or with non-duplicated stash
content was left alone.

## Executed

Deleted one inactive local branch that was already reachable from `origin/main`:

| Branch | Reason |
|---|---|
| `backup/provenance-envelopes-wip-20260428T030520Z` | Listed by `git branch --merged origin/main`; not registered to any active worktree. |

Command:

```bash
git branch -d backup/provenance-envelopes-wip-20260428T030520Z
```

## Left Alone

The current merged-branch floor after deletion is:

| Branch | Reason left alone |
|---|---|
| `main` | Canonical checkout branch. |
| `fix/aiohttp-web-collection-agent-a` | Registered active worktree at `/Users/aribs/Code/_worktrees/sapphire-agent-a-collection`. |

No stashes were dropped. All 35 stash patches failed the conservative
"already present on main" reverse-apply check, so none qualified as
clearly-stale duplicates.

Stash verification command:

```bash
for ref in $(git stash list --format='%gd'); do
  if git stash show -p "$ref" | git apply --check --reverse - >/dev/null 2>&1; then
    echo "$ref present_on_main"
  else
    echo "$ref not_safe"
  fi
done
```

Result: every stash returned `not_safe`.

## Current Counts

- Local branches after deletion: 102
- Stashes after deletion: 35
- Registered Sapphire worktrees observed during this pass:
  - `/Users/aribs/Code/Sapphire`
  - `/Users/aribs/Code/_worktrees/sapphire-agent-a-collection`
  - `/Users/aribs/Code/_worktrees/sapphire-agent-c-performance-endpoints`
  - `/Users/aribs/Code/_worktrees/sapphire-trading-shadow-controller`

## Follow-Up

The remaining branch/stash cleanup needs a deeper export-and-compare pass, not
blind deletion. Recommended next command pattern:

```bash
git stash show -p "stash@{N}" > /tmp/sapphire-stash-N.patch
git log --oneline origin/main..BRANCH
git diff --stat origin/main...BRANCH
```

Drop only patches or branches whose contents are either exported for recovery or
proven duplicated on `origin/main`.
