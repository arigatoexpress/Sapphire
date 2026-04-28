# ADR 0002 — Worktree-per-lane for parallel autonomous agents

- **Status**: accepted
- **Date**: 2026-04-26
- **Authors**: Ari (operator), Sapphire ops
- **Related**: ADR 0001, ADR 0010

## Context

Sapphire's autonomous push runs 3-9 parallel agents during overnight tranches.
Early attempts had agents share a single canonical checkout
(`~/Code/Sapphire`), and several pathologies emerged:

1. **Race conditions on `git status` / `git diff`** — when two agents both
   edited the same file or staged work concurrently, the checkout drifted
   into half-staged states that broke local verification.
2. **Module cache pollution** — pytest writes `__pycache__/` directories
   below `lib/`, `services/`, and `plugins/`. Two agents running pytest
   simultaneously over different changes invalidated each other's caches.
3. **Branch-switching collisions** — when one agent ran `git checkout -b`
   for its lane while another agent's lane was mid-test, pytest collection
   sometimes picked up the wrong tree.
4. **PR-creation race** — `gh pr create` from a checkout with uncommitted
   work from another agent leaked unintended changes into the PR.

The 2026-04-26 multi-tranche push first hit all four pathologies in one
night. The worktree-per-lane discipline emerged the next day.

## Decision

Every parallel autonomous agent runs in an **isolated git worktree** at
`~/Code/_worktrees/sapphire-<branch>`. Canonical (`~/Code/Sapphire`) stays
on `main` and is the operator's working copy.

**Setup pattern** (every megaprompt's step 1):

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git worktree add /Users/aribs/Code/_worktrees/sapphire-<branch> \
    -b <branch-prefix>/<lane-name> origin/main
cd /Users/aribs/Code/_worktrees/sapphire-<branch>
```

**Cleanup**: when the lane PR merges, the worktree is removed by the
operator (`git worktree remove ...`) or the safe-merge wrapper.

**Conflict surface**: lanes are scoped so that two parallel worktrees do
not need to edit the same file. ADR 0007 (correlator deterministic rules
+ LLM narrative split) is one example of the lane-fencing discipline.

## Consequences

- **Positive**:
  - Zero observed cross-agent collisions across Tranches 2-5 (≥ 60 PRs).
  - Each agent's verification (`pytest`, `ruff`) runs against its own
    `__pycache__/` and never sees stale state from a sibling.
  - Operator can `cd ~/Code/Sapphire` and inspect any of the in-flight
    worktrees from a clean canonical.
  - `gh pr create` only sees the worktree's own commits.
- **Negative**:
  - Disk cost: each worktree is a full checkout (~1.5 GB on Sapphire as
    of 2026-04-29). Overnight 9-lane tranches consume ~14 GB in
    `_worktrees/`. Cleanup discipline matters.
  - Initial setup is slower than `git checkout -b` against canonical.
  - Some tools (notably `gh pr merge` from a non-canonical worktree) trip
    over multi-worktree state — see `feedback_multi_repo_workflow.md` for
    the `gh api -X PUT` workaround.
  - LaunchAgents that bind to repo paths (e.g. `WorkingDirectory` in
    plists) point at canonical only — worktrees cannot replace canonical
    in the running production checkout.
- **Neutral**:
  - Pre-commit hooks fire in worktrees the same way they fire in canonical.
  - CODEOWNERS gates apply to PRs from worktrees identically.

## Alternatives Considered

- **One canonical, sequential agents**: rejected — sequential autonomous
  work caps throughput at ~1 PR/h; tranches need 8 PRs/h to stay
  competitive with Codex's overnight pace.
- **Container-per-lane (Docker)**: rejected — adds ~30s/lane bringup,
  complicates secret access, and worktrees solve 95% of the problem at
  zero overhead.
- **Branch-per-lane in canonical with explicit `git stash` discipline**:
  rejected — observed too fragile in practice; agents skip stash steps
  under load.

## References

- Memory entry: `~/.claude/projects/-Users-aribs/memory/feedback_multi_repo_workflow.md`
  (sections "Worktree per lane" and "Use `gh api -X PUT` from a non-canonical
  worktree")
- Force-multiplier playbook: `docs/process/claude-force-multiplier-playbook-2026-04-29.md`
- Cleanup convention: `git worktree remove ~/Code/_worktrees/sapphire-<branch>`
  after PR merge
