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

## Alpha Engine Wiring

### GTM outbound routing

`/Users/aribs/Sapphire/services/alpha-engine/src/collaboration/forum.py` now supports GTM outbound via normal scout publish flow:

- Set payload `channel=gtm` (or `dispatch_channel=gtm`) in `publish_scout_note`.
- Alpha dispatch action switches to `gtm_outbound`.
- When sandbox is configured, dispatch routes to `/v1/gtm/outbound`.

Optional alpha envs:

- `SAPPHIRE_SCOUT_GTM_OUTBOUND_URL` (fallback target URL)
- `SAPPHIRE_SCOUT_GTM_API_TOKEN` (fallback token; typically via secret)

### Scrapling intel routing

`/Users/aribs/Sapphire/services/alpha-engine/src/feeds/intel_feed.py` now has optional source `scrapling_web_intel`:

- Calls sandbox route `/v1/intel/scrapling_collect`
- Disabled by default
- Merges normalized rows into intel feed with source tags `scout_sandbox,scrapling`

Alpha env flags:

- `SAPPHIRE_SCRAPLING_INTEL_ENABLED`
- `SAPPHIRE_SCRAPLING_INTEL_SOURCE_URL`
- `SAPPHIRE_SCRAPLING_INTEL_SELECTORS` (semicolon-separated)
- `SAPPHIRE_SCRAPLING_INTEL_LIMIT_PER_SELECTOR`
- `SAPPHIRE_SCRAPLING_INTEL_INCLUDE_LINKS`
- `SAPPHIRE_SCRAPLING_INTEL_MAX_LINKS`
- `SAPPHIRE_SCRAPLING_INTEL_QUERY`
- `SAPPHIRE_SCRAPLING_INTEL_TIMEOUT_SECONDS`

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

Full one-command smoke:

```bash
cd /Users/aribs/Sapphire
PROJECT_ID=sapphire-479610 ./scripts/run_scout_sandbox_smoke.sh
```

Optional flags:

- `EXPECT_GTM_DISABLED=true|false` (default `true`)
- `SCRAPLING_SOURCE_URL=https://...`
- `SCOUT_SERVICE=sapphire-scout-sandbox`
- `ALPHA_SERVICE=sapphire-alpha`
