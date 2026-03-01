# Intel Feed Integration (Glint-Style) — 2026-02-28

## What shipped
- New alpha-engine feed module:
  - `services/alpha-engine/src/feeds/intel_feed.py`
- New alpha-engine endpoint:
  - `GET /intel/feed` (served by shared health server)
- New public frontend contract + page:
  - `GET /api/platform/intel-feed`
  - `GET /feed`

## Source strategy
Default ingestion is **safe-source-first**:
- Google News RSS (crypto + AI)
- Hacker News API (crypto + AI)
- GitHub search API (AI repo momentum)

## Glint scrape policy
Direct scrape logic exists only as an **optional fallback** and is blocked by default.

Env flags:
- `SAPPHIRE_GLINT_SCRAPE_ENABLED=false` (default)
- `SAPPHIRE_GLINT_SCRAPE_SANDBOX_ONLY=true` (default)

Behavior:
- Production: scrape blocked unless explicitly enabled and sandbox restriction lifted.
- Sandbox/dev: scrape allowed when enabled.

## Why this approach
- Reduces legal/compliance risk vs brittle full-site scraping.
- Keeps feed quality stable with documented upstreams.
- Preserves optional sandbox experimentation path for SCOUT.

## Frontend goals aligned
- Mobile-first shell improvements in `base.html`
- New tactical but business-facing feed surface (`/feed`)
- Security/privacy messaging updated (including zk attestation roadmap)

## 2026-03-01 hardening update
- SCOUT sandbox now exposes a dedicated collector endpoint:
  - `POST /v1/intel/glint_collect`
  - file: `services/scout-sandbox/app.py`
- Collector policy remains allowlisted + token-gated:
  - host/path checks for `glint.trade/feed`
  - optional authenticated Glint API mode via:
    - `SCOUT_SANDBOX_INTEL_GLINT_API_URL`
    - `SCOUT_SANDBOX_INTEL_GLINT_BEARER_TOKEN` (secret-backed)
- Alpha-engine now consumes Glint intel through SCOUT sandbox by default:
  - file: `services/alpha-engine/src/feeds/intel_feed.py`
  - env toggles wired in deploy script:
    - `SAPPHIRE_GLINT_USE_SCOUT_SANDBOX`
    - `SAPPHIRE_GLINT_SOURCE_URL`
    - `SAPPHIRE_GLINT_SANDBOX_LIMIT`
- Unified frontend intel contract hardened against transient upstream failures:
  - `_get_json()` retries transient HTTP/network errors before fallback.
  - `/api/platform/intel-feed` performs a forced refresh retry before degrading to Firestore logs.
  - file: `services/unified-frontend/app.py`
