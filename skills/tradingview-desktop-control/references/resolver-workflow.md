# Resolver Workflow (Intent -> Capability Candidate)

Use `scripts/tv_resolve_capability.py` after generating a merged registry to map intent text to likely TradingView actions.

## Basic Usage

```bash
python3 scripts/tv_resolve_capability.py "open indicators" \
  --registry output/capability-registry.merged.latest.json
```

## Useful Flags

- `--top N` limit results (default `10`)
- `--only-actionable` prefer capabilities that include an `action_recipe`
- `--prefer-surface-family web_ui|desktop_ui` bias ranking to a UI surface
- `--json` machine-readable output

Examples:

```bash
python3 scripts/tv_resolve_capability.py "settings" --prefer-surface-family web_ui
python3 scripts/tv_resolve_capability.py "watchlist remove row" --only-actionable
python3 scripts/tv_resolve_capability.py "symbol search" --json
```

## How It Scores (High Level)

- exact canonical label/alias match (highest weight)
- substring match in label/cluster key
- token overlap (label, tags, metadata)
- actionability bonus (`action_recipe` present)
- repeated observation bonus (same capability seen across multiple web captures)
- small risk penalty unless the query itself appears to request a risky action

## Recommended Loop

1. Generate desktop seed (`tv_inventory.py`)
2. Capture one or more web contexts (`tv_web_inventory.py`)
3. Merge (`tv_registry_merge.py`)
4. Resolve a user intent (`tv_resolve_capability.py`)
5. Convert the intent into an executable recipe (`tv_plan_intent.py`)
6. Execute the chosen recipe with explicit verification + safety checks
