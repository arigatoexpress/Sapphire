# Hermes Runtime Readiness

`scripts/ops/hermes_runtime_readiness.py` is the safe promotion gate for the
Hermes Telegram gateway. It compares the live checkout used by
`ai.hermes.gateway` with the development clone tracked in Sapphire, then reports
whether quick-command `exec` paths are actually covered by Sapphire
`CommandGuard`.

The probe is read-only. It does not restart Hermes, edit LaunchAgents, send
Telegram messages, read secret values, or print Hermes quick-command bodies.

## Commands

```bash
python3 scripts/ops/hermes_runtime_readiness.py
python3 scripts/ops/hermes_runtime_readiness.py --format json
make production-readiness-artifact PY=python3
```

## Production Gate

Hermes quick-exec promotion is ready only when all of these are true:

- `ai.hermes.gateway` points at the runtime checkout.
- The runtime checkout intercepts Sapphire confirmation replies.
- The runtime checkout gates quick-command `exec` through Sapphire
  `CommandGuard`.
- The LaunchAgent exposes `SAPPHIRE_REPO_PATH` so the guard path is active.

If the development clone has the guard but the runtime checkout does not, the
next action is a dedicated runtime promotion with a backup, exact diff, rollback
command, and explicit `launchctl kickstart` gate.
