# Production Readiness Matrix Runbook

Last updated: 2026-04-27

This is the full-system Sapphire readiness sweep. Use it when Ari asks whether
the autonomous org is truly ready for production testing, when a major merge
lands, or before increasing autonomy.

The matrix is aggressive about visibility and conservative about irreversible
actions. It runs read-only or dry-run probes across repo state, local CI,
GitHub, safety controls, routines, LaunchAgents, local health endpoints,
Google/GCP, media factory readiness, frontend drift, and secret presence. It
does not execute trades, send Telegram messages, read secret payloads, mutate
Gmail/Drive, write to GCP/Foundry/BigQuery/GCS, dispatch workflows, change
billing, enable APIs, or retarget LaunchAgents.

## Commands

Offline/no-external planning:

```bash
make production-readiness-offline
```

Live read-only production-testing sweep:

```bash
make production-readiness
```

Write the current full matrix as an ignored local artifact:

```bash
make production-readiness-artifact
```

The artifact lands at:

```text
data/readiness/production-readiness-latest.md
```

## What It Covers

| Area | Examples |
|---|---|
| Repo/CI | git cleanliness, latest local CI report, frontend endpoint drift |
| Org | repo manifest, worktrees, CI strategy, Hermes skill classes |
| GitHub | open PRs and open issues |
| Safety | confirmation firewall, kill switch state, autonomy audit schema |
| Routines | remote-shadow soak status for backtest, threat, and content routines |
| Local runtime | LaunchAgent presence plus selected localhost health probes |
| Google/GCP | Gemini CLI/tooling, GCP data plane, Vertex idle/batch posture, cost posture |
| Secrets | required secret presence only, never values |
| Media | local dry-run media factory run readiness |

## Status Meaning

| Status | Meaning |
|---|---|
| `pass` | Ready for production testing in this lane. |
| `warn` | Not a hard block, but production value is lower until addressed. |
| `manual_gate` | Safe to prepare, but live execution needs an exact target/cap/rollback. |
| `blocked` | Known prerequisite is missing. |
| `fail` | Fix before promotion. |

The script exits nonzero only for hard blockers. Manual gates are expected for
surfaces such as live Gemini/Vertex calls, BigQuery/GCS writes, Veo generation,
and LaunchAgent retargeting.

## Production Posture

The target state for Sapphire is not “no warnings.” It is:

1. Canonical `main` is clean and locally green.
2. Safety controls are auditable and paste-safe.
3. Required services are observable.
4. Routine migrations have enough soak evidence.
5. Every live action has a named target, budget/blast-radius cap, output path,
   and rollback.
6. Dry-run artifacts exist before live external execution.

Use the matrix’s `Next Actions` section as the control tower queue. Convert the
highest-value warning into a small PR or a dry-run artifact, then re-run the
matrix.
