# Scout Sandbox: Scrapling + GTM Integration

This document defines the new sandbox-only integration layer for:

- `scrapling` web intelligence collection
- `gtm` outbound dispatch bridge

All behavior is feature-flagged and allowlist-gated.

## Endpoints

### 1) Scrapling Intel Collector

- Route: `POST /v1/intel/scrapling_collect`
- Auth: `X-Scout-Sandbox-Token` or `Authorization: Bearer <token>`

Request body:

```json
{
  "source_url": "https://news.ycombinator.com/",
  "selectors": ["title", "a.storylink", "h1", "h2"],
  "limit_per_selector": 5,
  "include_links": true,
  "max_links": 15,
  "query": "trading"
}
```

Response highlights:

- `ok`, `reason`, `status`
- `items[]` normalized intel rows
- `selector_hits` extraction counts
- `snippet` page text excerpt
- `links[]` optional extracted links

### 2) GTM Outbound Bridge

- Route: `POST /v1/gtm/outbound`
- Auth: `X-Scout-Sandbox-Token` or `Authorization: Bearer <token>`

Request body:

```json
{
  "outbound_payload": {
    "company_url": "https://example.com",
    "campaign": "alpha-launch",
    "message": "Sapphire scout outbound draft"
  },
  "external_url_hint": "https://app.clawgtm.com/api/v1/agents/dispatch",
  "note": "sandbox gtm dispatch",
  "source": "alpha-engine",
  "request_id": "gtm-demo-001"
}
```

This endpoint maps to dispatch action `gtm_outbound` internally and uses GTM-specific allowlists/token policy.

## Environment Variables

### Scrapling

- `SCOUT_SANDBOX_SCRAPLING_ENABLED` (`false` default)
- `SCOUT_SANDBOX_SCRAPLING_ALLOWED_HOSTS` (CSV)
- `SCOUT_SANDBOX_SCRAPLING_TIMEOUT_SECONDS` (`20` default)
- `SCOUT_SANDBOX_SCRAPLING_VERIFY_TLS` (`true` default)

### GTM

- `SCOUT_SANDBOX_GTM_ENABLED` (`false` default)
- `SCOUT_SANDBOX_GTM_OUTBOUND_URL` (optional default target)
- `SCOUT_SANDBOX_GTM_API_TOKEN` (secret)
- `SCOUT_SANDBOX_GTM_REQUIRE_TOKEN` (`true` default)
- `SCOUT_SANDBOX_GTM_ALLOWED_HOSTS` (CSV)
- `SCOUT_SANDBOX_GTM_ALLOWED_PATH_PATTERNS` (semicolon-separated regex list)

### Deploy Script Support

`/Users/aribs/Sapphire/scripts/deploy_scout_sandbox.sh` now supports all variables above and optional secret mapping:

- `SCOUT_SANDBOX_GTM_API_TOKEN_SECRET` (`SCOUT_SANDBOX_GTM_API_TOKEN` default)

## Safety Model

- Only `https` URLs are accepted.
- URL hosts are checked against explicit allowlists.
- URL paths are checked against explicit regex allowlists (for dispatch/GTM).
- Inbound token auth is required when `SCOUT_SANDBOX_TOKEN` is configured.
- All outbound/intel actions are audited into `scout_sandbox_audit`.

## Quick Validation

Health:

```bash
curl -sS "${SCOUT_URL}/health" | jq
```

Scrapling dry check:

```bash
curl -sS -X POST "${SCOUT_URL}/v1/intel/scrapling_collect" \
  -H "X-Scout-Sandbox-Token: ${SCOUT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://news.ycombinator.com/","selectors":["title","a"],"include_links":true}'
```

GTM dry check:

```bash
curl -sS -X POST "${SCOUT_URL}/v1/gtm/outbound" \
  -H "X-Scout-Sandbox-Token: ${SCOUT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"outbound_payload":{"company_url":"https://example.com"},"external_url_hint":"https://app.clawgtm.com/api/v1/agents/dispatch"}'
```
