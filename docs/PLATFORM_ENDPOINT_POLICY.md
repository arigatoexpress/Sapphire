# Sapphire Platform Endpoint Policy

## Canonical API Surface
All new clients must use `GET /api/platform/*` contracts.

Current canonical contracts:
- `/api/platform/status`
- `/api/platform/metrics`
- `/api/platform/autonomy`
- `/api/platform/home-snapshot`
- `/api/platform/logs`
- `/api/platform/trades`
- `/api/platform/organization`
- `/api/platform/readiness`
- `/api/platform/projects`
- `/api/platform/intel-feed`
- `/api/platform/superswarm`
- `/api/platform/windows-lab`
- `/api/platform/contracts`

## Contract Manifest
Use `/api/platform/contracts` as source of truth for:
- Contract version
- Endpoint catalog
- Runtime auth mode
- Alias mapping and deprecation policy

## Headers
Canonical endpoints expose:
- `X-Sapphire-API-Tier: canonical`
- `X-Sapphire-Contract-Version: <version>`

All API responses expose:
- `Cache-Control: no-store, max-age=0`
- `Pragma: no-cache`

## Legacy Alias Policy
Legacy `/api/*` aliases remain for compatibility only.
They now return:
- `Deprecation: true`
- `Sunset: Sat, 01 Aug 2026 00:00:00 GMT` (default, configurable)
- `Link: <canonical-endpoint>; rel="successor-version"`
- `X-Sapphire-API-Tier: legacy-alias`

## Validation Commands
- Full production checks:
  - `./scripts/run_production_check.sh`
- Contract-only audit:
  - `./scripts/platform_contract_audit.sh`
