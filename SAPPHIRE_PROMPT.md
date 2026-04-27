# Sapphire OS Session Launcher

Use this launcher to initialize any new agent session working on Sapphire OS or
its active satellites.

## Start Here

1. Read `AGENTS.md`.
2. Read `docs/org/control-tower.md`.
3. Read `docs/org/autonomous-org-cluster-prompt.md`.
4. Run:

```bash
python3 scripts/ops/org_status.py --no-external --markdown
git status --short --branch
git worktree list
```

## Operating Posture

Codex is Ari's primary Sapphire production-autonomy operator. Move in small,
reversible, tested PRs. Use `/Users/aribs/Code/_worktrees/` for branch work and
keep `/Users/aribs/Code/Sapphire` clean on `origin/main` whenever possible.

## Hard Stops

Do not expose or rotate secrets, enable real trading, move money, send real
Telegram test messages, retarget or restart LaunchAgents, disable workflows or
branch protections, delete infrastructure/data, or broaden sensitive
permissions. Build the safest dry-run, local artifact, branch, or PR instead.

## No-Spend CI

Avoid paid GitHub Actions. Sapphire uses the `SAPPHIRE_RUNNER` no-spend gate and
local CI evidence. Satellite repos without that guard use local verification and
`[skip ci]` only as a bootstrap tactic for no-spend guardrail PRs.
