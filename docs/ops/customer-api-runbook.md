# Customer API Runbook

## Purpose

Run the Sapphire customer-facing demo API locally on `127.0.0.1:9000` for
private-beta integration review. The service is mock-only unless future payment
and customer-data gates are explicitly verified.

## Local Start

```bash
cd /Users/aribs/Code/Sapphire
PYTHONPATH=/Users/aribs/Code/Sapphire \
  /usr/local/bin/python3 -m services.customer_api.app
```

## Demo Probe

```bash
curl -i \
  -H 'Authorization: Bearer sapphire_demo_public' \
  http://127.0.0.1:9000/v1/health
```

Expected headers include:

```text
x-sapphire-billed: 0
Cache-Control: no-store
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SAPPHIRE_CUSTOMER_API_KEYS` | demo key set | Comma-separated allowed demo keys |
| `SAPPHIRE_CUSTOMER_API_RATE_LIMIT` | `60` | Requests per key per window |
| `SAPPHIRE_CUSTOMER_API_RATE_WINDOW_SECONDS` | `60` | Sliding-window size |
| `SAPPHIRE_CUSTOMER_API_LIVE` | `0` | Enables live-mode gate checks |
| `SAPPHIRE_CUSTOMER_PAYMENT_INFRA_VERIFIED` | `0` | Required with live mode |

## LaunchAgent Template

Template path:
`services/customer_api/launchagent/com.sapphire.customer-api.plist.template`

It ships disabled for launchd by default (`RunAtLoad=false`, `KeepAlive=false`)
and keeps both live/payment flags off. Do not load it until the operator has
reviewed the target checkout path and log paths.

## Safety Checks

- Anonymous requests return `401`.
- Unknown keys return `401`.
- Rate-limit overflow returns `429` with `Retry-After`.
- `X-Sapphire-Data-Mode: live` returns `403`.
- `SAPPHIRE_CUSTOMER_API_LIVE=1` without verified payment infrastructure returns
  `503`.
- Demo-mode endpoints always return `x-sapphire-billed: 0`.

## Rollback

Stop any local process bound to port `9000`, remove the LaunchAgent copy if one
was manually installed, and revert the feature branch or PR. No persistent data
is created by the demo service.
