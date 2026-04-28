# Telegram Operator Console — Threat Model

This is the short-form threat model for the Sapphire Telegram PM bot
operator console. It complements the runbook at
`docs/ops/telegram-operator-console-runbook.md` (which is the prose
reference for the operator) and the unit tests at
`plugins/claw-sapphire/tests/test_telegram_safety.py` (which are the
machine-checked posture). Read all three when reviewing a PR that
touches the bot.

---

## 1. Trust boundary

The Telegram bot sits at a deliberate trust boundary between two zones:

* **Phone zone** — the operator's Telegram client, the Telegram cloud
  infrastructure, the bot token, and any other Telegram users who could
  spoof the operator.
* **Commander zone** — the Mac that runs the bot LaunchAgent, the local
  filesystem, the Sapphire data directory, and the Firestore/Cloud Run
  surfaces that the bot talks to.

The bot is the only path between the two. Anything that crosses the
boundary in either direction is in scope for this model.

The boundary is **asymmetric**: the phone zone is treated as semi-
trusted (the operator has to be allowlisted, but the bot still assumes
the channel could be observed); the commander zone is fully trusted
(the bot runs as the operator's UID with full filesystem access).

---

## 2. Attacker profile

The model assumes an attacker who has at least one of:

| Attacker capability | Realistic? | What it grants |
|---|---|---|
| Knowledge of the bot's Telegram username | Yes | Can send arbitrary messages and observe responses. |
| Telegram account compromise of an allowlisted operator | Plausible (phishing, SIM swap) | Full bot access until the allowlist entry is removed. |
| Read access to a checkout of the Sapphire repo | Likely (the repo is shared with collaborators) | Knowledge of the bot code, the safety regex, the forbidden-command list, and where secrets live in the home dir. |
| Read access to the Mac filesystem | Unlikely | Direct read of bot token, allowlist env file, and Sapphire data. |
| Code-execution on the Mac as the operator | Out of scope | The bot's safety posture cannot mitigate this — game over for a much bigger surface than the bot. |

The *primary* threat is "compromised Telegram account of an allowlisted
operator." Most of the safety controls below are designed against that
attacker.

---

## 3. Mitigations

### 3.1 Fail-closed allowlist
**Threat:** an attacker who knows the bot username can send commands.
**Mitigation:** the bot rejects every request whose sender is not in
`SAPPHIRE_PM_BOT_ALLOWED_USER_IDS`. The default (env var unset) denies
everyone. The refusal text is identical for every denial so the
attacker cannot enumerate the allowlist by probing.

### 3.2 Generic refusal text
**Threat:** an attacker probes commands to learn the rate-limit window,
allowlist size, or routine-name regex.
**Mitigation:** allowlist denial, rate-limit denial, and routine-name
validation failure all return the same string. Forbidden-command denial
uses a different (but equally generic) string because that one is
policy disclosure, not configuration disclosure.

### 3.3 Per-user rate limit
**Threat:** a compromised operator account is used to flood the bot with
queries for exfiltration (e.g. `/digest dev` repeatedly to scrape Cloud
Run state and PR details).
**Mitigation:** sliding-window limiter caps any user at 10/minute and
60/hour. State is in-process — restarting the bot resets the window,
which is acceptable because compromise detection is not the limiter's
job (the goal is to *cap impact*).

### 3.4 Secret-keyword denylist on outgoing text
**Threat:** a downstream tool (health_check, dev_pulse, status) prints a
token, API key, or password into a status string. The bot would relay
that to the operator's Telegram chat, which is now in the phone zone.
**Mitigation:** every outgoing response runs through a line-based
redactor that replaces any line containing a secret-like keyword with
`[REDACTED:secret]`. The redactor is deliberately broad (matches
"api_key", "secret", "password", "bearer", plus vendor key prefixes
like `sk-`, `ghp_`, `xox*`, `AIza`). False positives are accepted; a
status report with one redacted line is fine.

### 3.5 Forbidden-command guard
**Threat:** a future maintainer adds a command that places trades,
moves funds, runs shell, or rotates a credential, and the operator's
phone is now a high-blast-radius target.
**Mitigation:** the dispatcher cannot reach the handler if the message
matches the forbidden-command regex (`/trade`, `/buy`, `/sell`,
`/transfer`, `/withdraw`, `/rotate-key`, `/launch`, `/exec`, `/eval`,
`/sudo`, `/shell`, etc.). The guard is enforced *after* allowlist —
even an allowed user attempting a forbidden command is rejected. To
unblock a stem, a maintainer must edit the safety module, ship a PR,
and pass CODEOWNER review.

### 3.6 Live-trading tripwire
**Threat:** a future regression silently enables a trading code path
inside the bot.
**Mitigation:** `LIVE_TRADING_DISABLED_FROM_TELEGRAM = True` plus
`assert_no_live_trading()` called on every command path. If the
constant is flipped without removing the assertion, the bot raises
`RuntimeError` and refuses to dispatch. There is also no command-path
code that *would* trade if the flag flipped — the bot has no order
surface. The tripwire exists to catch a maintainer mistake.

### 3.7 Routine-name validation + scoped pause directory
**Threat:** an attacker uses the routine-pause feature to write outside
the operator's home directory or trigger shell injection in a future
consumer of the flag file.
**Mitigation:** routine names are validated against
`^[A-Za-z0-9_\-]{1,64}$`. The pause directory is `~/.sapphire/routine_pause/`,
owned by the operator's UID. Path traversal, shell metacharacters, and
oversized names are rejected with the generic refusal.

### 3.8 No persistent state in source control
**Threat:** the allowlist or operator IDs leak via a git push.
**Mitigation:** the allowlist is an env var read from
`~/.sapphire/secrets.env` (mode 0600), which is never committed.
Pre-commit hooks (gitleaks) catch secret-like strings on staged files.

---

## 4. Residual risks

### 4.1 Telegram channel is observable to Telegram, Inc.
The bot token authenticates the bot to the Telegram cloud, which is
operated by Telegram, Inc. Messages relayed via the bot pass through
Telegram's servers in plaintext (Telegram does not provide end-to-end
encryption for bot conversations). An attacker who compromises Telegram
infrastructure could observe operator commands and bot responses. The
secret-redactor mitigates this for outgoing text; for incoming text,
the residual exposure is the metadata (which commands were run when).
This is intrinsic to bot architecture and accepted for the operational
benefit.

### 4.2 Telegram account compromise
A compromised operator Telegram account grants full bot access. The
rate limiter caps the blast radius, but a sustained-but-slow attacker
still has the read-only operator surface (status, services, dev_pulse,
RAG, PM list). No live trading, no fund movement, no shell — those are
ruled out by §3.5. Recovery: remove the operator's user_id from
`SAPPHIRE_PM_BOT_ALLOWED_USER_IDS`, restart the LaunchAgent, rotate
their Telegram session.

### 4.3 Rate limiter resets on restart
In-process state means a frequent-restart attacker bypasses the hourly
cap. Realistically, the LaunchAgent restarts once or twice a day in
steady state, and the per-minute window is the tighter constraint
anyway. If we ever shard the bot, move state to Redis.

### 4.4 Routine-pause flag is filesystem-owned, not authenticated
A file in `~/.sapphire/routine_pause/` is treated as ground-truth by
scheduled tasks. An attacker with code-execution on the Mac as the
operator can create or remove these flags freely — but at that point
they have already escaped the trust boundary the bot is meant to
defend, and we are in incident-response territory.

---

## 5. What the model deliberately does not cover

* Service availability of the Telegram cloud. If Telegram is down, the
  bot is unreachable, but the LaunchAgent supervisor + the in-person
  Mac console keep the system operable.
* The security of the Telegram bot token itself. That is covered by
  the credential rotation runbook (`docs/security/credential-rotation-runbook.md`).
* The internal security of the downstream tools (`health_check`,
  `dev_pulse`, `service_supervisor`). They have their own SKILL.md /
  threat-model context where applicable.
* Cryptographic weaknesses in Telegram's bot API. Out of scope.
* Insider risk of the only operator on the allowlist. The bot is not a
  defense against the legitimate operator going rogue; that is what
  the offline kill-switch + cold-storage Solana wallet are for.

---

## 6. Review trigger

Re-read this document before any of:

* Adding a new command to `sapphire_pm_bot.py`.
* Changing `_telegram_safety.py` (especially the regex tables or the
  rate-limit defaults).
* Loosening the forbidden-command list.
* Changing the bot's transport (e.g. moving to webhooks, adding a
  parallel SMS/Slack surface).

CODEOWNER review is required for any of the above. The default reviewer
is the platform owner; security-sensitive changes pull in a second
reviewer per the CODEOWNERS file.
