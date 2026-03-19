# Sapphire Operator Client (macOS)

Native SwiftUI operator client for the unified Sapphire platform.

## Features

- Control-plane health: online agents, queue, leases, failures.
- Agent monitor with heartbeat age and capability visibility.
- Queue monitor for queued, leased, and failed tasks.
- Project board and tracked-project health summary.
- Embedded unified web dashboards:
  - `Organization & Programs` (`/organization`)
  - `Market & Intelligence` (`/intelligence`)
  - `Platform Reliability` (`/platform`)
  - `Activity Stream` (`/activity`)
  - `Sapphire Book` (`/sapphire-book`)
- Secure token storage in macOS Keychain.
- In-app control actions:
  - `Sync Board`
  - `Autonomy Cycle`
  - `Assistant Check-In`
  - `Refresh Quotas`
  - `Run Deep Research`

## Run

```bash
cd "/Users/aribs/Documents/Organized/Codex Projects/macos/PMCommanderApp"
swift run PMCommanderApp
```

## Build release binary

```bash
cd "/Users/aribs/Documents/Organized/Codex Projects/macos/PMCommanderApp"
swift build -c release
```

## Package clickable macOS app bundle

```bash
cd "/Users/aribs/Documents/Organized/Codex Projects"
./scripts/package_pm_commander_app.sh
```

This creates and opens `/Applications/PMCommander.app` with the generated icon from
`/Users/aribs/Documents/Organized/Codex Projects/macos/PMCommanderApp/Assets/AppIcon.source.png`.

## First launch setup

1. Open `Settings` in the app.
2. Set the PM Hub control URL and `CONTROL_PLANE_TOKEN`.
3. Set the unified platform URL + basic auth credentials.
4. Save and confirm both control and platform metrics load.

Notes:
- Deprecated dashboard hosts are auto-migrated to canonical `https://sapphirealpha.xyz`.
- Legacy web paths are remapped to current canonical surfaces (for example `/trading` -> `/intelligence`, `/logs` -> `/activity`).
