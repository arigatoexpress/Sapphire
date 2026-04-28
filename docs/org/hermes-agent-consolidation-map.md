# Hermes Agent Consolidation Map

Verified on 2026-04-26. This is a read-only map for Wave 3 agent consolidation;
it does not change the running gateway, LaunchAgent, Hermes config, skills, or
Telegram behavior.

## Current Shape

Hermes has two local checkouts with different jobs:

| Path | Role | Branch/state |
|---|---|---|
| `/Users/aribs/.hermes/hermes-agent` | Runtime checkout used by `ai.hermes.gateway` | `local/sapphire-relay-ignore`, 2 commits ahead and 1103 commits behind fetched `origin/main` |
| `/Users/aribs/Code/hermes-agent` | Development/reference clone tracked by the org manifest | `main`, clean, 61 commits behind fetched `origin/main` |

The LaunchAgent at `/Users/aribs/Library/LaunchAgents/ai.hermes.gateway.plist`
executes the runtime checkout, not the development clone. It uses the
`ai.hermes.gateway` label, runs from `/Users/aribs/.hermes/hermes-agent`, and
sets only non-secret environment keys in the plist (`HERMES_HOME`, `PATH`,
`VIRTUAL_ENV`). Do not replace or update the development clone and assume the
running gateway changed.

## Sapphire-Specific Runtime Patches

The runtime checkout carries two local commits on top of the older Hermes base:

| Commit | Purpose | Consolidation path |
|---|---|---|
| `5f2af81c` | Ignore relay-only Telegram users after hooks capture their messages, preventing Kimi relay loops. Also raises the hook message slice from 500 to 16000 chars. | Prefer upstreamable ignore-list behavior or a Sapphire-owned hook/API that does not require patching `gateway/run.py`. |
| `3ba7bd5f` | Intercept bare Sapphire confirmation replies like `confirm abc12345` before they reach the LLM, forwarding them to `lib.core.confirmation_firewall.handle_confirmation_reply`. | Prefer a Hermes hook or Sapphire gateway adapter so confirmation handling stays in Sapphire code and survives Hermes updates. |

There is also a backup branch/stash in `/Users/aribs/Code/hermes-agent` touching
`gateway/run.py`; it matches the relay-ignore theme but is not in the running
checkout.

## Integration Surfaces

| Surface | Location | Notes |
|---|---|---|
| Gateway process | `ai.hermes.gateway` LaunchAgent | Live PID observed with last launchctl status `-15`, consistent with prior graceful restart history. |
| Sapphire skills | `/Users/aribs/.hermes/skills/sapphire/*/SKILL.md` | 15 Sapphire skills: cyber intel, inference tier, Kimi delegate, macro data, paper trading, regional intel, repo discovery, system health/ops, THO ops, threat intel, trading analysis/brain/signals, and TradingView. |
| Kimi relay hook | `/Users/aribs/.hermes/hooks/kimi-relay-writer/` | Captures relay bot responses into `~/.sapphire/relay/` after Hermes emits `agent:start`. |
| Confirmation firewall | `lib/core/confirmation_firewall.py` | Runtime patch imports this directly from the Sapphire repo path. |
| Sapphire control commands | Hermes skills and Sapphire plugin tools | Some skills can call `launchctl kickstart`, send notification tool messages, read live local files, or call THO admin endpoints. Treat as production-adjacent. |

## Risks

- Runtime drift is now the main risk: the running checkout is 1103 commits
  behind fetched Hermes `origin/main`, while carrying two local Sapphire patches.
- Updating Hermes directly could drop relay-loop prevention or confirmation
  firewall routing unless those behaviors are isolated first.
- The manifest used to point only at `/Users/aribs/Code/hermes-agent`; that is
  not sufficient for operational decisions because the LaunchAgent runs the
  separate runtime checkout.
- Several Sapphire skills contain operational commands. Future cleanup should
  classify them by blast radius before consolidating or deleting anything.

## Recommendation

Treat Hermes as a `local_patched_runtime` integration until one of these
explicit decisions is made:

1. Upstream or configure the relay ignore behavior in Hermes proper.
2. Move Sapphire confirmation replies into a supported Hermes hook or a
   Sapphire-owned adapter with tests.
3. Create a maintained Ari fork if upstreaming is too slow.
4. Only then update the runtime checkout, restart the LaunchAgent, or archive
   backup branches.

The next non-overlapping Wave 3 task is a command-surface audit of the 15
Sapphire Hermes skills, with each skill labeled `read_only`, `local_mutating`,
`external_mutating`, or `production_adjacent`.

## Runtime Readiness Probe

Sapphire now tracks the live/runtime distinction with
`scripts/ops/hermes_runtime_readiness.py` and the
`hermes_runtime_quick_exec_guard` production-readiness surface. The probe is
read-only and reports whether the running `ai.hermes.gateway` checkout has the
Sapphire confirmation-reply patch, quick-command `exec` CommandGuard patch, and
`SAPPHIRE_REPO_PATH` LaunchAgent environment needed to make the guard active.

Use this probe before any Hermes runtime promotion, restart, skill rewrite, or
Telegram command expansion:

```bash
make hermes-runtime-readiness PY=python3
make production-readiness-artifact PY=python3
```
