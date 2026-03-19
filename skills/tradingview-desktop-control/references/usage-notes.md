# TradingView Desktop Control Usage Notes

## What This Skill Can Actually Access

- It can drive the visible macOS TradingView desktop app through Accessibility/UI scripting.
- It uses your existing signed-in desktop session, so premium features are available if they are visible in that UI.
- It can also enumerate visible TradingView Web controls/capabilities using Playwright CLI (`tv_web_inventory.py`) when the web app offers better semantic DOM access than the desktop AX tree.
- Web inventory output now includes executable `action_recipe`s for many interactive web controls (for example `Settings`, `Indicators`, `Create Alert`) that can be planned/executed via `tv_plan_intent.py` + `tv_execute_plan.py`.
- It cannot bypass TradingView plan limits, hidden feature flags, broker permissions, or confirmations.
- It cannot reliably introspect every Electron UI element; prefer hotkeys and menu actions.
- For watchlist interactions, coordinate-based clicks are often necessary because the AX tree is sparse.

## Permissions Checklist (macOS)

- Accessibility: grant access to Codex (and/or the shell host it uses) so `System Events` can send keystrokes/clicks.
- Automation prompts: allow controlling `System Events` if macOS asks.
- Screen Recording (optional): grant if a workflow also captures screenshots for verification.

## Recommended Automation Pattern

1. `activate` the app and wait briefly.
2. Use `list-menus` to confirm the process is reachable.
3. Use a shortcut or menu to open a known panel.
4. `type` text only after focus is clearly in the correct input.
5. Add small waits between dependent UI changes.
6. Re-check state before repeating or branching.
7. Save stable points into a layout config and use config-backed macros for repeat work.

For watchlist workflows:

1. Run `window-bounds` and `mouse-location` while hovering the watchlist search field.
2. Convert to normalized coordinates (recommended), or use `--relative-window`.
3. Use `watchlist-search` / `watchlist-open` with those coordinates.
4. For row reorder, use `drag` with normalized row anchor points.

## High-Risk Actions (Require Explicit User Confirmation)

- Anything involving broker connection, order entry, order modification, or cancellation
- Bulk alert deletion
- Layout/workspace overwrite operations
- Account/profile or billing/settings changes

## Example Recipes

### Generate Desktop Capability Inventory + Registry Seed

```bash
python3 scripts/tv_inventory.py --pretty --write-default-registry
```

This exports:

- Desktop status + menu tree (recursive)
- Layout config points/shortcuts (if present)
- Seed capability registry (`references/examples/capability-registry.seed.json`)

### Merge Desktop + Web Inventories into a Canonical Registry

```bash
python3 scripts/tv_registry_merge.py \
  references/examples/capability-registry.seed.json \
  output/tv-web-inventory.json \
  --write-default-output
```

The merged registry includes:

- deduplicated capability nodes (`capabilities`) grouped by surface family + label
- cross-surface label clusters (`clusters`) for the same capability appearing in multiple extraction methods
- input provenance (which inventory file each observation came from)

### Resolve Intents Against the Merged Registry

```bash
python3 scripts/tv_resolve_capability.py "open indicators" --registry output/capability-registry.merged.latest.json
python3 scripts/tv_resolve_capability.py "watchlist add symbol" --only-actionable
python3 scripts/tv_resolve_capability.py "settings" --prefer-surface-family web_ui
```

`tv_resolve_capability.py` returns ranked candidates with:

- score
- matching reasons (token overlap, canonical alias match, etc.)
- action recipe (when available)
- risk level and surface family

### Plan an Executable Action From Intent (Resolver + Recipe Selection)

```bash
python3 scripts/tv_plan_intent.py 'set chart symbol AAPL'
python3 scripts/tv_plan_intent.py 'add indicator "RSI"'
python3 scripts/tv_plan_intent.py 'open indicators'
python3 scripts/tv_plan_intent.py 'remove watchlist row' --max-risk low
```

`tv_plan_intent.py` adds:

- executable recipe selection (prefers actionable capabilities even if the top match is descriptive-only)
- parameter extraction for common placeholders (for example `symbol`, `query`)
- risk gating (`--max-risk low|medium|high`) so destructive/risky actions can be blocked instead of silently substituted
- a command preview for the selected recipe (desktop `tvctl.py` or web `tv_web_inventory.py`)

### Execute Planned Actions (Desktop + Web)

```bash
python3 scripts/tv_execute_plan.py 'open settings' --prefer-surface-family web_ui --yes
python3 scripts/tv_execute_plan.py 'open indicators' --prefer-surface-family web_ui --yes
python3 scripts/tv_execute_plan.py 'add indicator "RSI"' --dry-run
python3 scripts/tv_execute_plan.py 'watchlist add symbol BTCUSDT' --dry-run
```

Key behaviors:

- requires explicit `--yes` to execute (otherwise returns a dry-run/plan-only result)
- enforces risk thresholds (`--max-risk`, optional `--allow-risk`)
- supports runner-specific verification hooks:
  - desktop (`tvctl.py`) defaults to pre/post `status`
  - web (`tv_web_inventory.py`) verifies by capturing a post-action inventory snapshot and evaluating recipe assertions

Useful web flow intents (planner/executor can route these to curated multi-step web recipes):

- `open indicators`
- `search indicators RSI`
- `open create alert`
- `open layout manager`
- `open chart settings`
- `open quick search`

### Enumerate TradingView Web Controls (Playwright)

```bash
python3 scripts/tv_web_inventory.py \
  --url https://www.tradingview.com/chart/ \
  --headed \
  --write-default-output
```

Optional interaction plan (example file in `references/examples/web-inventory-actions.example.json`) lets you open contexts before the final capture.

For richer context coverage, use the curated plans in:

- `references/examples/web-inventory-plans/`
- `references/examples/web-inventory-plan-manifest.json`

These rely on label-based snapshot actions (`snapshot-click-label`, `snapshot-click-one-of`) so they do not require hardcoded Playwright `e#` refs.

### Change Symbol (generic)

```json
[
  { "action": "activate", "launch": true },
  { "action": "wait", "seconds": 0.4 },
  { "action": "hotkey", "combo": "cmd+k" },
  { "action": "wait", "seconds": 0.2 },
  { "action": "type", "text": "AAPL" },
  { "action": "press", "key": "return" }
]
```

If your symbol search shortcut differs, inspect menus and replace the `hotkey` step.

### Change Symbol (high-level action)

```json
[
  { "action": "set-symbol", "symbol": "AAPL", "launch": true }
]
```

### Add Indicator (high-level action)

```json
[
  { "action": "activate" },
  { "action": "add-indicator", "query": "RSI", "open_combo": "/" }
]
```

If `/` does not open indicators on your setup, override `open_combo` with your shortcut.

### Watchlist Search / Open (normalized window coordinates)

Calibrate a point over the watchlist input first, then use:

```json
[
  {
    "action": "watchlist-open",
    "symbol": "BTCUSDT",
    "x": 0.90,
    "y": 0.10,
    "normalized_window": true
  }
]
```

### Config-Backed Watchlist Macros (recommended after calibration)

```bash
python3 scripts/tvctl.py config-init config/layouts/main.json --layout-name main
python3 scripts/tvctl.py calibrate-watchlist config/layouts/main.json --delay-per-point 8
python3 scripts/tvctl.py watchlist-open-config config/layouts/main.json BTCUSDT
python3 scripts/tvctl.py watchlist-add-config config/layouts/main.json SOLUSDT
python3 scripts/tvctl.py watchlist-reorder-config config/layouts/main.json
python3 scripts/tvctl.py watchlist-remove-config config/layouts/main.json
```

The timed calibration captures:

- `watchlist_search_field`
- `watchlist_add_button`
- `watchlist_row_1`, `watchlist_row_2`, `watchlist_row_3`
- `watchlist_context_remove_item` (right-click a row first, then hover Remove)

### Watchlist Reorder (drag)

```json
[
  { "action": "activate" },
  {
    "action": "drag",
    "x1": 0.92,
    "y1": 0.28,
    "x2": 0.92,
    "y2": 0.40,
    "normalized_window": true,
    "duration": 0.25
  }
]
```

### Save Layout Through Menu

```json
[
  { "action": "activate" },
  { "action": "click-menu", "path": "View > Layout" }
]
```

Nested menu paths are supported as `Top > Item > Subitem`.

## Recovery Tactics

- Send `press esc` one or more times to close popovers.
- Re-run `activate` if another app steals focus.
- Recalibrate coordinates after major layout/sidebar changes.
- Stop on unexpected dialogs; do not blindly continue sequence playback.
