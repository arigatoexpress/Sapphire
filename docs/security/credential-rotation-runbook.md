# Credential Rotation Runbook

This runbook is the canonical procedure for rotating any Sapphire-managed
credential after a suspected or confirmed exposure. Treat it as the first
thing to consult during an incident — *before* writing new code.

---

## When to use this runbook

Any of the following triggers a full rotation of the named credential:

- A secret value appears in `git log -p` output (current branch or any history).
- A secret value appears in a screenshot, audit document, chat transcript,
  or external file synced to Proton Drive, Google Drive, iCloud, or any
  third-party system.
- A push to a public repo, public mirror, or external code-review service
  is observed to have included a secret.
- A LaunchAgent plist, dashboard log, or test fixture contained a real
  value rather than a placeholder.
- An operator suspects credential reuse across accounts.

A private GitHub repo *narrows* the blast radius but does not eliminate
the need for rotation: anyone with read access at any point in the
repo's history retains a clone with the secret.

---

## 1. Sapphire-managed credentials

The list below is authoritative. If a credential exists in Sapphire that
is not in this list, add it before rotation. **Never paste credential
values into this file — only names and rotation paths.**

### Inference / model providers

| Credential | Storage path | Rotation procedure |
|---|---|---|
| `MOONSHOT_API_KEY` | `~/.sapphire/secrets.env` | Moonshot console → API Keys → Revoke + Create new → update `~/.sapphire/secrets.env` (mode 0600) → restart `com.sapphire.inference-proxy` |
| `OPENAI_API_KEY` | `~/.sapphire/secrets.env` (when present) | platform.openai.com → API Keys → Revoke + Create → update → restart inference-proxy |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `~/.sapphire/secrets.env` | aistudio.google.com → API keys → Disable + Create new → update → no restart needed (read at call time) |
| `ANTHROPIC_API_KEY` | `~/.config/sapphire-secrets/anthropic_api_key` | console.anthropic.com → Settings → API Keys → Revoke + Create → update file (mode 0600) |

### Telegram

| Credential | Storage path | Rotation procedure |
|---|---|---|
| `KIMI_CLAW_BOT_TOKEN` (legacy `KimiClawBot`) | `~/.config/sapphire-secrets/telegram_bot_token` and `~/.hermes/.env` | BotFather → `/revoke` → `/token` → update both files → restart `ai.hermes.gateway` LaunchAgent |
| `TELEGRAM_BOT_TOKEN` (NemotronRari relay) | `~/.config/sapphire-secrets/telegram_bot_token` | BotFather → `/revoke` → `/token` → update file (mode 0600) → restart `com.sapphire.pm-bot` |
| `RELAY_READER_TOKEN` | `~/.config/sapphire-secrets/relay_reader_token` (if used) | BotFather for the relay bot → `/revoke` → `/token` → update file → reload subscribers |

### Trading + chain

| Credential | Storage path | Rotation procedure |
|---|---|---|
| Robinhood Crypto credentials | `~/.config/sapphire-secrets/robinhood_*` | Robinhood Crypto API console → revoke key pair → generate new Ed25519 pair → update files |
| `SOLANA_WALLET_*` | `~/.config/sapphire-secrets/solana_*` | Move funds to new keypair via wallet UI → generate new keypair → archive old one |
| Hyperliquid API keys | `~/.config/sapphire-secrets/hyperliquid_*` | Hyperliquid UI → API → revoke + create → update files |

### GCP / Foundry

| Credential | Storage path | Rotation procedure |
|---|---|---|
| GCP service-account JSON | `~/.config/sapphire-secrets/gcp_service_account.json` | `gcloud iam service-accounts keys list` → `keys delete` → `keys create` → swap file (mode 0600) → restart `com.sapphire.gcp-sync` |
| Foundry bearer token | `~/.config/sapphire-secrets/foundry_token` | Foundry UI → Tokens → Revoke + Create → update file → no restart (read on each sync) |

### Webhook + dashboard

| Credential | Storage path | Rotation procedure |
|---|---|---|
| `AUTH_PASSWORD` (dashboard basic auth) | `~/.config/sapphire-secrets/dashboard_password` (mirrored into `~/.sapphire/secrets.env` for the LaunchAgent wrapper) | Generate new value (`openssl rand -hex 16`) → update file and `AUTH_PASSWORD` in `~/.sapphire/secrets.env` (mode 0600) → restart `com.sapphire.dashboard` |
| `CONTROL_PLANE_TOKEN` | `~/.config/sapphire-secrets/control_api_token` | Generate new value → update file → restart `com.sapphire.control-plane` |
| `TRADINGVIEW_HMAC_SECRET` | `~/.config/sapphire-secrets/tradingview_hmac_secret` | TradingView alert config → rotate webhook secret → update file → no restart (verified per request) |

---

## 2. Standard procedure (any credential)

1. **Verify scope.** `git log -p --all -S "<old-value-fragment>"` to find every
   commit that contains the value. `rg -F "<old-value-fragment>"` across the
   working tree, Proton Drive mount, and Google Drive mount. Catalogue every
   hit before doing anything else.

2. **Revoke at provider.** Always revoke at the source first. A new
   credential without revoking the old one means both are live until the
   old one expires naturally.

3. **Issue a new credential.** Follow the per-credential row above.

4. **Update the storage path.** Set file mode to `0600` and confirm
   `stat -f "%Sp" <path>` reports `-rw-------`.

5. **Restart consumers.** Use `launchctl kickstart -k system/<label>` for
   LaunchAgents or `~/.local/bin/hermes gateway restart` for Hermes. Watch
   logs (`tail -f ~/.hermes/logs/gateway.error.log`) for auth errors.

6. **Verify with a smoke probe.** For inference keys, run the readiness
   probe: `python3 scripts/ops/production_readiness_sweep.py --include-gemini-live-probe`
   in the appropriate session. For Telegram, send a low-priority canary
   *only with operator approval*.

7. **Delete leaked copies.** Remove the original from Proton Drive,
   Google Drive, screenshot folder, etc. Never just edit the file in
   place — file history may be retained.

8. **Optionally rewrite git history.** For a confirmed leak, run
   `git filter-repo --replace-text <patterns.txt>` and force-push. This
   requires coordinated cleanup of every clone (THO laptop, Windows GPU,
   any collaborator). For a private repo with one author, this is often
   overkill; document the decision either way.

9. **Post-rotation audit.** Confirm:
   - `production_readiness_sweep.py` returns no `manual_gate` for the
     rotated credential's path.
   - `gitleaks detect --redact` returns clean across the working tree.
   - Telegram message canary lands and shows the new bot username (if it
     changed).
   - The tool/plugin/dashboard endpoint backed by the credential returns
     200 on its smoke probe.

---

## 3. Active incidents

This section is appended to during real incidents and never deleted.

### 2026-04-17 — Audit doc credential exposure

**What happened.** `docs/technical-audit-2026-04-16.md` was committed
on 2026-04-17 (commit `5e8241d6`) containing real plist excerpts with the
literal `MOONSHOT_API_KEY` and `KIMI_CLAW_BOT_TOKEN` values. The doc was
deleted on 2026-04-18 (commit `af1ef010`) but the values remain visible
in `git log -p`. A copy of the same audit doc was synced to
`/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/technical-audit-2026-04-16.md`
and was still present as of 2026-04-27.

**Blast radius.**
- GitHub repo `arigatoexpress/Sapphire` is private, so external exposure
  is limited to anyone who held read access between 2026-04-17 and
  rotation.
- The Proton Drive copy is end-to-end encrypted at rest, but anyone with
  the Proton account password (or session cookie) could read it.
- The credential values were reachable from any local clone of the repo.

**Required actions.**
1. Rotate `MOONSHOT_API_KEY` per §1 above.
2. Rotate `KIMI_CLAW_BOT_TOKEN` per §1 above.
3. Delete the Proton Drive copy of the audit doc; verify with
   `ls "/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/technical-audit-2026-04-16.md"`
   returns "No such file" before closing this incident.
4. Decide whether to rewrite git history (commits `5e8241d6` and
   `af1ef010`) using `git filter-repo --replace-text`. If the team is
   one operator, recommended path is *rotate + leave history* and rely on
   secret revocation as the canonical defence.

**Status.** Awaiting operator rotation. This file is the single
canonical record of the incident; do not duplicate.

**2026-04-28 catch-up note.** `docs/security/2026-04-27-proton-audit.md`
records the redacted Proton Drive audit: 24 files inspected, 16 custom
credential-shape candidates, and two default `gitleaks` findings. The
dashboard basic-auth password was also rotated because `sapphire:sapphire`
still returned HTTP 200 locally before rotation; post-rotation probes return
HTTP 401 for that default pair.

---

## 4. Prevention controls now in place

- `pre-commit` runs `gitleaks` against staged changes. The config now
  flags plist `<key>...API_KEY</key>` excerpts with realistic-shaped
  values, not just bare tokens. See `.gitleaks-docs.toml`.
- `.gitignore` excludes ad-hoc audit doc patterns
  (`*-audit-private.md`, `audit-private/`, etc.) so an investigation doc
  written during an incident is never committed by default.
- `scripts/ops/production_readiness_sweep.py` enumerates every required
  credential by *path*; missing files trip the sweep and surface in the
  readiness matrix.
- The dashboard, inference-proxy, control-plane, and pm-bot LaunchAgents
  load secrets from `~/.config/sapphire-secrets/` or `~/.sapphire/secrets.env`
  at runtime; values are never embedded in plists.

The intent is that any future credential exposure either fails the
pre-commit hook, fails the readiness sweep, or is caught by this
runbook before the consequences compound.
