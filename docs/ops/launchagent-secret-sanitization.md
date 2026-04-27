# LaunchAgent Secret Sanitization Runbook — `dashboard` + `inference-proxy`

This is a **preparation runbook**. It describes the design, ordering, and
rollback story for sanitizing the two live LaunchAgents that still embed
secret values in `EnvironmentVariables`. **This document is docs-only — no
plists, scripts, services, or `~/Library/LaunchAgents/` files are modified
by the PR that introduces this runbook.** Implementation lands in a
follow-up PR after the rotation gate (below) clears.

## Background

The 2026-04-21 audit (`docs/launchagents-audit-2026-04-21.md`) flagged two
LaunchAgents as live-only and secret-bearing:

- **F1**: `com.sapphire.inference-proxy.plist` — embeds a Telegram bot token
  in `EnvironmentVariables`.
- **F2**: `com.sapphire.dashboard.plist` — embeds an `AUTH_PASSWORD` literal
  in `EnvironmentVariables`.

The 2026-04-27 follow-up audit (PR #297) confirmed both are still
unversioned. A repo-wide grep verified:

- No `services/dashboard/launchagent/` directory.
- No `services/inference-proxy/launchagent/` directory.
- No copy in `infra/launchagents/` for either label.

Sapphire's modern convention is service-owned plists at
`services/<name>/launchagent/` (precedent: `pm-bot`, `service-supervisor`,
`morning-digest`). Both targets here will follow that convention.

## Secret inventory (names only — values must never appear in this repo)

| Plist | Env var | Class | Disposition |
|-------|---------|-------|-------------|
| `com.sapphire.dashboard` | `AUTH_PASSWORD` | password | move to `~/.sapphire/secrets.env`; sanitized plist references nothing |
| `com.sapphire.inference-proxy` | `RELAY_READER_TOKEN` | Telegram bot token (live, **burnt**) | **rotate first** (see gate); then move to `~/.sapphire/secrets.env` |
| `com.sapphire.inference-proxy` | `OPENROUTER_API_KEY` | API key | move to `~/.sapphire/secrets.env`; current live value is empty/reserved |
| `com.sapphire.inference-proxy` | `KIMI_RELAY_CHAT_ID` | private Telegram chat identifier (PII-shaped, not a credential) | move to `~/.sapphire/secrets.env` for hygiene; not a strict rotation target |

Routing flags `PI_RARI1_ENABLED` and `PI_RARI2_ENABLED` are non-secret and
remain in the sanitized plist's `EnvironmentVariables`. `PATH` and `PORT`
likewise remain in the sanitized dashboard plist.

## Hard gate: rotate `RELAY_READER_TOKEN` before any live sanitization

The token has been observed in past Claude session transcripts and in
audit-tool output. Treat it as compromised. Sanitization without rotation
just hides a still-burnt credential — strictly worse than the current state
because the burnt value would now travel with a tracked plist instead of
staying isolated to the Mac.

The implementation PR that follows this runbook **must not be merged or
deployed** until:

1. Ari rotates the bot token via `@BotFather` (`/revoke`).
2. The new token is recorded in `~/.sapphire/secrets.env` (mode `0600`,
   not in repo).
3. The live `~/Library/LaunchAgents/com.sapphire.inference-proxy.plist`
   has been bounced and verified against the new token.

If steps 1–3 are not yet complete when the implementation PR is ready,
keep that PR in draft.

`AUTH_PASSWORD`, `OPENROUTER_API_KEY` (currently empty), and
`KIMI_RELAY_CHAT_ID` do not require rotation — they have no known
exposure beyond the local Mac and CLAUDE.md (which already documents
`AUTH_PASSWORD` as the dev default).

## Target structure (after the implementation PR)

```
services/dashboard/
├── launchagent/
│   └── com.sapphire.dashboard.plist        # tracked, sanitized
└── start.sh                                # new wrapper; sources secrets.env

services/inference-proxy/
├── launchagent/
│   └── com.sapphire.inference-proxy.plist  # tracked, sanitized
├── start.sh                                # already exists; gains source line
└── ...

~/.sapphire/secrets.env                     # NOT in repo; mode 0600
```

`~/.sapphire/secrets.env` schema (populated by Ari, never committed):

```
AUTH_PASSWORD=<dashboard password>
RELAY_READER_TOKEN=<rotated Telegram bot token>
OPENROUTER_API_KEY=<empty or set per env>
KIMI_RELAY_CHAT_ID=<chat id>
```

The wrapper-source pattern is the same one already used for
`MOONSHOT_API_KEY` in the inference proxy — see CLAUDE.md → "Inference
Proxy" section.

## Sanitized plist shape (illustrative — no secret values)

`services/dashboard/launchagent/com.sapphire.dashboard.plist`:

- `ProgramArguments`: `/bin/bash`, `services/dashboard/start.sh`
- `EnvironmentVariables`: `PATH`, `PORT` only
- `WorkingDirectory`: `/Users/aribs/Code/Sapphire/services/dashboard`

`services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist`:

- `ProgramArguments`: `/bin/bash`, `services/inference-proxy/start.sh`
  (unchanged from current)
- `EnvironmentVariables`: `PI_RARI1_ENABLED`, `PI_RARI2_ENABLED` only
- `WorkingDirectory`: `/Users/aribs/Code/Sapphire`

Both `start.sh` wrappers add this preamble immediately after the shebang:

```bash
set -a
[ -f "$HOME/.sapphire/secrets.env" ] && source "$HOME/.sapphire/secrets.env"
set +a
```

The conditional source means a missing secrets file does not crash boot
on a fresh machine; the dashboard will refuse to start without
`AUTH_PASSWORD` and the inference proxy will run with reduced relay
functionality. Both behaviors are preferable to a hard crash.

## Implementation PR checklist (for the follow-up PR, not this one)

- [ ] Token rotation gate cleared (Ari + BotFather; live plist already
      using rotated value).
- [ ] Add `services/dashboard/start.sh` wrapper.
- [ ] Add the `secrets.env` source preamble to
      `services/inference-proxy/start.sh`.
- [ ] Add `services/dashboard/launchagent/com.sapphire.dashboard.plist`
      (sanitized).
- [ ] Add `services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist`
      (sanitized).
- [ ] Extend `tests/unit/test_launchagent_plists.py` to cover both new
      plists. Required assertions:
      - `Label` matches the directory's service name.
      - `EnvironmentVariables` contains no key matching the sensitive
        regex `(?i)(TOKEN|SECRET|PASSWORD|PIN|BEARER|_KEY|KEY_)`.
      - `EnvironmentVariables` does not include any of the four sanitized
        names: `AUTH_PASSWORD`, `RELAY_READER_TOKEN`, `OPENROUTER_API_KEY`,
        `KIMI_RELAY_CHAT_ID`.
      - `ProgramArguments[1]` references the matching service's
        `start.sh`.
- [ ] Update `infra/launchagents/README.md` to remove `dashboard` and
      `inference-proxy` from the "intentionally not versioned" list and
      point at the new service-owned locations.
- [ ] Add a `2026-XX-XX repo-side update` inline note to
      `docs/launchagents-audit-2026-04-21.md` (matches the existing
      pattern at lines 74–78) closing F1 and F2.
- [ ] Run local CI verifier: `python3 scripts/ops/local_ci_verify.py
      --verbose`.

## Deployment (manual, after the implementation PR merges)

The implementation PR ships only repo state. Promoting the sanitized
plists to `~/Library/LaunchAgents/` is a separate manual step performed
by Ari, not by any agent or PR:

1. Backup the current live plists to `*.bak` next to themselves.
2. `cp services/<name>/launchagent/<plist> ~/Library/LaunchAgents/`.
3. `launchctl bootout gui/$(id -u)/com.sapphire.<name>` (or `unload` on
   older macOS).
4. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<plist>`.
5. `launchctl kickstart -k gui/$(id -u)/com.sapphire.<name>`.
6. Smoke test:
   - dashboard: open `http://localhost:8080` and complete the auth
     prompt with the value now sourced from `~/.sapphire/secrets.env`.
   - inference-proxy: `curl -s http://localhost:11435/health` and
     exercise a Kimi relay path.

No `launchctl` commands are run as part of the implementation PR or the
runbook PR.

## Rollback (conceptual — not executed by this PR)

If a deployed sanitized plist fails to start the service:

1. **Restore from backup**:
   `cp ~/Library/LaunchAgents/com.sapphire.<name>.plist.bak ~/Library/LaunchAgents/com.sapphire.<name>.plist`.
2. **Reload**:
   `launchctl bootout gui/$(id -u)/com.sapphire.<name>` then
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.<name>.plist`.
3. **Verify**: the same smoke test as in the deployment section
   confirms the rollback succeeded.
4. **Diagnose**: most likely failures are (a) `~/.sapphire/secrets.env`
   missing or wrong mode, (b) wrapper script not executable, (c) typo in
   the env-var name in either the wrapper or the consumer code. Fix in
   the implementation PR; do not patch the live plist.
5. **Revert tracked code if needed**: `git revert` on the implementation
   PR's merge commit, push as a new PR, gate on local CI before
   re-merging.

## Out of scope (deliberately, for both this runbook PR and the
implementation PR that follows)

- Hermes gateway (`ai.hermes.gateway.plist`) lives at `~/.hermes/` per
  the original audit; not a Sapphire repo concern.
- `cloudflare-tunnel`, `kronos-daily`, `regional-intel` plists were
  classified by the 2026-04-21 audit as non-tracked-by-design (cert
  paths, cross-repo venvs). No change here.
- Token rotation cadence and a broader secret-rotation policy.
- A general-purpose `~/.sapphire/secrets.env` schema doc.

## Verification of this runbook PR (docs-only)

- `git diff --stat`: only Markdown files touched.
- `git diff --check`: no whitespace issues.
- `gitleaks protect --staged --redact`: no leaks.
- No `*.plist`, `*.sh`, or `~/Library/LaunchAgents/` paths added or
  changed in the diff.
- No secret values present in any added file.

## References

- `docs/launchagents-audit-2026-04-21.md` — original F1/F2 findings.
- `infra/launchagents/README.md` — current LaunchAgent inventory and
  service-owned-plist convention.
- `services/inference-proxy/start.sh` — existing wrapper that the
  preamble above will be added to.
- CLAUDE.md → "Inference Proxy" — documents the
  `~/.sapphire/secrets.env` (mode 0600) pattern used today for
  `MOONSHOT_API_KEY`.
