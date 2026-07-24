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
bodies run under Git Bash on Windows without rewriting — **provided Git Bash is
actually on the runner service's PATH.** See the next section; it was not, and
that is what failed on the first Windows run.

## `bash` on the Windows runner resolves to WSL, not Git Bash

First real Windows run (2026-07-24, run 30119251115) failed all three jobs in
their first `run:` step, identically:

```
shell: C:\WINDOWS\System32\bash.EXE --noprofile --norc -e -o pipefail {0}
Running WSL as local system is not supported.
Error code: Bash/WSL_E_LOCAL_SYSTEM_NOT_SUPPORTED
```

The same log shows git resolving correctly:

```
[command]"C:\Program Files\Git\cmd\git.exe" version
git version 2.53.0.windows.1
```

That pair is the whole diagnosis. Git for Windows installs `git.exe` under
`Git\cmd\` and `bash.exe` under `Git\bin\`, and the installer only adds `cmd\`
to PATH unless "Use Git and optional Unix tools from the Command Prompt" was
selected. So `git` is found, `bash` is not, and the lookup falls through to
`C:\Windows\System32\bash.exe` — the WSL launcher. The runner is installed as a
service under LOCAL SYSTEM, and WSL refuses to run as LOCAL SYSTEM.

### Fix, applied in-repo (no machine access needed)

The seven portable jobs now carry a job-level shell default that names Git Bash
explicitly, keyed off the same variable that selects the runner:

```yaml
defaults:
  run:
    shell: ${{ contains(vars.SAPPHIRE_RUNNER_TESTS, 'Windows')
               && 'C:\Program Files\Git\bin\bash.exe --noprofile --norc -e -o pipefail {0}'
               || 'bash' }}
```

The Git install path is not a guess: the same failing logs show
`[command]"C:\Program Files\Git\cmd\git.exe" version` succeeding, so Git for
Windows is at `C:\Program Files\Git\` and `bin\bash.exe` is beside `cmd\`.
The argument list matches what the runner passes for built-in `bash`, so step
semantics (`-e`, `pipefail`) are unchanged.

Keying on `SAPPHIRE_RUNNER_TESTS` rather than hardcoding means pointing that
variable back at the macOS box transparently restores plain `bash` — the
override is not a one-way door. The three host-bound jobs (`smoke-test`,
`deploy`, `secrets-scan`) are untouched and keep the workflow-level `bash`.

### Optional machine-side cleanup (not required)

Still worth doing when someone is at the box, because it fixes `bash` for
everything else on that machine too — but CI no longer depends on it:

- Add `C:\Program Files\Git\bin` to the *system* PATH, or set it for the runner
  only via `<runner-dir>\.env` (read at service start):
  ```
  PATH=C:\Program Files\Git\bin;C:\Program Files\Git\usr\bin;%PATH%
  ```
  Runner dir is `C:\Users\aribs\.github-runners\sapphire-win`.

### Correction: the macOS tool-cache paths come from `ci.yml`, not the runner

An earlier revision of this document blamed the runner's `.env` for the macOS
paths visible in every Windows job log:

```
AGENT_TOOLSDIRECTORY: /Users/aribs/.github-runners/toolcache
RUNNER_TOOL_CACHE:    /Users/aribs/.github-runners/toolcache
```

That was wrong. They are set in **`ci.yml`'s own top-level `env:` block**, with a
comment explaining they exist for the self-hosted *macOS* runner. Because the
block is workflow-level it applies to every job, so Windows jobs receive a
`/Users/aribs/...` path that cannot exist on `DESKTOP-HFCK6U9`.

Harmless today: no job uses `setup-python` — everything goes through `uv`, and
uv is handled by the `ensure uv` step. It will bite the first action that
consults the tool cache. Fixing it properly means scoping those two variables to
the three macOS-bound jobs instead of setting them workflow-wide.

Running the service as the `aribs` user instead of LOCAL SYSTEM would also make
the WSL bash work, but that is the worse fix — it leaves CI depending on WSL and
on a specific user session.

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
