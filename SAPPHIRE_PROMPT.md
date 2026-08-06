# Sapphire OS Session Launcher

Use this launcher to initialize any new agent session working on Sapphire OS or
its active satellites.

## Start here

1. Read `docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md` (north star).
2. Read `AGENTS.md` (safety charter).
3. If you are **Gemini on Google Cloud Shell**, open and follow  
   `docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md` and run  
   `bash scripts/ops/gcp_cloudshell_bootstrap.sh`.
4. Read `docs/org/control-tower.md` and `docs/org/autonomous-org-cluster-prompt.md` if present.
5. Skim alpha critical path: `docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md`.
6. Run:

```bash
python3 scripts/ops/org_status.py --no-external --markdown
git status --short --branch
git worktree list
```

## Mission (one line)

Windows private datacenter + agent harnesses that earn on designated rails,
publish research, and self-improve — Mac commands, GCP warehouses, models propose only.

## Operating posture

- Move in small, reversible, tested PRs.
- Prefer worktrees; keep checkout clean on `origin/main` when possible.
- Plant runtime truth lives in `~/ops-state` (not only this git tree).

## Hard stops

Do not expose or rotate secrets, enable unbounded real trading, move THO money,
send real Telegram test messages, retarget LaunchAgents from Cloud Shell,
disable workflows or branch protections, delete infrastructure/data, or broaden
sensitive permissions. Build the safest dry-run, local artifact, branch, or PR
instead.

## No-spend CI

Avoid paid GitHub Actions. Sapphire uses the `SAPPHIRE_RUNNER` no-spend gate and
local CI evidence where configured.
