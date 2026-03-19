# PMCommander macOS Release Handoff (2026-03-01)

## Scope
This release updates the native macOS operator app to:
- enforce canonical platform routing (`https://sapphirealpha.xyz`),
- stop embedding deprecated dashboard surfaces,
- align UI with unified Apple-glass shell,
- expose platform contract status (`/api/platform/contracts`) in-app.

## Included commits (branch: `codex/telegram-ops-topology`)
- `7274ad0` Modernize macOS operator app and enforce canonical platform routing
- `1e40281` Polish native macOS operator UI with unified glass surfaces
- `174b576` Harden macOS settings UX and credential safety flows

## Runtime behavior changes
1. Canonical URL migration
- Deprecated dashboard hosts are auto-normalized to `https://sapphirealpha.xyz`.
- Legacy path fallbacks are remapped to canonical paths (e.g., `/command-deck` -> `/autonomy`).

2. Embedded surfaces updated
- Active web tabs now target current platform pages:
  - `/feed`, `/autonomy`, `/trading`, `/system-health`, `/logs`, `/projects`, `/infrastructure`, `/production-readiness`, `/organization`, `/sapphire-book`.

3. Native UX refresh
- Unified glass visual shell across native tabs.
- Stronger top-bar telemetry badges.
- Settings redesigned with explicit credential sections and confirmation dialogs for destructive actions.

4. Contract awareness
- App fetches `/api/platform/contracts` and surfaces contract version/count in the header.

## Build + package status
- Local debug build: `swift build` PASS
- Production package script: `./scripts/package_pm_commander_app.sh` PASS
- App deployed and launched at:
  - `/Applications/PMCommander.app`

## Smoke checklist (operator)
1. Open app and check top badges:
- `Cloud`, `Nodes`, `Readiness`, `Contracts` visible.

2. Open Settings:
- Platform URL shows canonical `https://sapphirealpha.xyz`.
- `Use Canonical URLs` works.
- `Test Connection` updates telemetry.
- Clear credential actions require confirmation.

3. Open each embedded tab and verify load:
- Feed, Autonomy, Trading, System Health, Logs, Projects, Infrastructure, Readiness, Organization, Sapphire Book.

4. Verify platform contract endpoint manually:
- `curl -u sapphire:<password> https://sapphirealpha.xyz/api/platform/contracts`
- Ensure endpoint count and version fields are present.

## Rollback plan
1. Re-open prior packaged app bundle from backup if needed.
2. Reset app settings to canonical defaults in Settings.
3. Rebuild from commit `8dae7f1` (branch baseline) only if a hard rollback is required.

## Notes
- This branch contains unrelated workspace dirt outside app sources; release commit scope is limited to `macos/PMCommanderApp/*` source and README updates.
