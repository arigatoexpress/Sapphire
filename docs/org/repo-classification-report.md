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

`agentic-arigato` owns the protected `agentic-pm-hub` Cloud Run service in
`tho-ai-agent`. The service should remain private; public unauthenticated probes
are expected to classify as `cloud_run_auth_required`, while health verification
uses authenticated requests.

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

- Add CI/pre-commit parity to `agentic-arigato` before any deploy or IAM change.
- Keep watching the TradingView MCP v2 upstream guardrail PR.
- Audit Hermes Sapphire skill command surfaces before moving or deleting any
  agent-facing skill.
- Keep the standalone `kimi-tools` workbench read-only during soak; archive
  only through a later dedicated cleanup PR/report.

## Safety

This report does not delete, archive, unload, or retarget anything. Every
absorb/archive action still requires a dedicated PR, focused tests, rollback
notes, and explicit cutover evidence.
