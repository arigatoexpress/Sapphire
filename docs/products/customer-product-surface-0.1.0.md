# Customer Product Surface 0.1.0

Sapphire Customer Product Surface is a demo-safe external API and microsite for
private-beta review. It packages three customer-facing product lines without
connecting to real customer data, real payment capture, or the trading critical
path.

## Scope

- Static microsite: `web/customer/index.html`
- Flask service: `services/customer_api/app.py`
- LaunchAgent template: `services/customer_api/launchagent/com.sapphire.customer-api.plist.template`
- API routes: `/v1/health`, `/v1/threat-intel`, `/v1/narrative`,
  `/v1/cross-asset`, `/v1/private-beta/request`

## Product Lines

| Product | Route | Status |
| --- | --- | --- |
| Threat Intel API | `GET /v1/threat-intel` | Mock payloads only |
| Narrative API | `GET /v1/narrative` | Mock payloads only |
| Cross-Asset API | `GET /v1/cross-asset` | Mock payloads only |

## Safety Contract

- Demo keys only by default: `sapphire_demo_public`,
  `sapphire_demo_partner`, and `sapphire_beta_demo`.
- Every demo response includes `mock=true` and `x-sapphire-billed: 0`.
- Real customer data requests are refused with `403`.
- Live mode refuses service unless `SAPPHIRE_CUSTOMER_API_LIVE=1` and
  `SAPPHIRE_CUSTOMER_PAYMENT_INFRA_VERIFIED=1`.
- Private beta requests are acknowledged but not stored.
- No real charges are initiated by this surface.

## Example

```bash
curl -s \
  -H 'Authorization: Bearer sapphire_demo_public' \
  http://127.0.0.1:9000/v1/cross-asset
```

The expected body is deterministic demo data and contains `"mock": true`.

## Non-Goals

- No real customer CRM ingestion.
- No live facilitator settlement.
- No trading execution or order-draft path.
- No external JavaScript, analytics, fonts, or CDN resources.
