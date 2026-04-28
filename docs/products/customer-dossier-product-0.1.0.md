# Sapphire Customer Dossier Product Surface 0.1.0

## What this is

`/customer-dossier` is the buyer-facing dashboard surface that
productizes the existing `tho_intel` plugin tool's customer-side
analytics into a read-only HTML page and a JSON API — with **mandatory,
non-negotiable PII redaction** applied to every leaf of the response.

The surface exists because corp-dev visitors (Palantir Foundry, Robinhood,
Anthropic) need to *see* that Sapphire's CRM-adjacent data (Texas Home
Outlet, the THO client) is reachable from the platform's data plane, but
they must not see any actual customer's name, phone number, email, or
address. The existing `tho_intel.py` plugin tool returns full PII when
called with admin credentials; this product surface deliberately
**downgrades** that data to paste-safe form before it ever crosses the
JSON boundary.

## Routes

* `GET /customer-dossier` — Jinja-rendered HTML page; uses the standard
  dashboard chrome and the same basic-auth as the rest of the site.
* `GET /api/customer-dossier` — JSON envelope. Both routes are
  registered with `methods=["GET"]` only; POST/PUT/DELETE/PATCH return
  HTTP 405 from Flask.

The page reads from `data/tho_intel/dossier_*.json` (latest by filename
sort, falling back to `latest.json`). If no snapshot is on disk, the
page renders an empty-state card pointing at the operator runbook.

## PII redaction contract

Every string leaf in the response — whether it appears in a structured
field (`customer_name`, `phone`, `email`, `address`) or in an
unstructured one (`notes`, `description`, `event`) — is passed through
`lib.security.pii_redactor.redact_record` before encoding. The
redactor's behaviour:

| Input shape | Redacted form |
|---|---|
| Names (`customer_name`, `actor`, etc.) | `customer_<6charhash>` (deterministic, salted SHA-256) |
| Phones | `***-***-NNNN` (last 4 only) |
| Emails | `<first2>***@<domain>` |
| Addresses | `<City>, <ST>` only (street number / apartment / PO box dropped) |
| SSN / DOB / credit card / PIN / API key / token / password / secret | dropped, replaced with literal `<redacted>` |
| Free-text fields | walked for embedded emails / phones / street addresses, scrubbed in place |

The redactor is **pure**: no I/O, no environment reads, no network
calls. A unit test in `tests/unit/test_dashboard_customer_dossier.py`
(`test_redactor_module_is_pure_no_side_effects`) inspects the source
file to confirm the absence of `urllib`, `requests`, `socket`,
`os.environ`, etc. The redactor is also idempotent —
`redact(redact(x)) == redact(x)` — which lets the dashboard route
re-walk the structure without risk of double-encoding.

## Data contract

```json
{
  "mode": "customer_dossier_product_dashboard",
  "available": true,
  "snapshot_at": "2026-04-28T12:00:00Z",
  "snapshot_path_basename": "dossier_2026-04-28.json",
  "summary": {
    "total_customers": 1963,
    "by_status": {"ENROLLED": 1326, "LEAD": 629, "CLOSED": 8},
    "document_templates": 63,
    "deals_recent": 10
  },
  "recent_deals": [{"deal_id": "DEAL-…", "customer_name": "customer_…", …}],
  "metadata": {…},
  "safety": {
    "execution_enabled": false,
    "live_trading_enabled": false,
    "telegram_sends_enabled": false,
    "writes_by_default": false,
    "pii_redaction": "applied_to_every_leaf",
    "guards": [
      "read_only_endpoint",
      "no_live_network_calls",
      "snapshot_only_read",
      "pii_redaction_required"
    ]
  }
}
```

The shape is identical between the empty state and the populated state.
`available: false` flips when no snapshot can be loaded; clients should
key on that flag rather than on the presence of `recent_deals`.

## Test coverage

`tests/unit/test_dashboard_customer_dossier.py` is the *primary*
enforcement point for the PII contract. Beyond shape and auth tests,
the suite specifically asserts that none of the original raw PII tokens
from a deliberately dirty upstream payload survive in the response
bytes. The forbidden-token list includes:

* Full names (`Marie Curie`, `李雷`, `John Doe`)
* Raw phone digit runs (`8675309`, `5550188`, `(312) 555-0188`)
* Email locals (`marie@`, `lilei@`, `john.doe@`)
* Street addresses (`1 Radium Way`, `PO Box 88`, `123 Main St`)
* High-sensitivity values (`123-45-6789`, `1980-01-01`, `4111-1111-1111-1111`,
  the operator PIN `4832`)

These checks run against the *literal HTTP response body*, not against
in-memory fixtures, so any regression in the JSON encoder, the route
handler, or the redactor is caught before merge.

## Snapshot format

The product page does not generate the snapshot. The operator runbook
(`docs/ops/dashboard-product-pages-runbook.md`) covers how the
snapshot is produced from the `tho_intel` plugin. The minimum required
shape for a valid snapshot is:

```json
{
  "snapshot_at": "<ISO 8601 UTC>",
  "document_template_count": <int>,
  "customers": [{"customer_name": "...", "status": "...", ...}],
  "deals": [{"deal_id": "...", "customer_name": "...", ...}],
  "metadata": {...}
}
```

`status` should be a normalized uppercase token (`ENROLLED`, `LEAD`,
`CLOSED`, etc.) so the by-status pill row renders correctly. All other
fields pass through the redactor without further validation.

## Safety posture

* **Read-only HTTP**: GET only; enforced by Flask's method-routing and
  by the `test_api_customer_dossier_returns_only_get` regression test.
* **Authenticated**: shares the dashboard's basic-auth path; no
  per-route credential override.
* **No live network calls**: the route reads from disk only.
* **PII redaction applied to every leaf**: enforced by
  `redact_record()` walking the snapshot recursively before encoding.
* **High-sensitivity drop list**: SSN, DOB, credit card, PIN, API key,
  password, token, secret are all dropped (not partially masked).

## Acquisition narrative

For corp-dev visitors, this surface answers three questions:

1. *Does Sapphire have a customer-data plane?* — yes, and it is
   reachable from the dashboard.
2. *How does Sapphire govern customer-data exposure?* — through a pure,
   versioned, exhaustively-tested redactor that runs on every read path.
3. *Can a buyer point at this URL during diligence without breaching
   downstream PII obligations?* — yes; the redactor's contract is
   strong enough that the dashboard URL is paste-safe in a corp-dev
   meeting.

## Roadmap (post-0.1.0)

* Per-tenant namespacing in the hash salt so two operators viewing the
  same dossier cannot correlate their respective `customer_<hash>`
  tokens across tenants.
* Differential privacy bands on the by-status counts (suppress small
  cell sizes).
* CSV export with the same redaction contract for board decks.
