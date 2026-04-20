# Contributing to Sapphire OS

## Before your first PR

1. Read [docs/onboarding/collaborator-pack.md](docs/onboarding/collaborator-pack.md) — the full dev pack (topology, architecture, security posture, repo layout).
2. Follow [docs/onboarding/first-week-checklist.md](docs/onboarding/first-week-checklist.md) — concrete day-by-day path, through first PR.
3. If you're here for security / model red-team work, read [docs/onboarding/ai-redteam-scope.md](docs/onboarding/ai-redteam-scope.md) — scope, rules of engagement, disclosure windows, credit model.
4. Read [CLAUDE.md](CLAUDE.md) — project map + commands. Humans should treat it like a map; agents already do.

## Getting a dev environment

```bash
git clone https://github.com/arigatoexpress/Sapphire.git
cd Sapphire
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pip install -r requirements-test.txt   # test deps
make install-hooks                     # pre-commit + commit-msg
make doctor                            # env health check — read every line
make test-all                          # 1,967 tests — must pass before any PR
```

## Core rules

- **Services never import from other services.** Cross-service reuse goes through `lib/`.
- **Every module has a `SKILL.md`.** Read it before working on that module.
- **Never reduce the test suite.** Today: 1,932 core + 35 plugin = 1,967 passing. Your PR should leave it at ≥ 1,967.
- **PnL is king.** Sortino / Calmar over Sharpe. 80 % win rate target.
- **No AI slop.** Every claim in a PR or doc must be verifiable from the diff or the data.

## Git + CI flow

1. **Branch:** `git checkout -b <your-handle>/<short-slug>`. Long-lived branches are fine; merge forward from `main` regularly.
2. **Commit:** small, atomic commits. Pre-commit runs ruff + gitleaks + bandit — **don't bypass with `--no-verify`**. If a hook fails, fix the root cause.
3. **PR:** [.github/pull_request_template.md](.github/pull_request_template.md) is mandatory. Fill out the "Risk touch points" checklist honestly — it's the signal reviewers rely on.
4. **CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs five jobs on every PR (ruff lint, pytest core, pytest plugin, tool-registry invariants, gitleaks). All must pass before merge.
5. **Review:** [`.github/CODEOWNERS`](.github/CODEOWNERS) gates security-sensitive, trading-critical, and infra paths — those PRs require Ari's explicit review. Non-gated paths can be merged after one `+1`.
6. **Merge:** squash-merge is preferred; keep the PR title useful as a commit title. Force-pushes to `main` are disabled.

## Pre-commit locally

```bash
pre-commit install                    # first time only
pre-commit run --all-files            # format/lint the whole repo
make fix                              # ruff auto-fix + format
make ci                               # mirror GitHub Actions locally before push
```

## Commit message style

Follow the existing `git log` style: `scope: short imperative summary`. Examples:

- `fix(foundry): graceful degradation when unauthed`
- `feat(trading): add VolatilityBreakout strategy`
- `docs: reconcile stale test counts`
- `infra(ci): pin requirements-test.txt`
- `chore(lint): retire flake8`

Body: *why* (not what — the diff shows what). Soft-wrap ~72 cols. When a commit was co-authored with an agent, append `Co-Authored-By:` per the existing convention.

## Reporting security findings

See [SECURITY.md](SECURITY.md). Short version: **sensitive findings go direct-message, not GitHub issue.** First message includes severity + description + payload *hash* (not payload itself).

## Questions

- **Project details**: [CLAUDE.md](CLAUDE.md) and [docs/](docs/).
- **Scope / rules of engagement for research**: [docs/onboarding/ai-redteam-scope.md](docs/onboarding/ai-redteam-scope.md).
- **Everything else**: DM the operator.

---

*This repo is a single-operator system today. Low ceremony, high signal — one clean commit beats three noisy ones.*
