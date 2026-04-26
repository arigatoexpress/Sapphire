# Sapphire Repo Classification Report

The machine-readable report is `infra/org-classification-report.yaml`. It
tracks Core+Satellites only; older experiments stay inventory-only unless they
overlap Sapphire autonomy.

## Active Set

- `core`: `sapphire`, `project-go-forward`
- `satellite`: `claw-code`, `cyber-threat-bot`,
  `regional-intel-workbench`, `tradingview-mcp`, `crypto-tax-tracker`
- `integration`: `tradingview-mcp-v2`, `hermes-agent`, `kimi-tools`

## Absorb Candidates

- `kimi-tools` -> `sapphire`: proposed. The local-only Kimi HTTP utilities
  overlap Sapphire/Hermes agent tooling and should not stay as a separate
  maintenance surface if call sites can be moved safely.
- `tradingview-mcp-v2` -> `tradingview-mcp`: conditional. Upstream hardening is
  open in PR #102, but Ari cannot merge upstream. If it stalls or becomes
  production-critical, consolidate required behavior into the Ari-owned bridge
  or pin the Ari fork.

## Archive Candidates

No Core+Satellites repo is approved for archive. `kimi-tools` is review-only for
archive after an absorb PR, tests, rollback notes, and a soak window.

## Immediate Follow-Ups

- Audit `crypto-tax-tracker` for CI, pre-commit parity, and README test command
  accuracy.
- Map `hermes-agent` local relay/filter changes and choose fork, patch, or
  absorb strategy.
- Find all `kimi-tools` callers before any absorb work.

## Safety

This report does not delete, archive, unload, or retarget anything. Every
absorb/archive action still requires a dedicated PR, focused tests, rollback
notes, and explicit cutover evidence.
