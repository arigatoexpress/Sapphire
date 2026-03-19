# Web Inventory Workflow (TradingView Web + Playwright CLI)

Use `scripts/tv_web_inventory.py` to enumerate TradingView Web controls/capabilities from the live page using:

- Playwright snapshot refs (`snapshot_refs`)
- DOM control extraction (`dom_controls`)
- Data-attribute extraction (`data_attribute_nodes`)

The output now also includes:

- executable web `action_recipe`s for many interactive controls (buttons/tabs/menuitems)
- curated multi-step flow capabilities (for example indicators dialog open/search, alerts, layout manager, chart settings, quick search)

## Basic Capture

```bash
python3 scripts/tv_web_inventory.py \
  --url https://www.tradingview.com/chart/ \
  --headed \
  --capture-label chart-default \
  --output output/tv-web-inventory.chart-default.json
```

## Action Plans (Open a Context First)

Pass an `--actions-file` JSON plan to open a dialog/menu before the final capture.

```bash
python3 scripts/tv_web_inventory.py \
  --url https://www.tradingview.com/chart/ \
  --actions-file references/examples/web-inventory-plans/open-indicators-dialog.json \
  --capture-label indicators-dialog \
  --output output/tv-web-inventory.indicators.json
```

## Plan Action Syntax

Supported actions:

- `wait` — sleep for `seconds`
- `press` — send a keyboard key via Playwright CLI `press`
- `click` — click an explicit snapshot ref (`ref`)
- `type` — type text
- `open` — open URL (optional `headed`)
- `snapshot` — capture and record snapshot metadata
- `eval` — run an eval expression and store parsed JSON/string result
- `snapshot-click-label` — take a fresh snapshot, find a matching ref by label text, click it
- `snapshot-click-one-of` — same, but tries multiple labels in order

### `snapshot-click-label` fields

```json
{
  "action": "snapshot-click-label",
  "label": "Settings",
  "role": "button",
  "match": "contains",
  "wait_after": 1.0
}
```

Fields:

- `label` (required)
- `role` (optional; filters snapshot ref role)
- `match` (optional): `contains` (default), `exact`, `startswith`, `regex`
- `case_sensitive` (optional boolean)
- `wait_after` (optional seconds)

### `snapshot-click-one-of` example

```json
{
  "action": "snapshot-click-one-of",
  "labels": ["Indicators, metrics, and strategies", "Indicators"],
  "role": "button",
  "match": "contains",
  "wait_after": 1.0
}
```

## Curated Context Plans

See `references/examples/web-inventory-plan-manifest.json` for a list of curated contexts and plan files, including:

- symbol search / compare
- indicators dialog
- create alert dialog
- layout setup menu
- settings dialog
- quick search
- bar replay

## Curated Flow Capabilities (Generated in Inventory Output)

When the corresponding controls are visible, `tv_web_inventory.py` emits additional curated flow capabilities such as:

- `Open indicators dialog (web)`
- `Search indicators dialog (web)` (parameterized `query`)
- `Add indicator via web search (heuristic)` (parameterized `query`)
- `Open create alert dialog (web)`
- `Open layout manager (web)`
- `Open chart settings (web)`
- `Open quick search (web)`

These are stored as regular capability candidates with `source=playwright-curated` and executable `action_recipe`s.

## Recipe Verification Assertions

Web `action_recipe`s may include declarative post-capture assertions in `verification.assertions`, for example:

- `plan_action_executed`
- `capture_label_equals`
- `snapshot_label_any` / `snapshot_label_all`
- `dom_label_any` / `dom_label_all`
- `capture_text_any` / `capture_text_all` (combined snapshot+DOM text matching)

`tv_execute_plan.py` evaluates these assertions after the web action runs and returns `verification_failed` if they do not pass.

## Recommended Capture Set (First Pass)

1. `chart-default`
2. `indicators-dialog`
3. `create-alert-dialog`
4. `layout-setup-menu`
5. `settings-dialog`
6. `quick-search`

Then merge with desktop inventory:

```bash
python3 scripts/tv_registry_merge.py \
  references/examples/capability-registry.seed.json \
  output/tv-web-inventory.chart-default.json \
  output/tv-web-inventory.indicators.json \
  output/tv-web-inventory.alerts.json \
  --output output/capability-registry.merged.json
```
