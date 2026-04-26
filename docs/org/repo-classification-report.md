# Sapphire Repo Classification Report

The machine-readable report is `infra/org-classification-report.yaml`. It
tracks Core+Satellites only; older experiments stay inventory-only unless they
overlap Sapphire autonomy.

## Active Set

- `core`: `sapphire`, `project-go-forward`
- `satellite`: `claw-code`, `cyber-threat-bot`,
  `regional-intel-workbench`, `tradingview-mcp`, `crypto-tax-tracker`
- `integration`: `agentic-arigato`, `tradingview-mcp-v2`, `hermes-agent`,
  `kimi-tools`

## Upstream Integration Fleet

`infra/org-repos.yaml` now includes a separate `upstream_repos` section for
starred or locally integrated upstreams that support Sapphire without being
first-class Core+Satellites. The initial fleet covers OpenBB, OpenClaw,
NemoClaw, Kronos, Lumo, Hermes, claw-code, TradingView MCP v2, Foundry/Palantir
SDKs, FRED, lightweight-charts, Goose, RTK, career-ops, and the AIP community
registry.

The rule is deliberately conservative: forks and clones are inventory/control
assets, not runtime cutovers. Retargeting Sapphire, Hermes, LaunchAgents, or any
Cloud Run service to an Ari fork still needs a dedicated PR, tests, blast-radius
notes, and rollback.

The AIP community registry is tracked as a Foundry/AIP reference clone. Its
local checkout disables Git LFS clean/smudge filters because upstream zip blobs
are committed as full objects while `.gitattributes` marks them as LFS. The
previous dirty LFS checkout is preserved in `_cleanup_backups`; the active clone
is clean for control-tower status.

`agentic-arigato` owns the protected `agentic-pm-hub` Cloud Run service in
`tho-ai-agent`. The service should remain private; public unauthenticated probes
are expected to classify as `cloud_run_auth_required`, while health verification
uses authenticated requests. Guardrail parity shipped in
[arigatoexpress/AgenticArigato#1](https://github.com/arigatoexpress/AgenticArigato/pull/1);
the authenticated health runbook shipped in
[arigatoexpress/AgenticArigato#2](https://github.com/arigatoexpress/AgenticArigato/pull/2).

## Absorb Candidates

- `kimi-tools` -> `sapphire`: absorb guardrails tested, no live callers found.
  The local-only Kimi HTTP utilities overlap Sapphire inference-proxy/router
  behavior; follow `docs/org/kimi-tools-absorb-map.md` before archive approval.
- `tradingview-mcp-v2` -> `tradingview-mcp`: conditional. Upstream hardening is
  open in PR #102, but Ari cannot merge upstream. If it stalls or becomes
  production-critical, consolidate required behavior into the Ari-owned bridge
  or pin the Ari fork.

## Archive Candidates

No Core+Satellites repo is approved for archive. `kimi-tools` is review-only for
archive after an absorb PR, tests, rollback notes, and a soak window.

## Immediate Follow-Ups

- Keep watching the TradingView MCP v2 upstream guardrail PR.
- Audit Hermes Sapphire skill command surfaces before moving or deleting any
  agent-facing skill.
- Keep the standalone `kimi-tools` workbench read-only during soak; archive
  only through a later dedicated cleanup PR/report.

## Safety

This report does not delete, archive, unload, or retarget anything. Every
absorb/archive action still requires a dedicated PR, focused tests, rollback
notes, and explicit cutover evidence.
