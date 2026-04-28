# Performance Endpoint Validation - 2026-04-28

Agent C validation after the BacktestEngine adapter merge.

## Runtime

- Checkout: `/Users/aribs/Code/Sapphire`
- Command: `AUTH_USERNAME=sapphire AUTH_PASSWORD=<non-default-local> PORT=18080 /usr/local/bin/python3 app.py`
- Note: the current dashboard rejects `AUTH_PASSWORD=sapphire` as a known weak default, so the smoke used a temporary non-default local password.
- Probe style: `/usr/bin/curl` with an `Authorization: Basic ...` header.

## Endpoint Health

| Endpoint | HTTP | JSON | Payload health |
| --- | ---: | --- | --- |
| `/api/strategy-performance` | 200 | valid | 9 trades, 3 symbols |
| `/api/performance-timeseries` | 200 | valid | 9 equity points, 9 trades |
| `/api/backtest-results?metric=sortino&limit=3` | 200 | valid | 7 leaderboard rows, 6 summary rows |
| `/api/forecast` | 200 | valid | 6 forecast rows, 6 symbols |
| `/api/prediction-accuracy` | 200 | valid | 36 scored, 42 total, 3 symbols |

## Result

PASS. The `/performance` data endpoints remain healthy and nonempty against the canonical local data surface after the BacktestEngine adapter change.
