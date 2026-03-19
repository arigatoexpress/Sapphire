# Layout Config (Per-Layout Points + Shortcuts)

Use a JSON config file per TradingView layout/window arrangement so the agent can run watchlist actions without re-entering coordinates.

Recommended location:

- `config/layouts/<name>.json`

Create it:

```bash
python3 scripts/tvctl.py config-init config/layouts/main.json --layout-name main
```

## What It Stores

- `shortcuts`: symbolic shortcut names (for example `symbol_search`, `indicator_search`)
- `watchlist`: named point bindings and watchlist macro defaults
- `points`: named coordinate points (usually `normalized_window`)

## Point Coordinate Modes

- `absolute`: screen coordinates
- `relative_window`: offset from the front TradingView window origin
- `normalized_window` (recommended): `0..1` fractions of front window width/height

`normalized_window` survives window moves and many resizes, so it is best for watchlist targets.

## One-Pass Timed Calibration (No Manual JSON Editing)

This command waits a fixed number of seconds before each capture. During each countdown, move the mouse to the target point.

```bash
python3 scripts/tvctl.py calibrate-watchlist config/layouts/main.json --delay-per-point 8
```

Capture order:

1. Watchlist search/input field
2. Watchlist add (`+`) button
3. Watchlist row 1 anchor
4. Watchlist row 2 anchor
5. Watchlist row 3 anchor
6. Context menu `Remove` item (right-click a row first, then hover `Remove`)

## Manual Point Capture (for refinements)

Capture a single point with a delay:

```bash
python3 scripts/tvctl.py config-capture-point config/layouts/main.json watchlist_row_2 --delay 5
```

Set a point manually:

```bash
python3 scripts/tvctl.py config-set-point config/layouts/main.json watchlist_row_2 0.91 0.24 --coord-mode normalized_window
```

## Config-Backed Watchlist Macros

```bash
python3 scripts/tvctl.py watchlist-open-config config/layouts/main.json BTCUSDT
python3 scripts/tvctl.py watchlist-add-config config/layouts/main.json SOLUSDT
python3 scripts/tvctl.py watchlist-remove-config config/layouts/main.json
python3 scripts/tvctl.py watchlist-reorder-config config/layouts/main.json --from-point-name watchlist_row_1 --to-point-name watchlist_row_3
```

## Caveats

- `watchlist-remove-config` depends on a stable `watchlist_context_remove_item` point. Recalibrate if TradingView updates the context menu layout.
- If your shortcuts differ from defaults, store overrides with `config-set-shortcut`.
