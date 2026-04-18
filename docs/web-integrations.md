# Sapphire — Web Integrations Reference

Single source of truth for every third-party web integration wired into
Sapphire OS. Pair with `.env.integrations.example` for the env vars each
service needs.

Status icons: ✅ set up & working · ⏳ partial · ❌ blocked (needs Ari)

---

## 0. Overview

```
content engine (06:00 CT)   →  data/content/ready/{linkedin,substack,x}/
        │
        ▼
auto_publish (06:15 CT LaunchAgent)
    ├── LinkedInClient         → LinkedIn UGC API
    ├── SubstackClient         → Resend → post@<pub>.substack.com → draft
    ├── XClient                → X v2 tweets API (OAuth 1.0a)
    └── TypefullyClient        → fallback if X quartet missing
        │
        ▼
event_bus ("content.published")  +  Telegram summary ping
        │
        ▼
data/content/published_ledger.json   (idempotency)
```

On-chain data providers (`lib/chain/providers/`) feed the intelligence
module used by the report generator — so a fresh run can cite MVRV-Z,
funding skew, liquidation levels, whale flow, etc.

---

## 1. Substack — "The Weekly Signal" by Kadima Digital Strategies

| | |
|-|-|
| **Status** | ❌ needs account creation (Ari must click "Create publication" — Substack requires an email-verified human) |
| **Publication name** | The Weekly Signal |
| **Tagline** | Market intelligence from an AI system. Data-driven. No hype. |
| **Sections** | **Free**: Weekly Signal (Tue AM), Monthly Retrospective  ·  **Paid ($15/mo)**: Alpha Signals (raw data, model portfolio, backtests) |
| **Custom domain** | `substack.kadima.digital` (optional, can add later) |

### API reality
Substack has **no public publishing API**. Two real paths:

1. **Email-to-post** (what Sapphire uses) — every publication exposes a
   private `post@<pub>.substack.com` address. Emails land as drafts; Ari
   clicks "Publish" manually after copy review. This is deliberate —
   human-in-the-loop is part of the content quality gate.
2. **Undocumented draft endpoint** — `POST https://substack.com/api/v1/drafts`
   with a session cookie. Enabled only if `SUBSTACK_SESSION_COOKIE` is
   set; expires on logout, so don't rely on it.

### Env vars
```
SUBSTACK_POST_EMAIL=post@kadimadigital.substack.com
RESEND_API_KEY=<from resend.com>
RESEND_FROM_EMAIL=press@kadima.digital
```

### About-page copy (paste into Substack after signup)
> Kadima Digital Strategies helps Houston-area businesses deploy AI that
> pays for itself. I run a self-sovereign trading system, Sapphire OS,
> that generates this newsletter autonomously every week. Everything you
> read is backed by a data source I can show you. I'm Ari — reach out at
> ari@kadima.digital.

---

## 2. LinkedIn

| | |
|-|-|
| **Status** | ⏳ personal profile OK, Kadima company page + developer app needed |
| **Profile** | aristotlespec@gmail.com |
| **Suggested headline** | AI Trading Systems · Founder @ Kadima Digital Strategies · Building self-sovereign intelligence in Houston |

### Company page (one-time)
1. linkedin.com/company/setup/new/
2. Name: **Kadima Digital Strategies**, handle `kadima-digital`
3. Industry: *Information Technology & Services*  ·  Size: *2–10*
4. Tagline: *AI automation, trading systems, and data platforms for Houston SMBs.*
5. Add Ari as admin.

### Developer app (for API posting)
1. linkedin.com/developers/apps → **Create app** → attach the Kadima
   company page (required).
2. Products to request:
   - **Share on LinkedIn** (unlocks `w_member_social`)
   - **Marketing Developer Platform** (unlocks
     `w_organization_social`; requires LinkedIn review — 5–10 business
     days, describe Sapphire as an internal analytics dashboard).
3. Generate a 3-legged OAuth token (tools: Postman collection
   `LinkedIn-API-Postman/collection.json`, or the developer console).
4. Copy to `.env.integrations`:
   - `LINKEDIN_ACCESS_TOKEN=<token>`  (expires in 60 days; refresh via
     refresh_token flow — see `docs/oauth-linkedin.md` TODO)
   - `LINKEDIN_AUTHOR_URN=urn:li:person:<your-id>` (personal)
     or `urn:li:organization:<page-id>` (company).

### Rate limits (2026-04, Developer tier)
- 500 posts / member / day
- 100 API calls / member / hour
- Media upload is a two-step register → upload flow (not implemented yet;
  text-only posts work today).

### Alternatives (if API review takes too long)
- **Buffer** — free tier: 3 channels, 10 scheduled posts. Good short-term.
- **Typefully** — LinkedIn support is paid only (~$12.50/mo).
- **Shield** — analytics-only, no posting.

---

## 3. X (Twitter)

| | |
|-|-|
| **Status** | ⏳ account exists; API tier needs verification |
| **Dev portal** | developer.x.com |
| **Free tier (2026-04)** | 1,500 posts / month *read*, 50 *write* with **Post endpoint** enabled — verify; policy drifts |
| **Basic** | $200/mo — 3,000 reads, 300 writes / day. Not needed yet. |
| **Pro / Enterprise** | $5,000 / $42,000 per month. Not needed. |

### If Free tier allows posting
1. developer.x.com → create project + app with **Read and write** perms.
2. Regenerate the OAuth 1.0a **user context** tokens (v2 `POST /tweets`
   requires user-context, not app-only bearer).
3. Copy to `.env.integrations`:
   ```
   X_API_KEY=...
   X_API_SECRET=...
   X_ACCESS_TOKEN=...
   X_ACCESS_SECRET=...
   ```

### If Free tier does NOT allow posting
`auto_publish` automatically falls through to the Typefully client when
the X quartet is absent but `TYPEFULLY_API_KEY` is set.

### Typefully fallback
- typefully.com/settings/integrations → generate API key.
- Free tier: 1 scheduled thread per day. $12.50/mo lifts to unlimited.
- Thread content is joined with `\n\n\n\n` to force a thread break.

### Buffer fallback
- buffer.com — free tier: 3 channels, 10 scheduled posts total.
- Useful only as a human-review queue; not wired as a publisher yet
  (can be added as `BufferClient` mirroring `TypefullyClient`).

---

## 4. Content Publishing Automation (DONE in code)

| | |
|-|-|
| **Status** | ✅ built; waiting on credentials |
| **Source files** | `lib/content/publishers/*`, `lib/content/auto_publish.py` |
| **Tests** | `tests/unit/test_content_publishers.py` (18 cases) |
| **LaunchAgent** | `infra/launchagents/com.sapphire.content-publisher.plist` (06:15 daily) |
| **CLI** | `python3 -m lib.content --publish` |
| **Dry-run flag** | `SAPPHIRE_PUBLISH_LIVE=0` (default — payload validated, no network) |
| **Ledger** | `data/content/published_ledger.json` — idempotency, so re-runs don't double-post |
| **Event bus** | emits `content.published` per platform (success + failure) |
| **Telegram** | summary ping on every run (priority p1 on any live failure) |

Install the LaunchAgent:

```bash
cp infra/launchagents/com.sapphire.content-publisher.plist \
   ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) \
   ~/Library/LaunchAgents/com.sapphire.content-publisher.plist
launchctl kickstart -k gui/$(id -u)/com.sapphire.content-publisher  # dry-run once
```

Flip to live mode after verifying the ledger + Telegram summary look
right:

```bash
launchctl setenv SAPPHIRE_PUBLISH_LIVE 1
launchctl kickstart -k gui/$(id -u)/com.sapphire.content-publisher
```

---

## 5. On-chain Data Providers (DONE in code)

| Service | Client | Env var | Free-tier ceiling | Key auth |
|---|---|---|---|---|
| BGeometrics | `BGeometricsClient` | `BGEOMETRICS_API_KEY` | ~500 req/day | `Authorization: Bearer <k>` |
| Santiment | `SantimentClient` (GraphQL) | `SANTIMENT_API_KEY` | 600 queries/mo | `Authorization: Apikey <k>` |
| Dune Analytics | `DuneClient` | `DUNE_API_KEY` | 1,000 executions/mo | `X-DUNE-API-KEY: <k>` |
| Whale Alert | `WhaleAlertClient` | `WHALE_ALERT_API_KEY` | 60 req/hour | `?api_key=<k>` |
| CoinAPI | `CoinAPIClient` | `COINAPI_KEY` | 100 req/day | `X-CoinAPI-Key: <k>` |
| Coinglass | `CoinglassClient` | `COINGLASS_API_KEY` | 30 req/min | `coinglassSecret: <k>` |
| Checkonchain | — | — | — | no public API; track manually |

**Signup checklist** (Ari, ~20 min):
1. Visit each URL with `aristotlespec@gmail.com`, confirm email.
2. Copy key into `.env.integrations` using the env var names above.
3. Smoke test with:
   ```bash
   python3 -c "from lib.chain.providers import BGeometricsClient; print(BGeometricsClient().mvrv_z_score())"
   ```
4. For Dune, save one query (e.g., stablecoin supply flow) and note its
   `query_id` — used by `DuneClient.run_query(query_id)`.

All clients share the in-process 5-minute cache in
`lib.chain.sources._cache` — so calling the same endpoint twice in a row
inside a report run only spends one quota unit.

---

## 6. Resend — transactional email (Substack email-to-post + THO site)

| | |
|-|-|
| **Status** | ❌ account + domain verification needed |
| **Signup** | resend.com/signup  (use `aristotlespec@gmail.com`) |
| **Primary domain** | `kadima.digital` (for press@, post-to-substack, newsletter) |
| **Secondary domain** | `texashomeoutlet.com` (Revenue Pipeline #1 — $8K project) |

### DNS records Ari will need to add

Resend issues these on a per-domain basis. After "Add Domain" in the
dashboard, they'll look something like:

```
# SPF (TXT on apex)
@                    TXT   "v=spf1 include:amazonses.com ~all"

# DKIM (three CNAMEs)
resend._domainkey    CNAME resend._domainkey.resend.com
resend2._domainkey   CNAME resend2._domainkey.resend.com
resend3._domainkey   CNAME resend3._domainkey.resend.com

# DMARC (TXT on _dmarc)
_dmarc               TXT   "v=DMARC1; p=none; rua=mailto:ari@kadima.digital"
```

For THO: Ari does not control DNS yet — vendor handover pending. Generate
the records now, hand them to the client when they're ready.

### Env vars
```
RESEND_API_KEY=<from dashboard>
RESEND_FROM_EMAIL=press@kadima.digital          # Sapphire / Substack
RESEND_THO_DOMAIN=texashomeoutlet.com
RESEND_THO_FROM=hello@texashomeoutlet.com
```

### Free tier
- 3,000 emails/month, 100/day, 1 domain.
- Upgrade to **Pro** ($20/mo) for 50k emails/mo, unlimited domains.

### Smoke test
```bash
curl -X POST https://api.resend.com/emails \
    -H "Authorization: Bearer $RESEND_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"from":"press@kadima.digital","to":"aristotlespec@gmail.com","subject":"resend test","text":"hi"}'
```

---

## 7. Cloudflare Tunnels

| | |
|-|-|
| **Status** | ⏳ needs dashboard check |
| **Account** | dash.cloudflare.com (Ari's personal login) |
| **Expected tunnels** | `sapphire-dashboard`, `sapphire-intel`, `sapphire-proxy` |
| **Reference** | `docs/CLOUDFLARE_DNS_SETUP.md` |

### Verification steps (Ari or a Chrome session)
1. dash.cloudflare.com → **Zero Trust → Access → Tunnels**.
2. Each tunnel should be `HEALTHY` (green).
3. Note the public hostname for each (e.g. `dashboard.kadima.digital`).
4. From any non-Tailscale box:
   ```bash
   curl -I https://dashboard.kadima.digital/healthz
   curl -I https://intel.kadima.digital/healthz
   curl -I https://proxy.kadima.digital/healthz
   ```
   Each should return 2xx / 401 (401 is fine — means auth gate is live).

### If a tunnel is degraded
`cloudflared` lives on the Mac at `/opt/homebrew/bin/cloudflared`. Logs:
```
log stream --predicate 'process == "cloudflared"' --level debug
```

Registered-token rotation: CF dashboard → tunnel → *Configure* →
*Delete and recreate* if a token leaks. Keep tunnel IDs out of git.

---

## 8. GCP — project `tho-ai-agent`

| | |
|-|-|
| **Status** | ⏳ needs console + billing check |
| **Console** | console.cloud.google.com |
| **Project ID** | tho-ai-agent |

### Things to verify this week
- **Cloud Run services** — `sapphire-analytics`, `project-go-forward`,
  `tho-agent` should each have traffic in the last 24h.  From gcloud:
  ```bash
  gcloud run services list --project=tho-ai-agent
  gcloud run revisions list --service=sapphire-analytics \
         --region=us-central1 --project=tho-ai-agent --limit=3
  ```
- **BigQuery** — dataset `sapphire`, look at `last_modified_time` on
  each table:
  ```bash
  bq ls --project_id=tho-ai-agent sapphire
  ```
- **Pub/Sub** — subscription health (no unacked accumulation):
  ```bash
  gcloud pubsub subscriptions list --project=tho-ai-agent
  ```
- **Cloud Function** — `sapphire-gcs-to-bq` last invocation + any
  errors:
  ```bash
  gcloud functions logs read sapphire-gcs-to-bq --limit=20 \
         --project=tho-ai-agent
  ```
- **Billing** — console → Billing → Reports. Current-month spend should
  track against the last-quarter baseline; set a $100 budget alert if
  one isn't in place.

---

## Credential storage policy

1. **Never** commit filled-in values. `.env.integrations` is in
   `.gitignore` (matched by `.env.*`, preserved by `!.env.*.example`).
2. Production secrets go in **GCP Secret Manager** under project
   `tho-ai-agent`, with IAM bound to the running service account:
   ```bash
   gcloud secrets create linkedin-access-token \
          --project=tho-ai-agent \
          --replication-policy="automatic"
   echo -n "<token>" | gcloud secrets versions add linkedin-access-token \
          --project=tho-ai-agent --data-file=-
   ```
3. The Mac LaunchAgent loads env via a setup script that pulls from
   Secret Manager; no secrets live in the `.plist`.

---

## Testing matrix

| Layer | Command |
|-------|---------|
| Publishers unit tests | `pytest tests/unit/test_content_publishers.py -q` |
| Provider unit tests | `pytest tests/unit/test_chain_providers.py -q` |
| End-to-end dry run | `SAPPHIRE_PUBLISH_LIVE=0 python3 -m lib.content --publish` |
| End-to-end live (after creds) | `SAPPHIRE_PUBLISH_LIVE=1 python3 -m lib.content --publish` |
| LaunchAgent smoke | `launchctl kickstart -k gui/$(id -u)/com.sapphire.content-publisher` |
