# 2026-04-27 Proton Drive Credential Audit

Status: open for operator deletion and provider-side rotation.

This report records the redacted audit of
`/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/`.
It intentionally contains paths, line numbers, detector classes, and short
fingerprints only. It does not contain credential values.

## Verification Summary

Commands were run on 2026-04-28 UTC from a clean Sapphire worktree.

| Check | Result |
|---|---:|
| Recursive files inspected | 24 |
| Symlinks observed | 0 |
| `gitleaks dir --redact=100` findings | 2 |
| Custom credential-shape candidates | 16 |
| Private-key blocks detected | 0 |

The specific URL alleged in the Cowork handoff,
`https://jessica-quite-permissions-jonathan.trycloudflare.com/`, did not
resolve during verification. The local `com.sapphire.cloudflare-tunnel`
LaunchAgent was running `cloudflared tunnel --url http://localhost:8080`, but
its logs showed repeated Cloudflare control-stream failures and no current
public `trycloudflare.com` URL. Because no reachable tunnel URL was verified,
no Cloudflare process was killed during this pass.

The dashboard basic-auth catch-up did find weak default access locally:
`sapphire:sapphire` returned HTTP 200 before rotation. The password was rotated
without printing the new value, `~/.sapphire/secrets.env` and
`~/.config/sapphire-secrets/dashboard_password` were set mode `0600`, and
`com.sapphire.dashboard` was restarted. Post-rotation probes returned HTTP 401
for no auth, HTTP 401 for `sapphire:sapphire`, and HTTP 200 for the newly stored
credential.

## Redacted Findings

| Severity | File | Line | Evidence class | Fingerprint |
|---|---|---:|---|---|
| High | `cloud-audit-2026-04-15.md` | 101 | markdown code block / env assignment | `52e0999cf162` |
| Medium | `cloud-audit-2026-04-15.md` | 108 | token-shaped string | `1b0082856a68` |
| Medium | `cloud-audit-2026-04-15.md` | 109 | token-shaped string | `b47d5000790d` |
| Low | `cloud-audit-2026-04-15.md` | 109 | token-shaped string | `62bb62b21ad4` |
| Low | `overnight-technical-report-2026-04-16.md` | 44 | config key / placeholder reference | `ab5df625bc76` |
| Low | `overnight-technical-report-2026-04-16.md` | 70 | token-shaped string | `6ef7e58f77c7` |
| Medium | `overnight-technical-report-2026-04-16.md` | 168 | token-shaped string | `d59062faf218` |
| Medium | `overnight-technical-report-2026-04-16.md` | 173 | token-shaped string | `8c6033e10185` |
| Medium | `overnight-technical-report-2026-04-16.md` | 178 | token-shaped string | `85cd46859d1e` |
| Medium | `security-investigation-2026-04-15.md` | 99 | token-shaped string | `2a0bbfffa3b9` |
| Medium | `system-cohesion-audit.md` | 315 | token-shaped string | `33b30fe56678` |
| High | `technical-audit-2026-04-16.md` | 48 | markdown code block / provider key shape | `37f07e24875b` |
| High | `technical-audit-2026-04-16.md` | 50 | markdown code block / Telegram token shape | `3c2ce2783a65` |
| High | `technical-audit-2026-04-16.md` | 239 | credential-bearing URL | `10bbdf4a6566` |
| Low | `threats.json` | 10 | JSON string / generic API-key detector hit | `generic-api-key` |
| Medium | `threats.json` | 12 | token-shaped string | `8266aec27d0f` |

## Operator Deletion Checklist

Do not delete Proton Drive files from automation. The operator should perform
this checklist from the Proton client or web UI.

1. Confirm provider-side rotation/revocation is complete for every High finding.
2. Delete or permanently redact these Proton Drive files:
   - `cloud-audit-2026-04-15.md`
   - `technical-audit-2026-04-16.md`
   - any local versions or exports containing the same fingerprints above
3. Triage and either redact or dismiss the Medium/Low findings in:
   - `overnight-technical-report-2026-04-16.md`
   - `security-investigation-2026-04-15.md`
   - `system-cohesion-audit.md`
   - `threats.json`
4. Empty Proton Drive trash and remove any version-history copies exposed by the
   Proton client.
5. Re-run `gitleaks dir --redact=100` against the Proton `Sapphire-OS/` folder.
6. Re-run a custom token-shape scan for the fingerprints in this report.
7. Update `docs/security/credential-rotation-runbook.md` when all High findings
   are rotated and deleted.

## Repository Follow-Up

- `.gitleaks-docs.toml` now includes a docs-scoped plist credential rule for
  `<key>...API_KEY|TOKEN|SECRET</key>` snippets with realistic value shapes.
  Local CI and pre-commit both run this rule in addition to the default
  `.gitleaks.toml` rules.
- `services/dashboard/start.sh` now honors
  `~/.config/sapphire-secrets/dashboard_password`, matching the runbook.
- `services/dashboard/app.py` now fails closed if `AUTH_PASSWORD` is the known
  default value.
