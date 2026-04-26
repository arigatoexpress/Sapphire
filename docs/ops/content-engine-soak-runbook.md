# Content-Engine Remote-Shadow Soak Runbook

This runbook is executed daily by the scheduled remote agent
**Sapphire content-engine soak collector** (claude.ai routine, cron `0 13 * * *`).
It is also the manual fallback if the routine is paused.

## Goal

Collect the latest successful `content-engine.yml` workflow artifact, compare it against
the manifests committed to the repo, append a row to the soak log, open a soak-log PR,
and (when the gate is met) open a second PR that promotes the remote shadow to
canonical.

## Critical Safety

- **Never** run `python3 -m lib.content --publish`.
- **Never** set `SAPPHIRE_PUBLISH_LIVE=1` or `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=1`.
- **Never** modify anything under `data/content/drafts/` or `data/content/ready/`.
  The comparator only writes under `data/content/shadow-reports/`, which is gitignored.
- All PRs ready-for-review (not draft). No emojis in titles, branches, commits, or bodies.
- **Idempotent.** Re-running the same day MUST be a no-op (see step 3).

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit.

2. Find the most recent successful content-engine run from the previous 26 hours:
   ```bash
   gh run list --workflow=content-engine.yml --status=success --limit 1 \
     --json databaseId,createdAt,event,conclusion,headBranch \
     --jq '.[0]'
   ```
   If empty or older than 26 hours from `date -u +%s`, exit 0 with no commit.

3. Read [`docs/org/content-engine-shadow-soak-2026-04-26.md`](../org/content-engine-shadow-soak-2026-04-26.md).
   If the soak-log table already references that run ID, exit 0 with no commit.

4. Determine the next cycle number `N`. Existing rows are numbered; pick `max + 1`.
   Cycle 1 was logged on 2026-04-26 with run `24966520333`.

5. Download the artifact:
   ```bash
   mkdir -p /tmp/content-engine-shadow/<RUN_ID>
   (cd /tmp/content-engine-shadow/<RUN_ID> && gh run download <RUN_ID> -R arigatoexpress/Sapphire)
   ```

6. Run the comparator from the repo root:
   ```bash
   python3 scripts/ops/compare_content_artifacts.py \
     --local-root . \
     --remote-root /tmp/content-engine-shadow/<RUN_ID> \
     --report-out data/content/shadow-reports
   ```
   Exit codes: `0` = PASS, `10` = WARN, `20` = FAIL. Do not treat 10 as an error.

7. Parse the most recent `data/content/shadow-reports/content-shadow-comparison-*.json`. Capture:
   - `verdict` (PASS | WARN | FAIL)
   - `summary.rows_pass`, `rows_warn`, `rows_fail`
   - `missing = len(summary.missing_in_local) + len(summary.missing_in_remote)`
   - One short sentence describing the dominant kind of drift across `kind_diffs`
     (body length, file hash, sources, quality).

8. Append exactly **one row** at the end of the markdown table under `## Soak Log` in
   [`docs/org/content-engine-shadow-soak-2026-04-26.md`](../org/content-engine-shadow-soak-2026-04-26.md).
   Match the existing pipe spacing exactly:

   ```
   | <N> | <YYYY-MM-DDTHH:MMZ> | <event> | [<RUN_ID>](https://github.com/arigatoexpress/Sapphire/actions/runs/<RUN_ID>) | <verdict> | <rows_fail> | <missing> | <one-sentence note> |
   ```

   Do not modify any other line in the file.

9. Open the **soak-log PR**:
   - Branch: `chore/content-engine-soak-cycle-<N>` from latest `main`.
   - Title: `Log content-engine soak cycle <N>`.
   - Body: paste the new row, then a one-paragraph summary of verdict, rows_pass/warn/fail,
     missing counts, and a link to the run.

10. **Failure escalation.** If `verdict == FAIL` or `rows_fail > 0` or `missing > 0`:
    - Ensure a `soak-alert` GitHub label exists with color `d73a4a`.
      Create it via `gh label create soak-alert --color d73a4a --description "Remote-shadow soak failure"` if missing.
    - Apply `soak-alert` to the cycle PR.
    - Add a PR comment titled `SOAK FAIL - escalate` listing the failing kinds and
      the dominant drift.

11. **Promotion check.** After appending the new row, look at the most recent 7 rows
    in the table. If **all 7** satisfy:
    - `verdict in {PASS, WARN}`
    - `rows_fail == 0`
    - `missing == 0`

    open a **second PR** (in addition to the cycle log PR) titled
    `Promote content-engine remote shadow to canonical`, branch
    `feat/content-engine-cutover` off latest `main`:

    a. Rename `infra/launchagents/com.sapphire.content-engine.plist` to
       `infra/launchagents/com.sapphire.content-engine.plist.disabled`.
       Repo-side change only — the operator will `launchctl unload` separately.
    b. Update [`docs/routines-manifest.md`](../routines-manifest.md):
       remove the `com.sapphire.content-engine` row from the section 2 table
       (Scheduled Mac LaunchAgents); in section 2.1, add a sentence stating
       content-engine is now remote-canonical, citing the soak log as evidence.
    c. Update [`infra/org-repos.yaml`](../../infra/org-repos.yaml): in the
       `content-engine` routine entry, change `stage: soaking` to `stage: cutover`
       and add `cutover_at: "<UTC date>"`.
    d. PR body: link the soak log, paste the 7 evidence rows, restate the
       rollback (reverse all three diffs; no data migration).

## Forbidden Operations

- Do not run pytest, ruff, or rebuild any data. Only the comparator.
- Do not commit anything under `data/`.
- Do not edit any file outside those listed above.

## Reporting

The PR(s) opened are the only report. Do not produce a separate summary message.
If steps 2–11 produce no commit (idempotent skip or no run found), exit 0 silently.

## Manual fallback

If the routine is disabled or paused, run the steps above by hand from the repo root.
The artifact comparator is read-only and safe to re-run; the soak log only grows
with new run IDs.
