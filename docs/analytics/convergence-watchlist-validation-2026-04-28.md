# Convergence Watchlist Validation - 2026-04-28

Agent C validation after the BacktestEngine adapter merge.

## Runtime

- Checkout: `/Users/aribs/Code/Sapphire`
- Command: `AUTH_USERNAME=sapphire AUTH_PASSWORD=<non-default-local> PORT=18080 /usr/local/bin/python3 app.py`
- Probe style: `/usr/bin/curl` with an `Authorization: Basic ...` header.

## Endpoint Health

| Endpoint | HTTP | JSON | Payload health |
| --- | ---: | --- | --- |
| `/api/convergence-watchlist` | 200 | valid | 5 tiers, 5 key insights, 3 catalyst highlights |

Observed top-level keys:

```text
catalyst_calendar_highlights, generated, key_insights, risks, source,
source_file, thesis, tiers
```

Observed tier keys:

```text
conservative_core, etf_layer, growth_satellite, pre_ipo_watchlist,
speculative_moonshots
```

## Result

PASS. `/api/convergence-watchlist` still serves the Kimi P1 research watchlist as valid, nonempty JSON and does not depend on the Backtester adapter path.
