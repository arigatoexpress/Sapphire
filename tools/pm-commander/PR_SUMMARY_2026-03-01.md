# PR Summary (macOS Operator Refresh)

## Suggested title
Modernize PMCommander macOS app, enforce canonical Sapphire routing, and harden operator UX

## Suggested PR body
### Why
The macOS operator app was still capable of routing through deprecated dashboard paths/hosts and lacked a clear, safe configuration flow for operators. This PR aligns the app with the canonical Sapphire platform contracts and updates the native UX to a uniform Apple-glass operator shell.

### What changed
1. Canonical routing enforcement
- Added platform URL normalization in app settings to pin deprecated hosts to `https://sapphirealpha.xyz`.
- Added legacy path remapping for embedded web views (`/command-deck -> /autonomy`, `/settings -> /sapphire-book`).
- Updated embedded tab surfaces to current canonical pages only.

2. Platform contract integration
- Added native `PlatformClient` for canonical `/api/platform/*` calls.
- Added support for `/api/platform/contracts` and in-app contract telemetry (version + endpoint count).

3. Native UI makeover
- Refreshed non-web tabs with a consistent glass visual system and card surfaces.
- Improved top-bar status readability and platform route visibility.
- Refactored large overview layout into maintainable section builders.

4. Settings hardening
- Split settings into explicit `Control Plane` and `Platform` sections.
- Added credential state indicators and safer destructive actions with confirmation dialogs.
- Added quick actions: `Use Canonical URLs`, `Test Connection`.

5. Documentation and handoff
- Updated PMCommander README for canonical routing behavior and surfaces.
- Added release handoff checklist for operators.

### Files changed
- `macos/PMCommanderApp/README.md`
- `macos/PMCommanderApp/Sources/AppSettings.swift`
- `macos/PMCommanderApp/Sources/DashboardViewModel.swift`
- `macos/PMCommanderApp/Sources/Models.swift`
- `macos/PMCommanderApp/Sources/PlatformClient.swift`
- `macos/PMCommanderApp/Sources/Views.swift`
- `macos/PMCommanderApp/RELEASE_HANDOFF_CHECKLIST_2026-03-01.md`

### Validation performed
- `swift build` (debug): PASS
- `swift build -c release`: PASS
- Packaged and launched updated bundle: `/Applications/PMCommander.app`
- Verified canonical platform contract endpoint:
  - `GET https://sapphirealpha.xyz/api/platform/contracts`
  - response snapshot: `version=v1`, `count=13`, `auth_enabled=false`

### Operator impact
- Existing users with legacy platform URLs are auto-migrated to canonical routing.
- Embedded pages no longer rely on deprecated dashboard surfaces.
- Settings and credential handling are safer and clearer for production operations.

### Rollback
- Reinstall previous `/Applications/PMCommander.app` bundle from backup if needed.
- Reset URLs via in-app `Use Canonical URLs`.
- Revert commits in this PR range if full code rollback is required.

## Commit range for this PR
- `7274ad0` Modernize macOS operator app and enforce canonical platform routing
- `1e40281` Polish native macOS operator UI with unified glass surfaces
- `174b576` Harden macOS settings UX and credential safety flows
- `95b5686` Add macOS operator release handoff checklist
