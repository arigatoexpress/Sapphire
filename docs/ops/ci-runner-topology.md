# CI runner topology — why jobs land on the Mac, and how to move them

Written 2026-07-24 while PR #953 sat queued for an hour. Intent has always been
"the always-on Windows box runs CI"; the wiring for that is present but has
never been switched on.

## How `runs-on` resolves today

`ci.yml` has ten jobs in two groups:

| Group | `runs-on` | Jobs |
|---|---|---|
| Portable | `fromJSON(vars.SAPPHIRE_RUNNER_TESTS \|\| vars.SAPPHIRE_RUNNER)` | lint (ruff), test (pytest), plugin tests, test inventory, public boundary smoke, tool registry invariants, pine static analyzer |
| Host-bound | `fromJSON(vars.SAPPHIRE_RUNNER)` | container smoke test, deploy dashboard candidate, gitleaks (secrets) |

The `||` is the migration seam. GitHub Actions treats an unset repository
variable as the empty string, which is falsy, so **if `SAPPHIRE_RUNNER_TESTS` is
unset every portable job silently falls back to `SAPPHIRE_RUNNER` — the Mac.**
Nothing errors; the jobs just queue on a machine that may be asleep.

`win-runner-smoke.yml` states the plan in its own header: it is a one-shot
validation that the Windows runner can execute the portable jobs *"BEFORE
flipping SAPPHIRE_RUNNER_TESTS."* The smoke workflow was written; the flip was
never made.

## The switch

Repository → Settings → Secrets and variables → Actions → Variables:

```
SAPPHIRE_RUNNER_TESTS = ["self-hosted","Windows","X64","sapphire-win"]
```

Set 2026-07-24.

Three things that look like the switch but are not, all observed while doing it:

- **A shell environment variable is the wrong layer.** `vars.*` is evaluated by
  GitHub's scheduler server-side, when it decides which runner receives the job.
  Exporting `SAPPHIRE_RUNNER_TESTS` in a container, on the Mac, or on the Windows
  box cannot reach that decision — none of those machines are in the scheduling
  path.
- **A GitHub *Environment* variable is also the wrong scope.** Variables defined
  under Settings → Environments only reach jobs that declare `environment:
  <name>`. No job in `ci.yml` does. It must be a *repository* variable.
- **Already-queued runs do not pick it up.** `runs-on` is resolved when the job
  is created, so a run that was queued before the variable existed keeps
  targeting the old runner forever. Push a commit (the `concurrency` group's
  `cancel-in-progress` retires the stale run) or use Re-run all jobs. Waiting
  will not help.

Must be a JSON array — `fromJSON()` parses it, and the labels have to match the
Windows runner's registration exactly (the same set `win-runner-smoke.yml`
already targets). Leave `SAPPHIRE_RUNNER` pointing at the Mac.

That single variable moves seven of ten jobs, including all of lint and the
whole test suite. No workflow edit is required — the seam already exists.

Recommended order:

1. Settings → Actions → Runners: confirm `sapphire-win` shows **Idle**, not
   Offline. If it is offline the flip changes nothing; the jobs just queue on a
   different sleeping machine.
2. Dispatch `win-runner-smoke.yml` (`gh workflow run win-runner-smoke.yml`). It
   runs `uv`, ruff, a two-file pytest subset and the README inventory check on
   the Windows box. Manual-only, read-only, no deploy.
3. Only if that is green, set the variable.

`defaults.run.shell: bash` is already set repo-wide in `ci.yml`, so the job
bodies run under Git Bash on Windows without rewriting. That was the expensive
part and it is done.

## What stays on the Mac, and why

Flipping the variable does **not** make PRs independent of the Mac. Two
host-bound jobs still run on pull requests:

- **`gitleaks (secrets)`** — installs via `brew install gitleaks`, which is
  macOS-only. Fixable, but it needs a portable install path: the repo already
  pins `gitleaks v8.21.2` in `.pre-commit-config.yaml`, so routing CI through
  the same pinned hook is the obvious candidate. Not attempted here because the
  CI job uses flags the pre-commit hook does not (`--redact`, `--exit-code=2`,
  SARIF output to the security tab) and the change could not be validated from a
  container without access to the Windows runner. Do not swap it blind.
- **`container smoke test`** — requires Docker Desktop. Windows can run Docker
  Desktop, but that is an infrastructure decision, not a workflow edit. Note its
  condition is `pull_request || main`, so it gates every PR.

`deploy dashboard candidate` is correctly Mac-only and does **not** gate PRs —
its condition is `github.ref == 'refs/heads/main'` plus the GCP WIF variables.

So the honest end state after the variable flip is: PRs get lint and the full
test suite from Windows within minutes, and still wait on the Mac for the
secrets scan and the container smoke test. Making PRs fully Mac-independent
means resolving those two as well.

## Why this failure mode is easy to miss

Every job carries `if: ${{ vars.SAPPHIRE_RUNNER != '' }}`. When the runner is
offline the jobs do not fail — they queue indefinitely and the PR shows
"Expected — Waiting for status to be reported." A red X gets attention; a
perpetually pending check does not. This is the same shape as the two other
quiet-failure findings in `docs/audits/portfolio-audit-2026-07-24.md`: a missing
`uvicorn` pin silently un-collecting 57 tests, and `pytest_ignore_collect`
dropping whole files without counting them. Prefer loud failure over silence.

Consider a `timeout-minutes` on the queue side or a hosted `ubuntu-latest`
fallback for lint alone, so at least one signal always reports.
