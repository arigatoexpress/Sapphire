# Sapphire Threat Intel Product Surface 0.1.0

## What this is

`/threat-intel` is the buyer-facing dashboard surface that productizes the
existing `threat_intel` plugin tool (which wraps `cyber-threat-bot`) into a
read-only HTML page and a JSON API. It is intended for two audiences:

1. **Acquisition diligence visitors** — Palantir Foundry corp-dev,
   Robinhood Crypto risk team, Anthropic safety reviewers — who need to
   see Sapphire's threat-intelligence stack as a *product*, not a tooling
   subdirectory.
2. **Internal operators** — security on-call, daily-brief readers — who
   want a single, paste-safe URL they can drop into a Slack thread or
   incident channel without first sanitizing the page by hand.

The surface is intentionally minimal. It renders three panels — top
exploited CISA KEV entries, highest-severity NVD CVEs, and the most-cited
MITRE ATT&CK techniques — over the most recent local snapshot of
`data/intelligence/<date>/threats.json`. Nothing is fetched live from the
internet at request time. The page is not interactive: no forms, no POST
buttons, no upload widgets, no comment fields.

## Routes

* `GET /threat-intel` — Jinja-rendered HTML page using the standard
  Sapphire dashboard chrome and `services/dashboard/templates/base.html`.
* `GET /api/threat-intel` — JSON envelope consumed by the page. Both
  routes are gated by the existing `requires_auth` decorator and require
  the dashboard's basic-auth credentials. The page falls through to an
  empty-state banner ("no recent snapshot — last update: …") whenever
  the snapshot is missing or unreadable.

## Data contract

The JSON envelope is intentionally narrow so the page renders the same
shape whether or not data is available:

```json
{
  "mode": "threat_intel_product_dashboard",
  "available": true,
  "snapshot_date": "2026-04-28",
  "refreshed_at": "2026-04-28T03:57:37+00:00",
  "summary": {
    "total_threats": 15,
    "exploited": 9,
    "critical": 3,
    "high": 4,
    "medium": 5,
    "low": 3
  },
  "kev_top": [{"canonical_id": "CVE-…", "severity": "critical", "score": 9.8, …}],
  "nvd_critical": [...],
  "mitre_techniques": [...],
  "safety": {
    "execution_enabled": false,
    "live_trading_enabled": false,
    "writes_by_default": false,
    "telegram_sends_enabled": false,
    "guards": ["read_only_endpoint", "no_live_network_calls", "snapshot_only_read"]
  }
}
```

The `safety` envelope ships in **every** response — even error responses
— so consumers can rely on it as a load-bearing contract.

## Severity classification

Severity is derived purely from `score` (CVSS) and `exploited` (KEV
membership):

| Condition | Severity |
|---|---|
| `exploited=True AND score >= 9.0` | `critical` |
| `exploited=True OR score >= 9.0` | `high` |
| `score >= 7.0` | `medium` |
| otherwise | `low` |

This mapping is deterministic, source-agnostic, and identical between the
HTML and JSON paths. The page colour-codes each row using existing
`sev-*` CSS classes.

## Data freshness

The dashboard reads from the latest dated subdirectory under
`data/intelligence/`. The repo's existing
`services/dashboard/refresh_threats.py` LaunchAgent (cron every 4 hours)
keeps that directory current by invoking `cyber-threat-bot` and writing
`threats.json` plus a `latest` symlink. The product page does not
refresh the data itself — keeping ingest separate from presentation
preserves the read-only guarantee and lets the refresher fail loudly
without disturbing the page.

If the snapshot is older than 24 hours, the meta line displays the
actual snapshot date (e.g. *"Snapshot 2026-04-25 — refreshed
2026-04-25T03:00:00Z"*) so the operator can see the staleness without
clicking through to logs. There is no auto-redirect, no auto-refresh,
and no client-side polling.

## Safety posture

* **Read-only HTTP**: only `GET` is registered. The Flask test suite
  enforces this via `iter_rules()` against `methods`.
* **Authenticated**: `requires_auth` is the same decorator used for the
  rest of the dashboard. There is no per-route credential override.
* **No live network calls**: the route reads JSON from disk. Every
  outbound TCP socket the upstream `cyber-threat-bot` would have opened
  is left to the refresh job, which runs out-of-band.
* **Paste-safe**: the panel only renders fields that are already public
  (CVE ID, vendor, product, score, due date, public summary URL). The
  Jinja template never echoes `data/intelligence` paths, environment
  variables, or operator names. Tests assert no internal terms (e.g.
  `MOONSHOT_API_KEY`) leak into the JSON response.

## Acquisition narrative

For Palantir-style buyers, this surface signals three things:

1. *We have a real cyber-threat ingest pipeline*, not a notebook.
2. *We separate ingest from presentation*, so the customer-visible
   surface is decoupled from the volatile upstream APIs.
3. *We treat read-only routes as a contract*, not a convention. The
   safety envelope is machine-checkable.

For Robinhood-style buyers, the surface demonstrates that we keep the
trading-critical-path hardening discipline applied to *non*-trading
surfaces too — every product route ships with the same safety envelope
that the kill-switch and confirmation-firewall routes ship with.

## Roadmap (post-0.1.0)

* `/threat-intel/feed.atom` — Atom feed for SOC integrations.
* Per-vendor pinning for repeat-offender vendors (currently lives in
  `cyber-threat-bot` config; surfacing it on the product page is a
  natural follow-up).
* Linkable detail pages per CVE — currently the row deep-links to the
  upstream NVD/CISA URL.
