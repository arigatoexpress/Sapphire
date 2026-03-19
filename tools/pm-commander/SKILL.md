---
name: pm-commander
description: macOS SwiftUI companion app — native menu bar UI for Sapphire control-plane
type: tool
runtime: swift
deploy_target: mac
dependencies: []
entry_point: PMCommanderApp/PMCommanderApp.swift
test_command: swift test
---

# tools/pm-commander

Native macOS SwiftUI app that lives in the menu bar. Provides at-a-glance project status, task creation, and Telegram notification relay without opening a browser.

## Features

- Menu bar popover: active projects, task count, system health
- Quick task creation → posts to control-plane API → syncs to Asana
- Push notification relay from Telegram bot
- Event stream viewer (tag-filtered)

## Build

```bash
cd tools/pm-commander
swift build -c release
# or open Package.swift in Xcode
```

## API Config

Points to control-plane at `http://localhost:8080` (dev) or `https://pm.sapphirealpha.xyz` (prod).
Set via `PM_API_URL` environment variable or app Settings panel.
