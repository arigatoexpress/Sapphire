# Inference Tenant Quotas

The inference proxy supports in-process tenant quotas and per-tenant prompt
cache TTLs for `/v1/chat/completions`.

This is a no-spend safety layer. It does not grant access to any model tier, and
it does not replace the sensitivity classifier or x402 payment gate.

## Configuration

Default local mode stays compatible with existing callers:

```bash
INFERENCE_DEFAULT_REQUESTS_PER_DAY=1000
INFERENCE_DEFAULT_TOKENS_PER_DAY=500000
INFERENCE_DEFAULT_CACHE_TTL_SECONDS=300
INFERENCE_MAX_TOKENS_PER_REQUEST=4096
INFERENCE_REQUIRE_API_KEY=0
```

Per-key policy can be supplied through `INFERENCE_QUOTAS_JSON` or
`INFERENCE_QUOTAS_FILE`. Keep the file in `~/.config/sapphire-secrets/` or
`~/.sapphire/secrets.env`; do not commit it.

```json
{
  "default": {
    "requests_per_day": 1000,
    "tokens_per_day": 500000,
    "cache_ttl_seconds": 300
  },
  "keys": {
    "actual-api-key-value": {
      "tenant": "operator",
      "requests_per_day": 250,
      "tokens_per_day": 100000,
      "cache_ttl_seconds": 60
    }
  }
}
```

Set `INFERENCE_REQUIRE_API_KEY=1` to reject missing or unknown keys.

## Request Headers

Accepted key headers:

- `X-API-Key: <key>`
- `X-Sapphire-API-Key: <key>`
- `Authorization: Bearer <key>`

Raw API keys are hashed in memory for matching and are never returned by
`/v1/quota` or `/v1/cache-stats`.

## Endpoints

`GET /v1/quota` returns the current tenant's policy and usage.

`GET /v1/cache-stats` returns aggregate cache counts by tenant id plus global
hit/miss/write/eviction counters.

Quota response headers on POST include:

- `X-Inference-Tenant`
- `X-Inference-Quota-Remaining-Requests`
- `X-Inference-Quota-Remaining-Tokens`
- `X-Inference-Cache` (`hit`, `miss`, or `bypass`)

## Cache Behavior

Only non-sensitive chat requests are cacheable. Sensitive prompts bypass the
cache and still stay blocked from Kimi Cloud by the sensitivity classifier.

Cache entries are scoped by tenant id, path, and canonical request payload.
Cache hits still count against the request quota, but they avoid a second model
call and do not add model spend.
