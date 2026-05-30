# Sapphire — Agent Charter

Read this first before editing code, docs, or configuration.

## What this repo does

Sapphire is the command repo for Ari's autonomous system. It orchestrates trading, intelligence, content, and security ops through a shared event bus on a Tailscale mesh. Treat it as a live collection of composable runtime surfaces, not a fixed product brief.

## Key directories and files

| Path | Purpose |
|---|---|
| `lib/core/` | Risk kernel, event bus, kill switch, confirmation firewall |
| `lib/analytics/` | Strategies, backtests, regimes, forecasts |
| `lib/chain/` | On-chain intel (Glassnode, Santiment, Dune, etc.) |
| `lib/content/` | 17-module research-to-publish pipeline |
| `lib/security/` | SBOM, model verification, network mapper |
| `services/` | 16 services (alpha, dashboard, control-plane, inference-proxy, etc.) |
| `plugins/claw-sapphire/` | 72 registered tools for the agent runtime |
| `infra/tool-registry.yaml` | Required registry for every tool |
| `contracts/` | 3 Solidity contracts |
| `pine/` | 5 Pine strategies |
| `docs/` | Architecture, audit, and planning docs |

## How to run tests / dev server

```bash
# Fast test pass
pytest plugins/claw-sapphire/tests/ -q

# Full unit test suite
/usr/local/bin/python3 -m pytest tests/unit/ --tb=short -q

# Lint touched files only
ruff check <files>

# Tool registry invariant
python scripts/validate_tool_registry.py

# Start dashboard locally
(cd services/dashboard && python3 app.py)   # :8080

# Start inference proxy
python3 services/inference-proxy/app.py     # :11435
```

## Safety boundaries — what NOT to touch

- **Never** delete GCP projects, Firestore collections, or force-push to `main`.
- **Never** commit `data/paper_trading.jsonl`, `data/signals/`, `data/enrich/*`, or any `~/.config/sapphire-secrets/*` file.
- **Never** embed secrets inline — use env vars or `~/.config/sapphire-secrets/` files.
- **Never** change inference-proxy tier routing without running the mesh benchmark first.
- **Never** run `launchctl bootout` on a service other sibling services depend on.
- **Never** move real money, expose secrets, or send live Telegram messages without explicit human approval.
- Do not `launchctl load/unload` from agent scripts — ship the plist and tell the human to load it.

## Branching and PRs

- Branch off `origin/main`, not local `main`:
  ```bash
  git fetch origin && git switch -c feat/<name> origin/main
  ```
- Open ready-to-merge PRs once local verification passes.
- Codex may merge its own green, reversible, non-draft PRs without waiting for human review.
- Human approval is required for real money movement, live execution, secret exposure, destructive infra changes, or workflow/branch-protection disabling.

## Current status

- Mac services run as LaunchAgents (`~/Library/LaunchAgents/com.sapphire.*.plist`).
- `sapphirealpha.xyz` is served from Cloud Run; do not delete the hosting GCP project.
- Firestore `(default)` in `tho-ai-agent` has delete protection enabled.
- Windows inference path is deprecated for new agentic work.
