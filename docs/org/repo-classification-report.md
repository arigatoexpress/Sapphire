# Sapphire Repo Classification Report

The machine-readable report is `infra/org-classification-report.yaml`. It
tracks Core+Satellites only; older experiments stay inventory-only unless they
overlap Sapphire autonomy.

## Active Set (as of 2026-05-12)

- `core`: `sapphire`, `project-go-forward`
- `satellite`: `cyber-threat-bot`, `regional-intel-workbench`, `tradingview-mcp-v2`, `crypto-tax-tracker`
- `integration`: `agentic-arigato`

## Archived 2026-05-12

The following repos were moved to `_Archive_2026-05-12/repo-quarantine-2026-05-12/`:
- **Satellites (formerly active):** `claw-code`, `tradingview-mcp` (original fork), `Cointracker`
- **Integrations:** `hermes-agent`, `kimi-tools`
- **Upstream fleet:** `openclaw`, `NemoClaw`, `lumo-api`, `foundry-platform-python`,
  `palantir-python-sdk`, `fredapi`, `lightweight-charts`, `goose`, `career-ops-plugin`,
  `aip-community-registry`

Active TradingView lane is `tradingview-mcp-v2` (`~/Code/tradingview-mcp-v2`).
Sapphire PM bot owns Telegram ingress (replaces hermes-agent gateway).
Agent dispatch is now internal to Sapphire (replaces claw-code runtime).

## Upstream Integration Fleet

`infra/org-repos.yaml` tracks an `upstream_repos` section for starred or locally
integrated upstreams. After the 2026-05-12 cleanup, the active upstream fleet is:
OpenBB, Kronos, tradingview-mcp-upstream (hardening PR), and RTK.

The rule is deliberately conservative: forks and clones are inventory/control
assets, not runtime cutovers. Retargeting Sapphire, LaunchAgents, or any Cloud Run
service to an Ari fork still needs a dedicated PR, tests, blast-radius notes, and rollback.

`agentic-arigato` owns the protected `agentic-pm-hub` Cloud Run service in
`tho-ai-agent`. The service should remain private; public unauthenticated probes
are expected to classify as `cloud_run_auth_required`, while health verification
uses authenticated requests. Guardrail parity shipped in
[arigatoexpress/AgenticArigato#1](https://github.com/arigatoexpress/AgenticArigato/pull/1);
the authenticated health runbook shipped in
[arigatoexpress/AgenticArigato#2](https://github.com/arigatoexpress/AgenticArigato/pull/2).

## Absorb Candidates

None open — `kimi-tools` absorb completed via the 2026-05-12 workspace cleanup.

## Immediate Follow-Ups

- Keep watching the TradingView MCP v2 upstream guardrail PR (tradesdontlie/tradingview-mcp#102).

## Safety

This report does not delete, archive, unload, or retarget anything. Every
absorb/archive action still requires a dedicated PR, focused tests, rollback
notes, and explicit cutover evidence.
