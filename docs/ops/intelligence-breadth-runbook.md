# Intelligence Breadth Runbook

Retrieval date for source docs: 2026-04-28.

## Default Operation

The intelligence breadth adapters are correlator sources, not trading actions.
They are read-only, cache-first, and dry-run by default. The default correlator
source builder now includes:

- `defillama`
- `dune_named_queries`
- `x_sentiment`
- `newsapi`
- `labor`

## Enabling Live Pulls

Put secrets in `~/.sapphire/secrets.env` and enable only the source being tested:

```bash
SAPPHIRE_DEFILLAMA_LIVE=1 python3 -m pytest tests/unit/test_sources_defillama.py -q
SAPPHIRE_DUNE_LIVE=1 python3 -m pytest tests/unit/test_sources_dune.py -q
SAPPHIRE_X_SENTIMENT_LIVE=1 python3 -m pytest tests/unit/test_sources_x_sentiment.py -q
SAPPHIRE_NEWSAPI_LIVE=1 python3 -m pytest tests/unit/test_sources_news.py -q
SAPPHIRE_LABOR_LIVE=1 python3 -m pytest tests/unit/test_sources_labor.py -q
```

Expected secret names:

- `DUNE_API_KEY`
- `X_BEARER_TOKEN`
- `NEWSAPI_KEY`
- `USAJOBS_API_KEY`
- `USAJOBS_USER_AGENT` as the contact email/header value for USAJOBS

DeFiLlama does not require a secret. All live responses are cached under
`~/.cache/sapphire/<source>/`.

## Dune Named Queries

Create `~/.sapphire/dune_named_queries.json`:

```json
{
  "queries": [
    {
      "name": "eth_net_flow",
      "id": 123456,
      "symbol": "ETH",
      "params": {}
    }
  ]
}
```

The adapter reuses a fresh cache for one hour. Query rows can provide
`direction` plus `confidence`, or a numeric `score`, `value`, or `net_flow`.

## Labor Sources

Allowed labor sources are:

- BLS RSS feeds: https://www.bls.gov/feed/
- USAJOBS API search: https://developer.usajobs.gov/api-reference/
- Operator-supplied career sitemap XML

Do not add LinkedIn or Indeed scraping. The adapter filters those hosts from
career sitemap inputs.

## Verification

Focused lane checks:

```bash
python3 -m pytest \
  tests/unit/test_sources_defillama.py \
  tests/unit/test_sources_dune.py \
  tests/unit/test_sources_x_sentiment.py \
  tests/unit/test_sources_news.py \
  tests/unit/test_sources_labor.py \
  tests/unit/test_correlator_sources.py -q
python3 scripts/validate_tool_registry.py
ruff check lib/sources lib/correlator/sources.py tests/unit/test_sources_*.py
git diff --check
```
