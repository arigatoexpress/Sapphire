# Sapphire Branch and Stash Triage

Generated: 2026-04-28T03:46Z

Scope: read-only inventory from `/Users/aribs/Code/Sapphire`. No branches,
stashes, worktrees, or files were deleted.

## Summary

- Local branches: 98
- Branches with an upstream: 68
- Local-only branches: 30
- Branches already merged into `origin/main`: 3
- Stashes: 35
- Registered Sapphire worktrees after PR #342 cleanup: root checkout and
  `sapphire-robinhood-manual-order`
- Extra `_worktrees` directories not registered as git worktrees:
  `sapphire-claude-md-cloud-routines`, `sapphire-claw-plugin-schema`

Prefix counts:

| Prefix | Count | Initial read |
|---|---:|---|
| `audit` | 1 | Review before delete. Security/audit context may still matter. |
| `backup` | 13 | Preserve until Ari approves cleanup; these look like rescue snapshots. |
| `chore` | 14 | Many have remote tracking refs; compare PR merge status before pruning. |
| `ci` | 1 | Likely merged posture work, but verify remote PR before pruning. |
| `claude` | 11 | Good cleanup candidates after checking for active worktree/session links. |
| `codex` | 11 | Mostly tracked remote branches; verify merged PRs first. |
| `docs` | 10 | Some are recent status/handoff lanes; prune only after merged status check. |
| `experiment` | 1 | Preserve until session-recap work is intentionally retired. |
| `feat` | 13 | Several feature branches track old PR lanes; verify before pruning. |
| `fix` | 19 | Many track remotes; verify PR status before pruning. |
| `main` | 1 | Keep. |
| `os` | 1 | Old consolidation branch; likely archive candidate. |
| `research` | 1 | Preserve unless Ari no longer wants Layer B design history. |
| `test` | 1 | Verify PR/status before pruning. |

## Do Not Touch Yet

- `feat/robinhood-manual-order`: active dirty worktree at
  `/Users/aribs/Code/_worktrees/sapphire-robinhood-manual-order`, containing
  Robinhood manual-order docs/script/test WIP.
- Any `backup/*` branch without Ari approval.
- All 35 stashes. They are concentrated conflict/WIP snapshots from 2026-04-20
  through 2026-04-26 and should be reviewed, exported, or dropped only in a
  dedicated cleanup window.

## Branches Already Merged into `origin/main`

These are the only branches `git branch --merged origin/main` reported:

| Branch | Recommendation |
|---|---|
| `main` | Keep. |
| `backup/provenance-envelopes-wip-20260428T030520Z` | Candidate after confirming the backup has no unique WIP Ari wants. |
| `docs/control-tower-status-20260428` | Current branch; remove after this PR lands and local worktree is deleted. |

## Local-Only Branches

Local-only branches are higher risk because GitHub cannot be used as the only
source of truth for their state. Preserve or export before deleting.

| Branch family | Branches | Recommendation |
|---|---|---|
| Backup snapshots | `backup/codex-live-cleanup-20260425-133649`, `backup/feat-sapphire-pm-bot-pre-cleanup`, `backup/main-pre-origin-sync-2026-04-23`, `backup/provenance-envelopes-wip-20260428T030520Z`, `backup/sapphire-conflicting-qwen-rollback-wip-20260426`, `backup/sapphire-health-preflight-wip-20260426`, `backup/sapphire-qwen-*` | Keep until a follow-up compares unique commits and exports patches for anything not merged. |
| Claude work | `claude/bold-ptolemy-a009f5`, `claude/compassionate-babbage-6882ac`, `claude/eager-grothendieck-8d1c81`, `claude/preflight-key-handling` | Review against recent Claude transcript/activity before deletion. |
| Test/chore leftovers | `chore/alpha-agent-unit-tests`, `chore/contracts-security-review-2026-04-26`, `chore/inference-proxy-app-tests`, `chore/risk-and-decision-engine-tests`, `chore/robinhood-crypto-edge-tests`, `chore/test-coverage-audit-2026-04-26`, `chore/todo-triage-2026-04-26`, `chore/x402-and-foundry-tests` | Candidate batch after PR merge-status check and patch export. |
| Older Codex/experiment branches | `codex/pristine-phase1`, `codex/pristine-phase2`, `experiment/session-recap-2026-04-21`, `os/consolidation`, `research/bearish-asymmetry-layer-b-design` | Keep until Ari chooses whether these are historical references or cleanup targets. |

## Stash Inventory

The stash stack has 35 entries:

- 29 entries on `main` from 2026-04-26, mostly `sapphire conflicting qwen ...`
  WIP and backup snapshots.
- 2 entries on `codex/qwen36-mesh-routing`.
- 1 entry on `feat/service-supervisor`.
- 3 older Claude-chain entries from 2026-04-20.

Recommended next cleanup step:

1. Export each stash to a patch under a local ignored backup directory.
2. Group patches by likely file family: app, docs, tests, dashboard, mesh, chain.
3. Compare each group against current `origin/main`.
4. Drop only exact duplicates or superseded patches after Ari approves the
   candidate list.

## Proposed Follow-Up

Create a dedicated cleanup PR or local-only report that computes, for each
candidate branch:

- whether the branch has unique commits not reachable from `origin/main`,
- whether those commits touch forbidden or active-worktree paths,
- whether a GitHub PR exists and is merged/closed/open,
- whether a patch export exists for recovery.

No deletion should happen until that report exists.
