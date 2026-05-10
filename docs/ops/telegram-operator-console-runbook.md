# Telegram Operator Console Runbook

This runbook is the canonical operator-facing reference for the Sapphire
Telegram PM bot in its Wave 4 hardened form. It documents what each
command does, what is deliberately forbidden, the safety posture that
makes the bot acquisition-grade, and how to recover from every reversible
state change the operator can trigger from their phone.

If you can read this and a phone is the only thing you have, you should
be able to get a system-state snapshot, pause a misbehaving routine, and
hand off to the commander Mac without ever risking funds, secrets, or
production data.

---

## 1. Where this lives

| Component | Path |
|---|---|
| Bot dispatcher | `plugins/claw-sapphire/tools/sapphire_pm_bot.py` |
| Safety primitives | `plugins/claw-sapphire/tools/internal/_telegram_safety.py` |
| Bot tests | `plugins/claw-sapphire/tests/test_sapphire_pm_bot.py` |
| Safety tests | `plugins/claw-sapphire/tests/test_telegram_safety.py` |
| Threat model | `docs/security/telegram-operator-threat-model.md` |
| LaunchAgent | `~/Library/LaunchAgents/com.sapphire.pm-bot.plist` |
| Bot token | `~/.config/sapphire-secrets/telegram_bot_token` (mode 0600) |
| Allowlist env | `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS` or `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS_FILE` |
| Pause-flag dir | `~/.sapphire/routine_pause/` |

---

## 2. Allowlist setup

The bot is fail-closed by default. With no allowlist set, **every** request
is denied with a generic message that never reveals which IDs are allowed.

To enable an operator:

1. Have them message the bot once. Use `/whoami` is the right command —
   but they will not get a response (allowlist denies). Instead, the
   bot logs `Denied Telegram PM bot request from user_id=<id>` to
   stderr. Read the LaunchAgent log:

   ```bash
   tail -n 200 ~/Library/Logs/sapphire-pm-bot.err
   ```

2. Add the operator's numeric Telegram user ID to either the comma-separated env
   value in `~/.sapphire/secrets.env`:

   ```
   SAPPHIRE_PM_BOT_ALLOWED_USER_IDS=111222333,444555666
   ```

   or to a file pointed at by the LaunchAgent / shell environment:

   ```
   ~/.config/sapphire-secrets/sapphire_pm_bot_allowed_user_ids
   ```

   with contents such as:

   ```
   111222333,444555666
   ```

3. Restart the LaunchAgent if you changed the env var. If you changed only the
   file-backed allowlist, the next request will pick it up automatically, but a
   restart is still fine if you want a clean boundary:

   ```bash
   launchctl kickstart -k gui/$(id -u)/com.sapphire.pm-bot
   ```

4. Have the operator try `/whoami` again. They should get back their
   own user_id, username, and chat_id.

The allowlist is **not** stored in the bot code, the registry, or any
file that gets committed. Treat the env value as moderately sensitive —
exposing it does not grant access (an attacker still needs to compromise
a Telegram account on the list), but it does narrow the set.

---

## 3. Command reference

All commands assume the operator is on the allowlist. Every command runs
through the gates in this order: live-trading tripwire → allowlist →
forbidden-command guard → rate limit → dispatcher. Any gate failure
returns a generic refusal — the operator will not be told *which* gate
fired (this is by design; see the threat model).

### 3.1 Read-only system state

| Command | Purpose | Output | Side effects |
|---|---|---|---|
| `/help` or `/start` | List all available commands. | MarkdownV2 menu. | None. |
| `/status` | Mesh device + inference proxy + paper-trading + THO health. | MarkdownV2 status block. | None. |
| `/health` | One-line summary from `health_check` tool (brief profile). | `health: GREEN \| green=N yellow=N red=N` | None. |
| `/services` | LaunchAgent + HTTP service status table. | MarkdownV2 table. | None. |
| `/sources` | Agentic Telegram source-registry summary. | Source count, safety defaults, Tier 0 IDs, domain counts, default model roles. | None. |
| `/dev pulse` (also `/dev`, `/pulse`) | Cross-repo PRs + CI + Cloud Run + LaunchAgent health. | MarkdownV2 dev pulse. | None. |
| `/svc status` | Dry-run preview of the service supervisor (what would be restarted). | MarkdownV2 dry-run summary. | None — `dry_run=True` is hard-coded. |
| `/whoami` | Echoes back the requester's user_id, username, chat_id. | MarkdownV2 identity block. | None. |
| `/digest morning` | Today's archived 8 AM morning digest (if it ran). | MarkdownV2 digest, or "no digest found" message. | None. Reads `data/morning_digest/<YYYY-MM-DD>.md`. |
| `/digest dev` | Live `dev_pulse` summary. | MarkdownV2 dev pulse. | None. |

### 3.2 PM workflow (Phase 1 — preserved)

| Command | Purpose | Output | Side effects |
|---|---|---|---|
| `/pm list [--project <id>]` | List up to 10 open PM tasks. | MarkdownV2 grouped by state. | Reads Firestore. |
| `/pm new <title>` | Create a new PM task in the default project. | HTML response with task ID. | Writes one Firestore doc. |
| `/rag <query>` | Query the THO document RAG index. | MarkdownV2 top 3 results. | One HTTPS call to THO. |
| `/claw <prompt>` | Stub. Returns "claw session not yet wired (phase 2)". | Plain text. | None. |

### 3.3 Routines (reversible state changes)

| Command | Purpose | CONFIRM required? |
|---|---|---|
| `/routines list` | List scheduled tasks with `(paused at <timestamp>)` tags. | No — read-only. |
| `/routines status` | List only paused routines with timestamps, including valid flags whose scheduled-task directory is missing. | No — read-only. |
| `/routines pause <name>` | Set a pause flag. Routine skips at startup. | No — pausing is the safe default. |
| `/routines resume <name> CONFIRM` | Remove pause flag. | **Yes**. Without `CONFIRM`, returns the confirmation-required message. |
| `/cancel-routine <name> CONFIRM` | Same as `/routines pause` but with the dangerous-action wording. | **Yes**. |

Pause-flag mechanism: a file at `~/.sapphire/routine_pause/<name>` is
written. Versioned Python LaunchAgent entrypoints call
`lib.core.routine_pause.abort_if_paused("<name>")` at startup, and
prompt-driven Claude scheduled-task skills begin by checking the same
flag path before any repo, cloud, Telegram, or data-writing work. When a
flag is present, the routine logs a structured `routine_pause.skipped`
message and exits successfully. The flag is owned by the operator's UID,
mode `0644` by default. It contains an ISO-8601 UTC timestamp of the
pause time — useful as an audit hint, but **never as authentication**.

Routine names are validated against `^[A-Za-z0-9_\-]{1,64}$`. Anything
with a path separator, shell metacharacter, or longer than 64 characters
is rejected with the generic refusal.

### 3.4 Forbidden — operator-only physical actions

The following slash commands are **always rejected** with the message
"Operator-only physical action. Telegram cannot execute this command.
Run it locally on the commander host with the appropriate confirmation
flow.":

| Stem | Reason |
|---|---|
| `/trade`, `/buy`, `/sell` | Live trading is never allowed from Telegram. |
| `/transfer`, `/withdraw`, `/deposit`, `/wire`, `/send-funds` | Funds movement requires physical access. |
| `/rotate-key`, `/rotate-secret` | Credential rotation runs through the rotation runbook. |
| `/launch`, `/deploy` | Deploys require local CI + signed commits. |
| `/exec`, `/eval`, `/sudo`, `/shell`, `/bash`, `/cmd`, `/ssh` | Shell is the wrong abstraction for a phone. |
| `/kill-switch` | The kill switch is a deliberate physical-act-of-trust. |

The forbidden list is enforced **before** the dispatcher. Even if a future
command file registers `/trade`, the forbidden-command guard will reject
it with the same generic refusal — regardless of whether the dispatcher
would have accepted it. To unblock a command, you must remove its stem
from `FORBIDDEN_COMMAND_PATTERNS` in `_telegram_safety.py`. This requires
a code change + PR review + at least one approving CODEOWNER (because
that file will end up under CODEOWNERS once Wave 4 lands).

---

## 4. Safety posture

### 4.1 Allowlist — fail-closed
The bot loads `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS` at request time and falls back
to `SAPPHIRE_PM_BOT_ALLOWED_USER_IDS_FILE` when the env var is unset. Empty,
unset, unreadable, or all-invalid → empty set → every request is denied.
Invalid CSV entries are logged at WARN and skipped — they never grant access.

### 4.2 Per-user rate limit
Every authenticated request increments a per-user sliding-window counter.
Two windows: 10 commands per minute, 60 per hour (defaults in
`_telegram_safety.DEFAULT_RATE_LIMIT_PER_MINUTE` /
`DEFAULT_RATE_LIMIT_PER_HOUR`). Exceeding either window returns the same
generic refusal as the allowlist denial. This caps a runaway loop or
compromised session before it can exfiltrate by command volume alone.

Rate-limit state is **in-process**. The bot is a single LaunchAgent
process; sharding the bot would require a Redis-backed limiter.

### 4.3 Secret denylist on outgoing text
Every Telegram response passes through a line-based redactor. Any line
containing one of the keyword patterns
(`api_key`, `api-key`, `secret`, `password`, `bearer`, `authorization`,
`private_key`, `access_token`, `refresh_token`, `client_secret`, plus
high-confidence vendor key prefixes — `sk-`, `ghp_`, `xox*`, `AIza`) is
replaced by `[REDACTED:secret]`. False positives are accepted as the
cost of doing business; false negatives are not. If a downstream tool
prints a token into a status string, the operator never sees it on
their phone — even if a maintainer forgets to redact at the source.

### 4.4 Live-trading tripwire
The constant `LIVE_TRADING_DISABLED_FROM_TELEGRAM = True` lives at the
top of `_telegram_safety.py`. The function `assert_no_live_trading()` is
called on every command path — including each new operator-console
command. If a maintainer ever flips the constant without removing the
assertion, the bot raises `RuntimeError` and refuses to dispatch.

This is defense-in-depth. There is also no command-path code that would
*do* anything if the flag were flipped — the bot has no order-placement
surface. The flag exists as a tripwire so a future regression is caught
before the bot has a chance to start trading.

### 4.5 Generic refusal text
Allowlist denial, rate-limit denial, and (for some sub-cases) routine-
name validation failure all return the **identical** text:

> This Sapphire PM bot is not enabled for your Telegram user ID on this host.

This is on purpose. A probe should not be able to enumerate the
allowlist, the rate-limit window, or the routine-name regex by sending
test commands and observing different error messages. Forbidden-command
denials use a different message (operator-only physical action) because
that response is policy, not policy-against-disclosure.

---

## 5. Recovery flows

### 5.1 Operator paused a routine and wants it back

```
/routines status                          # confirm <name> appears with paused_at
/routines resume <name> CONFIRM           # remove the flag
/routines status                          # confirm no pause flag remains
```

If the second command says "No pause flag set," the recovery is already
complete — the file may have been removed manually. Inspect with
`ls -la ~/.sapphire/routine_pause/`.

### 5.2 Operator paused the wrong routine

Identical to 5.1 — pause is reversible. Re-pause the intended routine
afterward.

### 5.3 Bot is rate-limiting an operator who is not abusing

The rate limiter is per-process and resets on bot restart. To clear the
window for one user without restarting the whole bot, you must restart
the LaunchAgent (state is not persisted to disk):

```bash
launchctl kickstart -k gui/$(id -u)/com.sapphire.pm-bot
```

Alternatively, raise `DEFAULT_RATE_LIMIT_PER_MINUTE` / `_PER_HOUR` in
`_telegram_safety.py`, ship a PR, and restart. The defaults exist to
err on the side of safety for a single-operator workload.

### 5.4 Operator's user_id changed (rare — Telegram account migration)

Have them message the bot once, watch the WARN log for the new ID, edit
`SAPPHIRE_PM_BOT_ALLOWED_USER_IDS`, restart the LaunchAgent. Remove the
old ID from the env file after confirming the new one works.

### 5.5 A forbidden command is firing for a legitimate workflow

It almost certainly is not. The forbidden list is intentionally broad
and intentionally conservative. The right response is:

1. Run the action locally on the commander Mac with the appropriate
   physical-act-of-trust flow (CONFIRM token, signed commit, kill-switch
   physical reset, or whatever the action requires).
2. If you genuinely need a Telegram surface for this action, write a
   PR to `_telegram_safety.py` removing the relevant stem from
   `FORBIDDEN_COMMAND_PATTERNS`, plus a new dispatcher branch in
   `sapphire_pm_bot.py`. Both must be CODEOWNER-reviewed.

There is no override path. There never will be.

### 5.6 Bot is silently broken

Symptom: operator sends `/help` and gets nothing back.

1. Check the LaunchAgent is loaded: `launchctl list | grep com.sapphire.pm-bot`.
2. Check the log: `tail -n 200 ~/Library/Logs/sapphire-pm-bot.err`.
3. Verify the bot token: `cat ~/.config/sapphire-secrets/telegram_bot_token | head -c 5; echo`.
4. Restart: `launchctl kickstart -k gui/$(id -u)/com.sapphire.pm-bot`.

If the log shows `Denied Telegram PM bot request`, the operator is not
on the allowlist (see §2). If it shows `Rate-limited`, see §5.3. If it
shows tracebacks, file an incident issue and triage from there — do not
weaken any of the safety posture as a quick fix.

---

## 6. Local verification

Before any change to `sapphire_pm_bot.py` or `_telegram_safety.py`:

```bash
ruff check .
python3 -m pytest plugins/claw-sapphire/tests/test_sapphire_pm_bot.py \
                  plugins/claw-sapphire/tests/test_telegram_safety.py -x --tb=short
python3 -m pytest plugins/claw-sapphire/tests/ tests/unit/ -x --tb=short -q
python3 scripts/validate_tool_registry.py
```

All four commands must pass before the PR is mergeable. CI runs the same
gates. The `validate_tool_registry.py` step is what enforces that
`_telegram_safety.py` is registered and that no untracked tool file is
hiding under `tools/`.

---

## 7. What deliberately is **not** here

- A `/restart-bot` command. Restarting the bot from the bot is a circular
  dependency; use `launchctl` from the Mac.
- A `/log` or `/tail` command. Telegram message size limits make logs
  unsuitable for delivery, and any log that contains a stack trace is
  one downstream-tool slip away from leaking a secret. Use the Mac.
- A `/promote` or `/merge` command. The factory + cloud-routine flow is
  the right surface for that. Telegram cannot place a signing key.
- A `/secret` command. Secrets do not travel through Telegram, full stop.
  Rotate via the credential rotation runbook
  (`docs/security/credential-rotation-runbook.md`).
- A "trusted user" tier. There is one tier: on the allowlist or not. No
  per-user permission grids. If we ever need them, that is a code change
  with CODEOWNER review.

The omissions above are not an oversight. They are the same posture that
makes the bot phone-safe: a small, audited, fail-closed surface area.
