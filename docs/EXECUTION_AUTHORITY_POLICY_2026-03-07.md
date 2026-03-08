# Execution Authority Policy (2026-03-07)

## Purpose
Eliminate split-brain between deployed services and actual trade execution by defining a single authoritative execution plane.

## Authoritative Planes
- **Authoritative execution plane:** edge runtime on `rari2` (`lighter-trading` and approved companion workers).
- **Cloud control/data plane:** gateway, unified frontend/jobs, alpha, PM hub, scout sandbox.
- **Public plane:** `https://sapphirealpha.xyz` read-only contracts only.

## Cloud Venue Service Posture
- `sapphire-lighter`: **standby_cloud**
- `sapphire-aster`: **standby_cloud**

Standby requirements:
1. `TRADING_ENABLED=false`
2. `ALLOW_LIVE_TRADING=0` where applicable
3. Cloud Run labels indicate standby role and edge execution authority
4. Runbooks and status summaries must explicitly call out standby posture

## Operator Rule
- All live trade execution debugging starts on `rari2` first.
- Cloud venue services are not treated as first-line execution roots unless explicitly promoted out of standby mode.

## Promotion Out of Standby (controlled)
Allowed only when all are true:
1. Edge execution unavailable or intentionally decommissioned.
2. Risk gate + fill-rate gate are green in last 24h.
3. Explicit change log entry and rollback command are prepared.
4. Production check passes after rollout.

## Rollback
- Return affected cloud venue service to:
  - `TRADING_ENABLED=false`
  - `ALLOW_LIVE_TRADING=0`
  - standby labels intact
