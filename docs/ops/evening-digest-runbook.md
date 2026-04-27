# Evening Digest Runbook

Run by the cloud routine **Sapphire evening digest** (cron `0 0 * * *`,
00:00 UTC = 18:00 America/Denver). Also the manual fallback if the
routine is paused.

## Goal

Summarize the day's repo-side activity in a single GitHub issue: what
merged, what landed in `main`, what's in flight as open PRs, what
newly-failing or newly-stale signals appeared. Replaces the previously
stale local Claude scheduled task `evening-digest` whose dispatch
became unreliable.

## Critical Safety

- **Read-only.** No PR opened, no branch pushed, no file modified.
- **One issue per UTC day, idempotent.** Compute today's UTC date stamp
  (`YYYY-MM-DD`) and refuse to re-open if an open issue with
  `digest_date=<DATE>` is already present.
- **Repo-side only.** Do not query trading data, paper trading state,
  market signals, or any local Sapphire `data/` artifacts (the cloud
  env doesn't have them and they're high-noise anyway).
- **No emojis** in titles, branches, commits, or issue bodies.
- **Concise.** Cap the body at ~600 words. The digest's value is at-a-
  glance scannability, not exhaustiveness.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit and
   log "no gh auth, skipping".

2. Compute today's UTC date stamp:
   ```bash
   TODAY=$(date -u +'%Y-%m-%d')
   ```

3. Idempotency check:
   ```bash
   gh issue list --state open --label evening-digest \
     --search "$TODAY" --json number,title,body --limit 5
   ```
   If any result contains `digest_date=$TODAY` in its body, exit 0
   silently.

4. Collect today's merged PRs:
   ```bash
   gh pr list --state merged --search "merged:>=$TODAY" \
     --json number,title,author,mergedAt,labels,additions,deletions --limit 50 \
     > /tmp/digest-merged.json
   ```

5. Collect today's commits to `main`:
   ```bash
   gh api 'repos/arigatoexpress/Sapphire/commits?since='$TODAY'T00:00:00Z' \
     --jq '.[] | {sha: .sha[0:8], message: (.commit.message | split("\n")[0]), author: .author.login // .commit.author.name, date: .commit.author.date}' \
     > /tmp/digest-commits.json
   ```

6. Collect open PR snapshot:
   ```bash
   gh pr list --state open \
     --json number,title,author,createdAt,labels,mergeStateStatus,isDraft --limit 30 \
     > /tmp/digest-open-prs.json
   ```
   Classify into:
   - `READY` (not draft, mergeStateStatus = CLEAN)
   - `BLOCKED` (mergeStateStatus = DIRTY or BEHIND)
   - `DRAFT`

7. Collect open issues snapshot, grouped by label:
   ```bash
   gh issue list --state open --json number,title,labels,createdAt --limit 50 \
     > /tmp/digest-open-issues.json
   ```
   Group by primary label; surface counts only (not full lists).

8. Newly-stale signals — check the open issues for any with the labels
   we know are signal-driven from cloud routines:
   ```
   factory-test-guardian, dependency-drift-digest, threat-intel-sweep,
   evening-digest, mission-digest, github-discovery
   ```
   If any of those labels has an issue created today that we have NOT
   already mentioned in another digest, include a one-line callout.

9. Open the digest issue:
   - Title: `Evening digest: <TODAY>`
   - Labels: `evening-digest`, `chore`.
   - Body sections:
     1. `## Summary` — counts: merged today, commits to main, open PRs
        (READY/BLOCKED/DRAFT split), open issues by label.
     2. `## Merged today` — bulleted list: `#<N> <title> (+<adds>/-<dels>)`.
     3. `## Commits to main today` — bulleted list: `<sha> <message>`.
     4. `## Open PRs ready for review` — bulleted list of READY only.
     5. `## Stuck/blocked PRs` — list of BLOCKED, age in days.
     6. `## New routine signals` — any of the labels from step 8 with
        issues created today.
     7. `## Digest date` — single line `digest_date=<TODAY>`.

10. Print a one-line status summary to stdout:
    `evening-digest: <merged> merged, <commits> commits, <ready> READY, issue #<num>`.

## Required tools

`Bash`, `Read`, `Glob`, `Grep`, plus `gh` on PATH. No write/edit tools.

## Out of scope

- Trading P&L, paper portfolio, signals, regime status. Those belong in
  a separate trading-digest runbook (out of scope here).
- Cross-repo digest (THO, regional-intel-workbench, claw-code, etc.).
  This digest is Sapphire-only by design; cross-repo can be a separate
  runbook.
- Telegram delivery. The digest is the issue; subscribe to issue events
  for notification routing.
