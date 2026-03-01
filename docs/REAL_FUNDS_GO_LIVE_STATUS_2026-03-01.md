# Real-Funds Go-Live Status (2026-03-01)

## Scope
- Project: `sapphire-479610`
- Canonical frontend: `https://sapphirealpha.xyz`
- Canonical repo: `/Users/aribs/Sapphire`

## What was verified
- Production contracts and pages:
  - `/Users/aribs/Sapphire/scripts/run_production_check.sh`
  - Contracts: `13/13` returning HTTP `200`
  - Frontend routes: all expected routes returning HTTP `200`
- Readiness gates:
  - `A_contracts: 13/13`
  - `B_cloud: 6/6`
  - `C_edge: 2/2`
  - `D_signal_ingress: 2/2`
  - `overall_ok: true`, `blockers: 0`
- Cross-environment monitor:
  - `18/18 healthy`
- Gateway security behavior:
  - Invalid webhook secret rejected with `401`
  - Valid webhook secret accepted with `200` and Pub/Sub message id
- IAM ownership/editor drift:
  - Owner/editor scan shows only one owner binding and no editor bindings.

## Current live-trading posture
- `TRADINGVIEW_EXECUTION_ENABLED=false` on `sapphire-alpha`
- `SAPPHIRE_DEX_EXECUTION_STAGE=full_live`
- `SAPPHIRE_AUTONOMY_REQUIRE_OWNER_APPROVAL=false`
- `SAPPHIRE_AUTONOMY_DRY_RUN=false`

## Blocking items for safe real-funds start
1. Secret readiness script still reports missing trading/control secrets in Secret Manager:
   - `ASTER_API_KEY`, `ASTER_SECRET_KEY`
   - `LIGHTER_API_KEY_0`, `LIGHTER_API_PUBLIC_KEY_0`
   - plus control-plane optional gaps (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENCLAW_GATEWAY_TOKEN`, etc.)
2. Windows TV agent currently reports disconnected state (`tradingview.connected=false` and `sapphire.connected=false`) even though service health endpoint is up.
3. Safety policy mismatch:
   - execution stage is `full_live` while owner approval is disabled.
   - this should be tightened before funds are exposed.

## Required go-live sequence (recommended)
1. Provision missing venue secrets into GCP Secret Manager and bind them to runtime.
2. Set safety gate to staged mode first:
   - `SAPPHIRE_DEX_EXECUTION_STAGE=staged_live`
   - `SAPPHIRE_AUTONOMY_REQUIRE_OWNER_APPROVAL=true`
3. Enable signal execution only after staged validation:
   - set `TRADINGVIEW_EXECUTION_ENABLED=true`.
4. Run controlled canary with strict notional cap and kill-switch verification.
5. Promote to `full_live` only if canary passes.

## Conclusion
Platform health is strong, but real-funds go-live is **not yet safe to execute immediately** due missing key material in canonical secret checks and safety-policy mismatch. Continue in paper/staged mode until above gates are closed.
