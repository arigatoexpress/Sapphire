# Executor Workflow (Plan -> Execution)

Use `scripts/tv_execute_plan.py` to execute a planner-selected TradingView recipe with explicit confirmation, risk gates, and verification hooks.

## Basic Usage

```bash
python3 scripts/tv_execute_plan.py 'open settings' --prefer-surface-family web_ui --yes
```

## What It Does

- builds a plan from intent (or loads a saved plan JSON)
- blocks non-ready plans (`needs_input`, `blocked_risk`, etc.)
- enforces execution risk threshold
- requires `--yes` to execute (otherwise dry-run/plan-only)
- runs the selected recipe:
  - `tvctl.py` (desktop UI automation)
  - `tv_web_inventory.py` (web action + post-action capture verification + recipe assertions)
- applies per-recipe execution policy defaults from the registry (`timeouts`, `retry_policy`) when present
- retries transient web capture/execution failures with bounded backoff before failing
- resets to a fresh Playwright session on retry for session/socket-level failures (for example `target closed`, `browser ... is not open`) and recaptures web baselines when needed
- stores per-attempt debug artifacts for failed web retries under `output/executor-debug/` (metadata + captured inventory JSON + copied snapshot YAMLs when available)

## Useful Flags

- `--plan-file <file.json>` execute a saved `tv_plan_intent.py --json` result
- `--dry-run` force plan-only mode
- `--max-risk low|medium|high` planning + execution threshold
- `--allow-risk low|medium|high` execution-only threshold override
- `--prefer-surface-family web_ui|desktop_ui` bias planner to a surface
- `--pre-hook/--post-hook status|window-bounds|mouse-location|list-menus|window-titles`
- `--no-auto-hooks` disable default runner hooks (desktop defaults to pre/post `status`)
- `--web-headed` run web recipes in headed Playwright mode
- `--debug-artifacts off|on-failure|always` control persistence of web retry/debug artifacts (default `on-failure`)
- `--command-timeout-seconds <n>` override timeout for `tvctl.py` recipe runs (`<=0` disables timeout; otherwise recipe/default policy applies)
- `--web-exec-timeout-seconds <n>` override timeout for web recipe execution capture (`<=0` disables timeout; otherwise recipe/default policy applies)
- `--web-baseline-timeout-seconds <n>` override timeout for baseline capture used by delta assertions (`<=0` disables timeout; otherwise recipe/default policy applies)
- `--json` machine-readable execution result

## Status Values

- `dry_run`
- `executed`
- `execution_failed`
- `verification_failed`
- `execution_error`
  - may include partial `execution` diagnostics (for example baseline retry/session history) when failure occurs before the main action capture completes
- `blocked_risk`
- `missing_parameters`
- `needs_input` (from planner)

## Examples

```bash
python3 scripts/tv_execute_plan.py 'open indicators' --prefer-surface-family web_ui --yes
python3 scripts/tv_execute_plan.py 'search indicators RSI' --prefer-surface-family web_ui --yes
python3 scripts/tv_execute_plan.py 'open create alert' --prefer-surface-family web_ui --dry-run
python3 scripts/tv_execute_plan.py 'open layout manager' --prefer-surface-family web_ui --dry-run
python3 scripts/tv_execute_plan.py 'add indicator "RSI"' --yes
python3 scripts/tv_execute_plan.py 'watchlist add symbol BTCUSDT' --dry-run
python3 scripts/tv_execute_plan.py 'remove watchlist row' --max-risk low --yes
python3 scripts/tv_execute_plan.py 'open indicators' --prefer-surface-family web_ui --yes --web-exec-timeout-seconds 60 --web-baseline-timeout-seconds 30
python3 scripts/tv_execute_plan.py 'open indicators' --prefer-surface-family web_ui --yes --debug-artifacts always
```

## Debug Artifact Cleanup

Use the cleanup utility to prune old debug runs by age and/or total size:

```bash
python3 scripts/tv_executor_debug_cleanup.py --dry-run --json
python3 scripts/tv_executor_debug_cleanup.py --apply --max-age-days 3 --max-total-mb 256 --keep-last 10
```

## Web Recipe Assertions (Declarative Verification)

For web recipes, `tv_execute_plan.py` evaluates `recipe.verification.assertions` against the post-action inventory capture and fails with `verification_failed` when assertions do not pass.

Supported assertion kinds:

- `plan_action_executed`
- `capture_label_equals`
- `page_title_contains`
- `page_href_contains`
- `snapshot_label_any` / `snapshot_label_all`
- `dom_label_any` / `dom_label_all`
- `capture_text_any` / `capture_text_all`
