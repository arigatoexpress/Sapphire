# Planner Workflow (Intent -> Executable Recipe)

Use `scripts/tv_plan_intent.py` after building a merged registry to choose a runnable TradingView action recipe (usually a `tvctl.py` command) from natural-language intent.

## Basic Usage

```bash
python3 scripts/tv_plan_intent.py 'set chart symbol AAPL' \
  --registry output/capability-registry.merged.latest.json
```

## What It Adds Beyond `tv_resolve_capability.py`

- runs a resolver pass for descriptive matches and a separate pass for actionable matches
- prefers executable capabilities when planning (not just descriptive UI labels)
- infers common parameters from intent (`symbol`, `query`)
- applies risk gating with `--max-risk`
- emits a command preview for supported runners (`tvctl.py`, `tv_web_inventory.py`)

## Useful Flags

- `--search-top N` increase candidate search depth (default `20`)
- `--prefer-surface-family web_ui|desktop_ui` bias resolution toward a UI surface
- `--max-risk low|medium|high` block recipes above the allowed risk
- `--json` machine-readable output for agent loops

## Status Values

- `ready`: executable recipe selected and all required parameters are filled
- `needs_input`: executable recipe selected but one or more parameters are missing
- `blocked_risk`: a strong actionable match exists but exceeds `--max-risk`
- `no_actionable_match`: only descriptive/non-executable matches were found

## Examples

```bash
python3 scripts/tv_plan_intent.py 'add indicator "RSI"'
python3 scripts/tv_plan_intent.py 'open indicators'
python3 scripts/tv_plan_intent.py 'watchlist add symbol BTCUSDT'
python3 scripts/tv_plan_intent.py 'remove watchlist row' --max-risk low
```

## Recommended Loop

1. Enumerate capabilities (`tv_inventory.py`, `tv_web_inventory.py`)
2. Merge inventories (`tv_registry_merge.py`)
3. Inspect matches (`tv_resolve_capability.py`) when tuning aliases/coverage
4. Plan executable action (`tv_plan_intent.py`)
5. Execute with explicit verification and risk checks (`tv_execute_plan.py`)
