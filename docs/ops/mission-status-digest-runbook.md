# Sapphire Mission Status Digest Runbook

Executed by the scheduled remote agent **Sapphire mission status digest**
(claude.ai routine, cron `0 14 * * 1` — Mondays 14:00 UTC = 8:00 AM MDT).
Manual fallback: run the steps below from a fresh checkout of `main`.

## Goal

Produce a single Markdown digest summarising the state of the Sapphire mission for
the prior 7 days, posted as a GitHub issue under the `mission-digest` label so it
shows up in Ari's GitHub notifications and the issues feed.

## Critical Safety

- Read-only against the repo apart from one new GitHub issue per run.
- Do not touch any branch, do not open any PR, do not modify any file.
- Do not run pytest, ruff, or any data-mutating script.
- No emojis in the issue title or body.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no issue.

2. Compute the 7-day window in UTC: `since = (now - 7d).isoformat()`.

3. Collect inputs (each via `gh` or simple file reads, all read-only):

   a. **Soak progress** — read `infra/org-repos.yaml` to find every routine with
      `stage: soaking`. For each, read its `evidence_doc` (referenced as
      `docs/org/<routine>-shadow-soak-<date>.md`) and count rows in the
      `## Soak Log` table. Note `required_scheduled_successes` and how many
      cycles remain.

   b. **Open PRs** — `gh pr list --state open --json number,title,isDraft,createdAt,labels,mergeStateStatus,headRefName`. Group by:
      - draft vs ready
      - has `soak-alert` label
      - mergeable (CLEAN) vs blocked (UNSTABLE/DIRTY/BEHIND/BLOCKED)

   c. **Closed PRs in the window** — `gh pr list --state merged --search "merged:>=$since" --json number,title,mergedAt,additions,deletions,author,labels`. Count by area (use `gh pr view ... --json files` if the title is ambiguous; partition by top-level path: `lib/` / `services/` / `plugins/` / `infra/` / `docs/` / `.github/` / `contracts/` / `tests/`).

   d. **CI health** — `gh run list --workflow=ci.yml --status=failure --created=">=$since" --limit 20 --json conclusion,headBranch,createdAt`. Report any failure spikes.

   e. **Routine soak status** — there are three routines with documented soak gates as of 2026-04-26: `weekly-backtest` (4-cycle gate), `threat-refresh` (24-cycle gate), `content-engine` (7-cycle gate). For each, surface the latest comparator verdict and remaining cycles.

   f. **Open issues** — `gh issue list --state open --label mission-digest --json number,title,createdAt`. Mention any prior digest still un-closed.

4. Render the digest as a single Markdown body with sections:
   - `## TL;DR` — three bullet points: best result, worst result, blocking decision.
   - `## Soak progress` — table per routine: stage, latest verdict, cycles done / required, evidence doc link.
   - `## PRs merged this week` — table grouped by area.
   - `## PRs still open` — table with status flags.
   - `## CI failures` — list with run links, or `none` if zero.
   - `## Decisions awaiting Ari` — concrete questions, each with a link to the relevant doc / PR.
   - `## Next-week candidates` — the next 3 high-value workstreams given current state.

5. Post the digest:
   - `gh label create mission-digest --color 0A2540 --description "Weekly Sapphire mission digest"` if missing (idempotent).
   - `gh issue create --title "Mission digest YYYY-MM-DD" --body "<digest>" --label mission-digest`.

6. If no PRs merged in the window AND no soak progress AND no failing CI runs, still post the digest — say so explicitly. Silence is not progress.

## Idempotency

If an issue exists with title `Mission digest YYYY-MM-DD` for today's UTC date, exit 0 with no issue. (Re-running on the same day is a no-op.)

## Reporting

The GitHub issue is the only report. No inline summary, no other side effects.
