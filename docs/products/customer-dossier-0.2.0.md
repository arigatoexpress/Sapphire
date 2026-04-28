# Sapphire Customer Dossier Product Surface 0.2.0

> **What changed since 0.1.0**: per-tenant hash isolation
> (HMAC-SHA256 with operator-configured salts) and cell-suppression for
> small status buckets. Both items came directly from the 0.1.0 roadmap
> (PR #374). Backward-compatible: a tenant without a configured salt
> continues to receive a stable, deterministic-but-randomized hash, and
> the response shape is a strict superset of 0.1.0.

## What this is

`/customer-dossier` is the buyer-facing dashboard surface that
productizes the existing `tho_intel` plugin tool's customer-side
analytics into a read-only HTML page and a JSON API — with **mandatory,
non-negotiable PII redaction** applied to every leaf of the response,
**per-tenant hash isolation** for cross-snapshot correlation, and
**cell-suppression** on the status-count distribution.

The surface exists because corp-dev visitors (Palantir Foundry,
Robinhood, Anthropic) need to *see* that Sapphire's CRM-adjacent data
(Texas Home Outlet, the THO client) is reachable from the platform's
data plane, but they must not see any actual customer's name, phone
number, email, or address. The existing `tho_intel.py` plugin tool
returns full PII when called with admin credentials; this product
surface deliberately **downgrades** that data to paste-safe form before
it ever crosses the JSON boundary.

## Routes

* `GET /customer-dossier` — Jinja-rendered HTML page; uses the standard
  dashboard chrome and the same basic-auth as the rest of the site.
* `GET /api/customer-dossier` — JSON envelope. Both routes are
  registered with `methods=["GET"]` only; POST/PUT/DELETE/PATCH return
  HTTP 405 from Flask.
* `GET /api/customer-dossier?tenant=<id>` — *new in 0.2.0*. The optional
  query string scopes the per-tenant hash output to a specific tenant.
  When omitted the surface uses the literal `default` tenant id.

The page reads from `data/tho_intel/dossier_*.json` (latest by filename
sort, falling back to `latest.json`). If no snapshot is on disk, the
page renders an empty-state card pointing at the operator runbook.

## PII redaction contract (unchanged from 0.1.0)

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

The redactor remains **pure**: no I/O, no environment reads, no network
calls. The 0.2.0 `per_tenant_hash` function is an addition to the same
module and preserves the purity contract — env reads happen in the
dashboard layer, not in the redactor itself.

## Per-tenant hash isolation (new in 0.2.0)

For each customer in the snapshot, the response now includes a
deterministic per-tenant hash under `customer_hashes[*].per_tenant_hash`.
The hash shape is:

    tenant_<normalized-tenant-id>_<16hex>

The `<16hex>` portion is the first 16 hex chars of an HMAC-SHA256
digest, keyed by the operator-configured per-tenant salt and seeded
with the canonicalized customer anchor (preferring `customer_name`,
falling back to `email`, `id`, or `customer_id`). Properties:

* **Deterministic per `(value, tenant, salt)`** — the same upstream
  customer always maps to the same hash, so a tenant can correlate
  their own records across snapshots without ever seeing raw PII.
* **Isolated across tenants** — different `tenant` query strings
  produce different hashes for the same upstream customer. A buyer
  cannot cross-link their tenants by matching hash strings.
* **Salt rotation** — rotating
  `SAPPHIRE_DOSSIER_HASH_SALT_<TENANT>` invalidates every previously
  emitted hash for that tenant. Other tenants' hashes are unaffected.
* **Backward compat** — when no salt is configured, the surface
  derives a deterministic-but-randomized default salt from the tenant
  id alone, so 0.1.0 callers without a configured salt continue to
  receive stable hashes (no breaking change).

### Salt configuration

Operator-configured salts live in `~/.sapphire/secrets.env` (mode
`0600`). The recognized variable name is:

    SAPPHIRE_DOSSIER_HASH_SALT_<NORMALIZED_TENANT_ID>=<random-32+-bytes>

The dashboard normalizes the tenant id to ASCII alnum + underscore
before lookup (e.g. `acme corp` → `ACME_CORP`). Live-mode rotation:
update the variable in `~/.sapphire/secrets.env`, restart the
dashboard service. The `tenant.salt_source` field in the JSON
response will switch from `default_fallback` to `configured` once
the env value is loaded.

## Cell-suppression on small buckets (new in 0.2.0)

`summary.by_status` now reports any bucket with a count strictly less
than 5 as the literal string `"<5"` instead of an exact integer.
Buckets at or above the threshold pass through unchanged.

This addresses the small-cohort re-identification risk from 0.1.0: in a
sufficiently filtered snapshot, a `by_status` bucket of count 1 was
effectively a unique identifier. With cell-suppression, a buyer can
still see the *shape* of the distribution (a 1326-customer ENROLLED
bucket vs. a small CLOSED tail) without learning the exact count of
small cohorts.

The threshold (5) is documented in the response under
`summary.cell_suppression`:

```json
"cell_suppression": {
  "applied": true,
  "threshold": 5,
  "marker": "<5"
}
```

The marker is intentionally a string (`"<5"`) rather than a numeric
sentinel (`-1`, `null`, etc.) so naive consumers fail loudly when
attempting integer arithmetic on suppressed buckets — better a clean
TypeError than a silently-wrong sum.

## Data contract (0.2.0)

```json
{
  "mode": "customer_dossier_product_dashboard",
  "available": true,
  "snapshot_at": "2026-04-28T12:00:00Z",
  "snapshot_path_basename": "dossier_2026-04-28.json",
  "summary": {
    "total_customers": 1963,
    "by_status": {"ENROLLED": 1326, "LEAD": 629, "CLOSED": "<5"},
    "document_templates": 63,
    "deals_recent": 10,
    "cell_suppression": {"applied": true, "threshold": 5, "marker": "<5"}
  },
  "tenant": {
    "id": "acme",
    "salt_source": "configured",
    "hash_algorithm": "HMAC-SHA256"
  },
  "customer_hashes": [
    {"per_tenant_hash": "tenant_acme_a1b2c3d4e5f60718", "status": "ENROLLED"}
  ],
  "recent_deals": [{"deal_id": "DEAL-…", "customer_name": "customer_…", ...}],
  "metadata": {...},
  "safety": {
    "execution_enabled": false,
    "live_trading_enabled": false,
    "telegram_sends_enabled": false,
    "writes_by_default": false,
    "pii_redaction": "applied_to_every_leaf",
    "cell_suppression": "applied",
    "per_tenant_hash": "applied",
    "guards": [
      "read_only_endpoint",
      "no_live_network_calls",
      "snapshot_only_read",
      "pii_redaction_required",
      "cell_suppression_lt_5",
      "per_tenant_hmac_sha256"
    ]
  }
}
```

The shape is a strict superset of the 0.1.0 contract:

* `summary.cell_suppression` is new.
* `tenant` and `customer_hashes` are new top-level keys.
* `safety.cell_suppression`, `safety.per_tenant_hash`, and the two new
  guard strings under `safety.guards` are additions.

Existing 0.1.0 consumers that ignore unknown keys will continue to
function with no code change.

## Test coverage

* `tests/unit/test_pii_redactor.py` — the original 0.1.0 redactor
  contract suite (77 tests).
* `tests/unit/test_dashboard_customer_dossier.py` — the original
  dashboard-route tests, updated to assert the cell-suppression
  format on the existing fixtures.
* `tests/unit/test_pii_redactor_per_tenant_hash.py` — *new in 0.2.0*,
  22 tests covering determinism, tenant isolation, salt rotation,
  fallback behaviour, output shape, and a defensive purity guard.
* `tests/unit/test_dashboard_customer_dossier_v2.py` — *new in 0.2.0*,
  16 tests covering cell-suppression and per-tenant hash end-to-end
  through the Flask test client.

The forbidden-token regression list (no raw PII in response bytes) is
preserved unchanged from 0.1.0 and now also asserts that the per-tenant
hash is opaque (the raw input cannot be reconstructed from the hash).

## Snapshot format

Unchanged from 0.1.0 — the product page does not generate snapshots.
The operator runbook
(`docs/ops/dashboard-product-pages-runbook.md`) covers how the
snapshot is produced from the `tho_intel` plugin. The 0.2.0 surface
prefers the `customer_name` field for hash anchoring; if that is
missing it falls back to `email`, then `id`, then `customer_id`.
Customers with none of those fields are skipped from the
`customer_hashes` list entirely (they still count toward the
`summary.total_customers` and `summary.by_status` aggregates).

## Safety posture

* **Read-only HTTP**: GET only; enforced by Flask's method-routing and
  the `test_api_customer_dossier_returns_only_get` regression test.
* **Authenticated**: shares the dashboard's basic-auth path.
* **No live network calls**: the route reads from disk only.
* **PII redaction applied to every leaf**.
* **Cell-suppression on small buckets**: counts <5 emit `"<5"`.
* **Per-tenant hash isolation**: HMAC-SHA256 with operator-configured
  salts, deterministic-but-randomized fallback for non-live mode.
* **No secret echo**: the loaded salt value is never reflected in the
  response. Only the `salt_source` discriminator (`configured` vs
  `default_fallback`) is exposed.

## Acquisition narrative (0.2.0 update)

For corp-dev visitors, this surface now answers four questions instead
of three:

1. *Does Sapphire have a customer-data plane?* — yes, and it is
   reachable from the dashboard.
2. *How does Sapphire govern customer-data exposure?* — through a
   pure, versioned, exhaustively-tested redactor and the per-tenant
   hash isolation contract above.
3. *Can a buyer point at this URL during diligence without breaching
   downstream PII obligations?* — yes; the redactor's contract is
   strong enough that the dashboard URL is paste-safe in a corp-dev
   meeting.
4. *Can a multi-tenant buyer (Foundry, Robinhood) operate this surface
   without correlating across tenants?* — yes; per-tenant HMAC-SHA256
   hashes guarantee that two tenants viewing the same source data
   receive disjoint hash spaces.

## Roadmap (post-0.2.0)

* CSV / Parquet export with the same redaction contract for board
  decks (was on the 0.1.0 roadmap).
* Differential-privacy noise on the by-status counts above the
  cell-suppression threshold (Laplace mechanism with operator-tunable
  ε), pending an honest assessment of whether the buyer audience
  requires it.
* Audit log of per-tenant hash queries for buyer-facing access
  reviews; today the dashboard's basic-auth log is the only trail.
