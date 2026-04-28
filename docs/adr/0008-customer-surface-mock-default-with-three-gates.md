# ADR 0008 — Customer-facing surface is mock-default with three live gates

- **Status**: accepted
- **Date**: 2026-04-29 (Tranche 5 Lane 7)
- **Authors**: Sapphire ops
- **Related**: ADR 0003, ADR 0004, ADR 0005

## Context

Tranche 5 Lane 7 introduced a customer-facing API at
`services/customer_api/` that returns sample backtest summaries, sample
narratives, sample SEC filings — anything a B2B prospect might consume
to evaluate Sapphire as a vendor. This is genuinely new territory: until
Tranche 5, every Sapphire surface was internal-tooling-only.

Three risks emerged:

1. **Real-money exposure**: a customer-facing surface implies pricing
   tiers, which implies payment processing. A test that accidentally
   touches a live Stripe / x402 endpoint could charge a real card or
   leak the operator's payment credentials.
2. **Signal IP leak**: returning real backtest results, real
   correlations, or real narratives is exactly the alpha we don't
   want flowing to a public API uncontrolled.
3. **Reputational risk**: a malformed or misleading sample response to
   a corp-dev reviewer (Palantir, Robinhood) is worse than no response.

## Decision

The customer-facing surface follows a **mock-default with three gates**
pattern. The three gates are checked in order; only when all three
pass does the surface return real data.

### Gate 1 — Env flag

`SAPPHIRE_CUSTOMER_API_LIVE=1` is required to engage live mode. Default
is unset; the API returns sample fixtures with `mock=true` clearly
marked in every response body.

### Gate 2 — Payment infrastructure verification

`SAPPHIRE_PAYMENT_VERIFIED=1` is required as a second flag. This is set
only after the operator has confirmed that the payment infrastructure
(Stripe webhook, x402 contract, or whatever the active scheme is) is
wired with the right keys and the right rate limits. Setting Gate 1
without Gate 2 returns a structured `mock=true, reason="payment_not_verified"`
response — the API does not silently succeed.

### Gate 3 — Per-tenant allowlist

Live responses are gated to a per-tenant allowlist file at
`~/.sapphire/customer_api_allowlist.yaml`. Requests outside the
allowlist return `mock=true, reason="tenant_not_allowlisted"` even when
both env flags are set.

**Sample data fidelity**: mock responses use the same shape as live
responses. The `mock` field is the only distinguishing key. Sample
data is curated under `data/customer_api/samples/` and reviewed
by the operator.

**Provenance** (ADR 0005): every response — mock or live — carries an
envelope. The operator can chase any customer-facing artifact back to
its source.

## Consequences

- **Positive**:
  - Three independent gates means a single accidental env flag does
    not flip live mode. Operator must explicitly cross all three.
  - Sample-fidelity discipline means the surface is genuinely usable
    for buyer demos without real-money risk.
  - The `mock=true` field is honest — buyer reviewers can tell at a
    glance that they're seeing a sample.
- **Negative**:
  - Three gates is operationally heavy. Bringing live mode online
    requires three artifacts (env vars, allowlist file, payment
    verification confirmation).
  - Sample data drift is a real risk: if `data/customer_api/samples/`
    falls out of sync with the live response shape, demos look
    plausible but consumers integrating the API hit shape errors at
    cutover.
  - The allowlist file is plaintext YAML — not encrypted at rest. A
    leak of the allowlist would not breach paid customers but would
    surface internal demo-account names.
- **Neutral**:
  - The pattern is reusable: any future B2B surface (data feed,
    analytics export) can plug into the same three-gate harness.

## Alternatives Considered

- **Single-gate (env flag only)**: rejected — accidental env flag
  flip is a real risk in autonomous tranches.
- **No mock; live-mode-or-error**: rejected — buyer demos need a
  return value; "service unavailable" is the wrong UX for a sample.
- **Two-gate (env flag + allowlist) without payment-verified gate**:
  rejected — payment is the highest-risk surface and warrants a
  dedicated gate.
- **Authentication-as-the-gate (require API key)**: deferred —
  authentication is layered on top of the three gates, not a
  replacement. Live mode requires both an API key and the gates.

## References

- Implementation: `services/customer_api/`
- Mock fixtures: `data/customer_api/samples/` (when populated)
- Tranche 5 megaprompt constraint #13:
  `docs/handoffs/codex-megaprompt-tranche-5-compound-edge-2026-04-29.md`
- Runbook: `docs/ops/customer-api-runbook.md`
- Related: ADR 0003 (CODEOWNERS gate on critical paths)
