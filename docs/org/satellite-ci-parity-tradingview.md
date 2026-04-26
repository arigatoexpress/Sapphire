# TradingView MCP v2 CI Parity Status

`tradingview-mcp-v2` is an upstream integration for the Sapphire autonomous org.
It controls a local TradingView Desktop chart through CDP, so its automated
guardrails must stay offline by default and must not launch, mutate, or trade
through TradingView during CI.

## Current State

- Local path: `/Users/aribs/Code/tradingview-mcp-v2`
- Upstream repository: `tradesdontlie/tradingview-mcp`
- Ari fork: `arigatoexpress/tradingview-mcp-upstream`
- Upstream permission: read-only
- Ari fork permission: admin
- Tracking branch: `chore/ci-agent-guardrails`
- Upstream PR: [tradesdontlie/tradingview-mcp#102](https://github.com/tradesdontlie/tradingview-mcp/pull/102)

## What PR #102 Adds

- `AGENTS.md` with repo safety rules and PR expectations.
- `.github/workflows/ci.yml` with read-only permissions and Node 20/22 offline
  checks.
- `.pre-commit-config.yaml` with JSON/YAML hygiene, whitespace checks, syntax
  checks, and offline tests.
- `npm run check:syntax` for JavaScript syntax validation.
- `npm run test:offline` that skips CDP/server compile checks and runs
  deterministic static-analysis and sanitization tests.

## Local Validation

Validated on 2026-04-26 from `/Users/aribs/Code/tradingview-mcp-v2` on branch
`chore/ci-agent-guardrails`:

```bash
npm run check:syntax
npm run test:offline
```

Result:

- Syntax check passed.
- Offline tests passed: 79 passed, 0 failed.
- CDP-dependent Pine compile tests were skipped through `SKIP_NETWORK_TESTS=1`.

## Blocker

The true upstream repository is read-only for Ari. The hardening work is open as
an upstream PR, but merging requires upstream maintainer action. Until that
merges, Sapphire should treat this integration as `upstream_pr_open`, not fully
hardened.

## Operating Decision

- Do not duplicate PR #102 in another branch.
- Keep Sapphire pointed at the upstream integration for awareness, but record
  the Ari fork as the controlled fallback if upstream stalls.
- If upstream does not merge, choose between pinning Sapphire to the Ari fork or
  absorbing the required bridge behavior into an Ari-owned repo.

## Blast Radius

This report and the manifest update are documentation/control-tower changes
only. They do not modify TradingView, CDP sessions, local LaunchAgents, package
dependencies, or production Sapphire runtime behavior.
