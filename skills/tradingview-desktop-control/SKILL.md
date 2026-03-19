---
name: tradingview-desktop-control
description: Control the local TradingView Desktop app on macOS through UI automation (AppleScript/System Events) using the user's already logged-in desktop session. Use when Codex needs to automate TradingView actions such as focusing the app, sending hotkeys, typing into UI fields, clicking menu items, switching symbols/timeframes/layouts, or running repeatable charting workflows in the desktop app rather than the browser. This skill uses visible UI access only and does not bypass TradingView subscription restrictions, account permissions, or broker protections.
---

# TradingView Desktop Control

## Overview

Automate the running macOS TradingView desktop app via Accessibility-enabled UI scripting.
Use the bundled `scripts/tvctl.py` tool for deterministic actions instead of hand-writing AppleScript each turn.
Use `scripts/tv_inventory.py`, `scripts/tv_web_inventory.py`, `scripts/tv_registry_merge.py`, `scripts/tv_resolve_capability.py`, `scripts/tv_plan_intent.py`, and `scripts/tv_execute_plan.py` to enumerate capabilities, build/query a merged registry, plan actions, and execute them with risk gates/verification hooks.

## Quick Start

1. Verify the app is reachable:

```bash
python3 scripts/tvctl.py status
python3 scripts/tvctl.py list-menus
```

2. Bring TradingView to the front:

```bash
python3 scripts/tvctl.py activate --launch
```

3. Send UI actions (hotkeys, typing, menu clicks):

```bash
python3 scripts/tvctl.py hotkey "cmd+k"
python3 scripts/tvctl.py type "AAPL"
python3 scripts/tvctl.py press return
```

4. Use higher-level chart/indicator workflows:

```bash
python3 scripts/tvctl.py set-symbol "AAPL"
python3 scripts/tvctl.py add-indicator "RSI"
```

5. Calibrate watchlist field coordinates (for watchlist editing/search):

```bash
python3 scripts/tvctl.py config-init config/layouts/my-layout.json --layout-name my-layout
python3 scripts/tvctl.py window-bounds
python3 scripts/tvctl.py mouse-location
# then use normalized window coordinates (0..1)
python3 scripts/tvctl.py watchlist-search "TSLA" 0.90 0.10 --normalized-window
# or timed point capture into config (move mouse during prompts)
python3 scripts/tvctl.py calibrate-watchlist config/layouts/my-layout.json --delay-per-point 8
```

6. For repeatable workflows, run a JSON sequence:

```bash
python3 scripts/tvctl.py run-sequence references/examples/change-symbol.json
```

7. Build and merge capability inventories (desktop + web):

```bash
python3 scripts/tv_inventory.py --pretty --write-default-registry
python3 scripts/tv_web_inventory.py --url https://www.tradingview.com/chart/ --headed --write-default-output
python3 scripts/tv_registry_merge.py \
  references/examples/capability-registry.seed.json \
  output/tv-web-inventory.json \
  --write-default-output
```

8. Enumerate targeted TradingView Web contexts (dialogs/menus) using label-based action plans:

```bash
python3 scripts/tv_web_inventory.py \
  --url https://www.tradingview.com/chart/ \
  --actions-file references/examples/web-inventory-plans/open-indicators-dialog.json \
  --capture-label indicators-dialog \
  --output output/tv-web-inventory.indicators.json
```

9. Resolve intents against the merged registry:

```bash
python3 scripts/tv_resolve_capability.py "open indicators" --registry output/capability-registry.merged.latest.json
python3 scripts/tv_resolve_capability.py "settings" --prefer-surface-family web_ui
python3 scripts/tv_resolve_capability.py "watchlist add symbol" --only-actionable
```

10. Produce an executable plan (with parameter extraction + risk gating):

```bash
python3 scripts/tv_plan_intent.py 'set chart symbol AAPL'
python3 scripts/tv_plan_intent.py 'add indicator "RSI"'
python3 scripts/tv_plan_intent.py 'remove watchlist row' --max-risk low
```

11. Execute a planned action with confirmation + verification hooks:

```bash
python3 scripts/tv_execute_plan.py 'open settings' --prefer-surface-family web_ui --yes
python3 scripts/tv_execute_plan.py 'add indicator "RSI"' --dry-run
python3 scripts/tv_execute_plan.py 'remove watchlist row' --max-risk low --yes
```

## Workflow

1. Probe current UI state with `status`, `list-menus`, and optionally `window-titles`.
2. Prefer keyboard shortcuts and menu clicks over coordinate-based clicking.
3. Use built-in high-level commands (`set-symbol`, `add-indicator`) for common chart workflows.
4. For watchlist editing/search, calibrate a watchlist input point and use normalized window coordinates.
5. Prefer config-backed watchlist macros after calibration (`watchlist-*-config`) to avoid retyping coordinates.
6. Type symbols/values only after focusing the intended field/panel.
7. Insert short delays between dependent UI steps (`wait` action or separate command).
8. Re-check state after important steps (menu presence, window title, screenshot if needed).

## Commands

Use `python3 scripts/tvctl.py --help` and `python3 scripts/tvctl.py <subcommand> --help`.

Core subcommands:

- `status`: print JSON with running/frontmost/menu discovery info
- `activate [--launch]`: focus TradingView; optionally launch it first
- `list-menus`: list top-level menu bar items visible to macOS UI scripting
- `window-titles`: list accessible window names (may be empty for some Electron states)
- `window-bounds`: return front window bounds for coordinate calibration
- `mouse-location`: return current pointer coordinates
- `config-init <file>`: create a per-layout config JSON (points + shortcuts)
- `config-show <file>`: print config JSON
- `config-set-shortcut <file> <key> <combo>`: store shortcut overrides (`symbol_search`, `indicator_search`)
- `config-set-point <file> <name> <x> <y>`: store a named point manually
- `config-capture-point <file> <name>`: capture current mouse position into config (supports delay + normalized coords)
- `calibrate-watchlist <file>`: timed capture of common watchlist points (search, add, rows, remove menu item)
- `config-bind-watchlist <file>`: remap watchlist point names in config
- `hotkey "<combo>"`: send combo like `cmd+k`, `shift+cmd+p`, `esc`
- `press <key> [--mods ...] [--times N]`: send special keys (`return`, `tab`, `esc`, arrows, etc.)
- `type "<text>" [--interval 0.02]`: type text into the focused UI element
- `click-menu "Top > Item > Subitem"`: click a menu path
- `move-mouse <x> <y>`: move pointer (supports `--relative-window` and `--normalized-window`)
- `click <x> <y>`: click pointer target (supports left/right, repeated clicks, window-relative coords)
- `drag <x1> <y1> <x2> <y2>`: drag rows/panes (useful for watchlist reorder)
- `search "<query>"`: generic shortcut-opened search flow (`--open-combo` overrideable)
- `set-symbol "<symbol>"`: open symbol search and switch chart symbol (default `cmd+k`)
- `add-indicator "<query>"`: open indicators search and add/select indicator (default `/`, overrideable)
- `watchlist-search "<query>" <x> <y>`: click watchlist search/input field by coordinate and type query
- `watchlist-open "<symbol>" <x> <y>`: click watchlist field, type symbol, confirm
- `watchlist-open-config <config> "<symbol>"`: open/switch symbol using the configured watchlist search point
- `watchlist-add-config <config> "<symbol>"`: add symbol using configured add/search point
- `watchlist-remove-config <config>`: right-click configured row point, click configured remove menu point
- `watchlist-reorder-config <config>`: drag between configured row points
- `tv_inventory.py`: export desktop/menu/config inventory and a capability-registry seed
- `tv_web_inventory.py`: enumerate visible TradingView Web controls via Playwright CLI snapshot + DOM extraction
- `tv_web_inventory.py` now also emits executable web `action_recipe`s for many interactive controls (buttons/tabs/menuitems) plus curated multi-step web flows (indicators search, alerts, layout/settings, quick search), with declarative post-capture verification assertions
- `tv_registry_merge.py`: merge desktop/web inventories and registries into a canonical merged registry + clusters
- `tv_resolve_capability.py`: rank the best capability/action candidates for a user intent using the merged registry
- `tv_plan_intent.py`: choose an executable action recipe from the merged registry, infer parameters, and emit a command preview for supported runners (`tvctl.py`, `tv_web_inventory.py`)
- `tv_execute_plan.py`: execute the selected recipe (desktop or web) with confirmation/risk gates and optional pre/post verification hooks; web recipes can return `verification_failed` when post-capture assertions do not match
- `wait <seconds>`: sleep between steps
- `run-sequence <file.json>`: execute a JSON list of actions

Coordinate notes:

- `--normalized-window` treats `x` and `y` as `0..1` fractions of the front TradingView window.
- This is usually the most stable way to target watchlist inputs/buttons across window moves/resizes.

## Sequence Format

Pass a JSON file containing a list of action objects:

```json
[
  { "action": "set-symbol", "symbol": "AAPL", "launch": true },
  { "action": "wait", "seconds": 0.3 },
  { "action": "add-indicator", "query": "RSI" },
  {
    "action": "config-watchlist-open",
    "config": "config/layouts/aribs-main.json",
    "symbol": "BTCUSDT"
  }
]
```

Supported actions:

- `activate`, `wait`, `hotkey`, `press`, `type`, `click-menu`
- `move-mouse`, `click`, `drag`
- `search`, `set-symbol`, `add-indicator`
- `watchlist-search`, `watchlist-open`
- `config-watchlist-open`, `config-watchlist-add`, `config-watchlist-remove`, `config-watchlist-reorder`

Example watchlist step using normalized coordinates:

```json
{ "action": "watchlist-search", "query": "ETH", "x": 0.90, "y": 0.10, "normalized_window": true }
```

## Safety Rules

- Treat broker/order entry, order modification, and order cancellation as high risk.
- Require explicit user confirmation before any live trading action, even if the UI is accessible.
- Stop if an unexpected modal, login prompt, CAPTCHA, or broker confirmation appears.
- Use visible UI only; do not claim unsupported API-level or hidden internal access.
- Keep automation scoped and reversible; avoid long unattended loops.

## Limitations

- Premium features are available only through the currently signed-in TradingView desktop session.
- This skill cannot bypass TradingView paywalls, broker permissions, or platform restrictions.
- Electron UI elements may not expose a full accessibility tree; use hotkeys and menus first.
- Watchlist controls may require coordinate-based targeting because TradingView exposes sparse AX metadata.
- Window titles may be unavailable in some app states.

## Troubleshooting

- If commands fail with assistive access errors, grant Accessibility access to Codex/Terminal.
- If the app is running but not responding, call `activate` and retry with a short `wait`.
- If a shortcut differs from expectations, inspect TradingView menus and use `click-menu`.
- If watchlist automation misses the target, recalibrate using `window-bounds` + `mouse-location` and switch to `--normalized-window`.
- If UI focus is wrong, send `esc` and re-open the intended panel before typing.

## References

- Read `references/usage-notes.md` for permissions, patterns, and example automation recipes.
- Read `references/layout-config.md` for the config schema and a one-pass calibration workflow.
- Read `references/capability-registry-schema.json` for the capability registry format used by inventory scripts.
- Read `references/web-inventory-workflow.md` for web inventory action-plan syntax and targeted context capture workflow.
- Read `references/resolver-workflow.md` for merged-registry intent resolution and scoring usage.
- Read `references/planner-workflow.md` for intent-to-recipe planning, parameter extraction, and risk gating.
- Read `references/executor-workflow.md` for recipe execution, risk gates, and verification hooks.
