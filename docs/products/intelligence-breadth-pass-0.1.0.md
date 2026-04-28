# Intelligence Breadth Pass 0.1.0

Retrieval date: 2026-04-28.

This pass adds five dry-run-default signal sources to the Sapphire correlator:
DeFiLlama fundamentals, Dune named queries, X handle sentiment, NewsAPI category
headlines, and labor-market breadth. Each adapter emits the existing
`SourceSignal` schema and reports whether its live operator flag was enabled in
`raw.live_operator_flag`.

## Source Coverage

| Source | Signal | Live gate | Cache |
| --- | --- | --- | --- |
| DeFiLlama | TVL plus daily revenue direction for configured protocols | `SAPPHIRE_DEFILLAMA_LIVE=1` | `~/.cache/sapphire/defillama/` |
| Dune | Operator-named query rows with `direction`, `confidence`, or numeric score fields | `SAPPHIRE_DUNE_LIVE=1` | `~/.cache/sapphire/dune/` with 1h TTL |
| X sentiment | Recent-search sentiment across configured handles | `SAPPHIRE_X_SENTIMENT_LIVE=1` | `~/.cache/sapphire/x_sentiment/` |
| NewsAPI | Top headline categories, defaulting to business/technology/science | `SAPPHIRE_NEWSAPI_LIVE=1` | `~/.cache/sapphire/newsapi/` |
| Labor | BLS RSS, USAJOBS public search, and approved career sitemaps | `SAPPHIRE_LABOR_LIVE=1` | `~/.cache/sapphire/labor/` |

## Primary References

- DeFiLlama docs and data definitions, retrieved 2026-04-28:
  https://docs.llama.fi/ and https://defillama.com/data-definitions
- Dune API overview and execution model, retrieved 2026-04-28:
  https://docs.dune.com/api-reference/overview/introduction and
  https://docs.dune.com/api-reference/executions/execution-object
- X API v2 search overview, retrieved 2026-04-28:
  https://developer.x.com/en/docs/x-api/search-overview
- NewsAPI top-headlines endpoint, retrieved 2026-04-28:
  https://newsapi.org/docs/endpoints/top-headlines
- BLS RSS feeds and USAJOBS API reference, retrieved 2026-04-28:
  https://www.bls.gov/feed/ and https://developer.usajobs.gov/api-reference/

## Safety Posture

Live external calls are off by default. Secrets are read from environment
variables first and `~/.sapphire/secrets.env` second; secret values are never
placed in `SourceSignal.raw`. Labor collection is limited to BLS RSS, USAJOBS,
and operator-approved career sitemaps. LinkedIn and Indeed URLs are explicitly
filtered out instead of scraped.

The Dune adapter expects an operator-owned JSON config at
`~/.sapphire/dune_named_queries.json`:

```json
{
  "queries": [
    {"name": "btc_flow", "id": 123456, "symbol": "BTC", "params": {}}
  ]
}
```

The X adapter defaults to an empty handle list, so it emits no signal until an
operator supplies handles in code/config wiring.
