# Factory Test Guardian Runbook

Run by the cloud routine **Sapphire factory test guardian** (cron `0 4 * * *`,
04:00 UTC = 22:00 America/Denver). Also the manual fallback if the routine
is paused.

## Goal

Run the Sapphire test suite end-to-end against the latest `main`. If any
test fails, open a single GitHub issue describing the failures so the
factory can self-heal even when Ari is offline. If everything passes,
exit 0 silently — no issue, no PR, no Telegram, no comment.

## Critical Safety

- **Read-only repo state.** Do not edit any tracked file, do not stage
  any change, do not push any branch.
- **No PR opened by this routine.** Test failures get a labeled issue;
  fixing them is a separate human or factory-repo-fixer concern.
- **One issue per failure cluster, not per test.** Group failures so the
  issue list does not flood when a shared module breaks many tests.
- **Idempotent.** If today's failure cluster already has an open issue
  (label `factory-test-guardian` + same fingerprint in body), exit 0
  silently — do not open a second one.
- **No emojis** in titles, branches, commits, or issue bodies.
- **Cloud-only execution.** This runbook runs in the Sapphire cloud
  environment with the repo cloned in. It must not assume any local
  Mac state, local Ollama, local OpenBB, Tailscale connectivity, or
  any LaunchAgent is up.

## Steps

1. `gh auth status` must succeed. Otherwise exit 0 with no commit and
   log "no gh auth, skipping".

2. Confirm clean working tree:
   ```bash
   git rev-parse HEAD
   git status --short
   ```
   If working tree is dirty, exit 0 with no issue (the cloud env should
   always be clean; dirtiness indicates an environment bug).

3. Install test deps. The cloud env has Python 3.11+ already; verify:
   ```bash
   python3 --version
   pip install -e . 2>&1 | tail -5
   pip install -r requirements-test.txt 2>&1 | tail -5
   ```

4. Run the **core** test suite:
   ```bash
   python3 -m pytest tests/unit/ --tb=short -q --maxfail=20 \
     2>&1 | tee /tmp/factory-test-guardian-core.log
   ```
   Capture the exit code as `CORE_EXIT`.

5. Run the **plugin** test suite:
   ```bash
   python3 -m pytest plugins/claw-sapphire/tests/ -q --maxfail=20 \
     2>&1 | tee /tmp/factory-test-guardian-plugin.log
   ```
   Capture the exit code as `PLUGIN_EXIT`.

6. If both `CORE_EXIT == 0` AND `PLUGIN_EXIT == 0`: exit 0 silently.
   Do not open any issue.

7. Otherwise extract failures:
   - From each log file, grep `^FAILED ` lines plus the last `===` summary
     block.
   - Compute a fingerprint: sha1 of the sorted concatenation of
     `FAILED ` test node IDs from both suites. Use the first 12 chars
     as `FP`.

8. Search existing issues to enforce idempotency:
   ```bash
   gh issue list --state open --label factory-test-guardian \
     --search "fingerprint=$FP" --json number,title,body --limit 5
   ```
   If any result has `fingerprint=$FP` literally in its body, exit 0
   silently.

9. Open one issue:
   - Title: `Test failures detected by factory-test-guardian (<N> failed)`
     where N = total failed across both suites.
   - Labels: `factory-test-guardian`, `bug`.
   - Body sections (markdown):
     1. `## Summary` — N failures across (core, plugin) on commit
        `<HEAD short SHA>`.
     2. `## Failed tests` — bulleted list of test node IDs (full paths).
     3. `## Last error excerpt` — last 30 lines of each suite's log.
     4. `## Fingerprint` — single line `fingerprint=<FP>`. Used by
        step 8 above for idempotency on subsequent runs.
     5. `## Reproduce locally` — copy-paste of the two pytest commands
        in step 4 + 5.

10. Print a one-line status summary to stdout: either
    `factory-test-guardian: PASS` or
    `factory-test-guardian: <N> failures, opened issue #<num>`.

## Required tools

`Bash`, `Read`, `Glob`, `Grep`. The cloud routine must include
`gh` available on `PATH`. No write/edit tools are needed by this runbook.

## Out of scope

- Fixing the failing tests. That's `factory-repo-fixer` (only for
  ruff-class auto-fixes) or human work.
- Running flaky-test detection. If a test is flaky, this runbook will
  open one issue per fingerprint each time the flake fires — that's
  acceptable until a human marks it `xfail`.
- Reporting test coverage drift. Separate runbook (TBD).
