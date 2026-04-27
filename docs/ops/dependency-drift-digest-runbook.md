# Dependency Drift Digest Runbook

Run by the cloud routine **Sapphire dependency drift digest** (cron
`0 12 * * 3`, 12:00 UTC Wednesday = 06:00 America/Denver). Also the
manual fallback if the routine is paused.

## Goal

Survey the open Dependabot PRs against `arigatoexpress/Sapphire`,
classify them by impact (security / major / minor / patch / grouped),
and open a single weekly issue summarizing what is waiting for human
attention. Complements the existing `dependency-security-scan` Claude
scheduled task by triaging, not scanning.

## Critical Safety

- **Read-only.** Do not merge any Dependabot PR, do not close any PR,
  do not push any branch, do not modify any tracked file.
- **One issue per week, idempotent.** If an open issue with label
  `dependency-drift-digest` already exists with this week's
  ISO-week stamp in its body, exit 0 silently — do not open a second
  one.
- **Never read** any secret, env file, or credentials. The runbook
  only consumes `gh api` PR metadata.
- **No emojis** in titles, branches, commits, or issue bodies.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit and
   log "no gh auth, skipping".

2. Compute the current ISO week stamp:
   ```bash
   WEEK=$(date -u +'%G-W%V')
   ```
   Example: `2026-W18`.

3. Idempotency check:
   ```bash
   gh issue list --state open --label dependency-drift-digest \
     --search "$WEEK" --json number,title,body --limit 5
   ```
   If any result contains `iso_week=$WEEK` in its body, exit 0
   silently.

4. Fetch open Dependabot PRs:
   ```bash
   gh pr list --state open --author "app/dependabot" \
     --json number,title,labels,createdAt,headRefName,mergeStateStatus,isDraft \
     --limit 100 > /tmp/dep-prs.json
   ```

5. Classify each PR by reading its title (Dependabot's title format is
   stable: `chore(deps): bump <pkg> from <ver-a> to <ver-b>`):
   - **Security**: title or labels include `security`.
   - **Major**: version bump where major component changes (e.g.,
     `1.x.y` → `2.0.0`).
   - **Minor**: minor bump (`1.2.x` → `1.3.0`).
   - **Patch**: patch bump (`1.2.3` → `1.2.4`).
   - **Grouped**: title contains `bump the <group> group with` —
     these are batched per `.github/dependabot.yml`.

6. For each class, count and identify the oldest PR by `createdAt`.

7. Check repository workflow / CI status indicators:
   - `gh pr checks <pr-number>` for the top 5 oldest PRs to see if
     hosted checks have completed (or are skipped under the
     SAPPHIRE_RUNNER no-spend gate).
   - Note any PR with `mergeStateStatus == "DIRTY"` — those need
     rebase before merge.

8. Open the digest issue:
   - Title: `Dependency drift digest: <WEEK> (<TOTAL> open PRs)`.
   - Labels: `dependency-drift-digest`, `chore`.
   - Body sections (markdown):
     1. `## Summary` — total open PRs, count per class.
     2. `## Security PRs` — table: number, title, age (days), checks
        status, suggested action ("merge ASAP if checks pass").
     3. `## Major-version PRs` — table: same columns + "review for
        breaking changes" recommendation.
     4. `## Minor / Patch / Grouped` — counts only, plus the 3 oldest
        in each class.
     5. `## Stale-rebase candidates` — PRs with `mergeStateStatus ==
        "DIRTY"` older than 14 days.
     6. `## ISO week stamp` — single line `iso_week=<WEEK>`. Used by
        step 3 for idempotency.
     7. `## Suggested next action` — one short sentence: "Land the
        security PRs first; batch-merge minor/patch where checks pass;
        rebase stale-DIRTY PRs older than 14 days."

9. Print a one-line status summary to stdout:
   `dependency-drift-digest: <TOTAL> PRs across <N classes>, issue #<num>`.

## Required tools

`Bash`, `Read`, `Glob`, `Grep`, plus `gh` on PATH. No write/edit tools.

## Out of scope

- Actually merging Dependabot PRs. Sapphire policy requires human
  review for non-grouped major-version bumps; the digest just surfaces
  them.
- CVE database lookups. The existing `dependency-security-scan` Claude
  task and OSV.dev workflow cover that lane.
- Dependabot config changes. Repo-side `dependabot.yml` is the source
  of truth; PRs to change cadence should go through normal review.
