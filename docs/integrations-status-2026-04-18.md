# Sapphire — Web Integrations Status Report
Session date: **2026-04-18** · Requested by: Ari

## Summary

| # | Section | Status | What's blocking |
|---|---------|--------|-----------------|
| 1 | Substack newsletter | ❌ Blocked | Slug chosen: `agentdev.substack.com`. Needs Ari to accept publisher ToS + finish wizard |
| 2 | LinkedIn profile / company page / app | ⏳ Partial | Ari needs to update headline, create company page, register developer app (5–10 day review for `w_organization_social`) |
| 3 | X / Twitter API | ⏳ Partial | Dev portal confirmed (`@rariwrld`, pay-per-use billing, $0 balance). Needs a small credit top-up before live posts; Typefully fallback wired in code |
| 4 | Content publishing automation | ✅ Done | Live on merge — currently dry-run until credentials land |
| 5 | Free on-chain APIs (6 clients) | ⏳ Partial | Clients built; signups + API keys needed (BGeometrics, Santiment, Dune, Whale Alert, CoinAPI, Coinglass) |
| 6 | Resend transactional email | ❌ Blocked | Ari needs to sign up + verify `kadima.digital` and `texashomeoutlet.com` domains |
| 7 | Cloudflare tunnel health check | ❌ Blocked | Chrome session not signed into Cloudflare. Easiest unblock: `CLOUDFLARE_API_TOKEN` with `Zone.Read + Account.Cloudflare Tunnel.Read` |
| 8 | GCP (`tho-ai-agent`) health check | ✅ Done | Project nominal: billing $6.20 (Apr 1–18), 0 app errors/24h, all services normal. Cloud Run live: `sapphire-analytics`, `sapphire-gcs-to-bq`, `tho-agent`, `project-go-forward`, `agentic-pm-hub`. No `sapphire-alpha` visible — needs reconciliation |

Only sections 4 & 5-code could be completed fully autonomously. Everything with ❌ / ⏳ needs you at the keyboard — the blocker is always account creation, payment, DNS, or 2FA, which I can't safely do on your behalf.

## ✅ What I built (all committed-ready, none pushed)

### 4. Content publishing pipeline — fully wired, dry-run by default

**New files:**
- `lib/content/publishers/` — four live clients:
  - `LinkedInClient` — UGC Posts API, text + media URN support
  - `SubstackClient` — Resend email-to-post (Substack has no public API)
  - `XClient` — v2 tweets API, OAuth 1.0a, auto-threading
  - `TypefullyClient` — fallback for X when OAuth quartet is missing
  - `base.py` — shared `PublisherClient` with dry-run default, never-raise contract, env-only credentials
- `lib/content/auto_publish.py` — orchestrator that
  - scans `data/content/ready/{linkedin,substack,x}/` for new renderings
  - deduplicates via `data/content/published_ledger.json`
  - dispatches through the right client (auto-falls back X → Typefully)
  - emits `content.published` events on the bus
  - sends a priority-tagged Telegram summary
- `lib/content/__main__.py` — added `--publish` subcommand
- `infra/launchagents/com.sapphire.content-publisher.plist` — 06:15 CT daily, 15 min after content-engine
- `tests/unit/test_content_publishers.py` — 18 tests, all mocked HTTP

**Dry-run default** — `SAPPHIRE_PUBLISH_LIVE=0` means clients validate the payload but never hit the network. Flip to `1` in the LaunchAgent once you've confirmed a dry-run ledger + Telegram ping look correct.

### 5. On-chain data provider clients — code done, keys still needed

**New files** (`lib/chain/providers/`):
- `bgeometrics.py` — MVRV-Z, SOPR, NVT, Puell, realized price
- `santiment.py` — GraphQL social/dev activity
- `dune.py` — execute + poll + results convenience wrapper
- `whale_alert.py` — whale transaction stream
- `coinapi.py` — OHLCV + funding
- `coinglass.py` — OI + funding + liquidations
- `_common.py` — shared HTTP helpers, reuses `lib.chain.sources` cache
- `tests/unit/test_chain_providers.py` — 9 tests, header + payload assertions

All six clients share the existing 5-minute cache so a cold run through the report generator costs at most one quota unit per endpoint.

### Supporting

- `.env.integrations.example` — complete env-var template for all integrations (already covered by `.gitignore`'s `.env.*` rule; `.example` is whitelisted)
- `env.example` updated to point at the new file
- `docs/web-integrations.md` — single source of truth: endpoints, rate limits, OAuth scopes, DNS records, signup checklists, smoke-test commands

## ❌ What needs you

### Account creation (I can't do these safely)
1. **Substack** — create publication "The Weekly Signal", set tagline + sections + about page.
2. **LinkedIn** — update headline, create Kadima Digital company page, register developer app at linkedin.com/developers, apply for Marketing Developer Platform.
3. **X/Twitter** — log into developer.x.com, confirm current API tier.
4. **Resend** — sign up, verify both domains, add the DNS records (template in `docs/web-integrations.md` §6).
5. **BGeometrics / Santiment / Dune / Whale Alert / CoinAPI / Coinglass** — six free-tier signups, keys into `.env.integrations`.

### Dashboards (need Chrome session I can't reach)
6. **Cloudflare tunnels** — 3-tunnel health check.
7. **GCP `tho-ai-agent`** — Cloud Run / BigQuery / Pub/Sub / billing verification.

### Access I requested but didn't get
- Chrome browser control — the extension shows "not connected" in this session.
- `computer-use` approval dialog — timed out twice. If you want me to try the browser-side work live, open Chrome with the Claude extension signed in, then say "try Chrome again" and I'll re-request access.

## Ready-to-run commands

```bash
# Run the new tests (on your Mac with Python 3.11+)
/usr/local/bin/python3 -m pytest tests/unit/test_content_publishers.py \
  tests/unit/test_chain_providers.py -q

# Dry-run the publisher end-to-end
/usr/local/bin/python3 -m lib.content --publish

# Load .env.integrations into launchd (required before LaunchAgents see creds)
chmod 600 .env.integrations
scripts/load_integrations_env.sh

# Smoke-test every integration — PASS/FAIL/SKIP table, exits 1 on any FAIL
scripts/smoke_integrations.py
scripts/smoke_integrations.py resend,cloudflare      # probe a subset
scripts/smoke_integrations.py --json                  # machine-readable

# Install the publisher LaunchAgent
cp infra/launchagents/com.sapphire.content-publisher.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) \
  ~/Library/LaunchAgents/com.sapphire.content-publisher.plist
launchctl kickstart -k gui/$(id -u)/com.sapphire.content-publisher

# Flip to live (after you've added creds + reviewed a dry-run run)
launchctl setenv SAPPHIRE_PUBLISH_LIVE 1
launchctl kickstart -k gui/$(id -u)/com.sapphire.content-publisher
```

## Shortest path to live

1. Sign up for Substack, Resend, and Typefully (15 minutes).
2. Drop the 3 keys into `.env.integrations` + verify the Resend domain.
3. Kick off the LaunchAgent in dry-run, check the Telegram ping.
4. Flip `SAPPHIRE_PUBLISH_LIVE=1`. Tuesday morning publishes automatically.

LinkedIn's UGC posting works today with `w_member_social` (instant grant) — you don't need to wait for the Marketing Developer Platform review to ship personal posts. Company-page posting is the only thing gated on review.

X is the least-likely near-term win. Free tier posting is heavily restricted; Typefully at $12.50/mo is the cheapest real option.

---

## Live dashboard scan (Chrome session, 2026-04-18)

After the session resumed with the Chrome extension connected, I pulled each dashboard and captured the actual state. Updates to the table at the top of this doc reflect these findings.

| Service | Logged in? | Key facts |
|---------|------------|-----------|
| Substack | ✅ as `@arispector` (aristotlespec@gmail.com) | Slug chosen: `agentdev.substack.com`. `publisher_agreement_accepted_at: null` — Ari still needs to accept ToS and complete the wizard. |
| LinkedIn | ❌ authwall | Chrome session is not signed in. Ari mentioned being logged into Brave, but the extension is Chrome-only. Either sign into LinkedIn in Chrome, or do the profile/page work directly in Brave. |
| X Developer Console | ✅ as `@rariwrld` | **Pricing model changed**: now pay-per-use consumption billing (no more Free/Basic/Pro monthly tiers). Balance $0.00, 0 credits, 0 requests past 30 days. `.env.integrations.example` comment for X has been corrected to reflect this. |
| Cloudflare | ❌ login screen | Not signed in; can't enumerate tunnels until Ari logs in or provides an API token with `Account.Cloudflare Tunnel.Read`. |
| GCP (`tho-ai-agent`) | ✅ | Project number `691674245427`. Billing: **$6.20 for Apr 1–18**, all services normal, 0 app errors / 24h. Cloud Run services observed: `sapphire-analytics` (updated 23h ago), `sapphire-gcs-to-bq` (23h), `tho-agent` (3d), `project-go-forward` (3d), `agentic-pm-hub` (Feb 23). Note: no `sapphire-alpha` visible — the env.example still points at the old Cloud Run URL; may need the Vite base URL updated or the service renamed/redeployed. |

### Immediate knock-on items

- **X**: Before flipping `SAPPHIRE_PUBLISH_LIVE=1` for X, buy a small credit balance at console.x.com (or link an xAI team for free credits). The publisher client will still work (OAuth 1.0a unchanged) but hits will fail on a $0 balance. Profile bio was refreshed this session (`🤖 Autonomous trading + on-chain intelligence + weekly signal reports. Live AI telemetry from Sapphire's agent mesh. Open-source.`). Profile picture still needs Ari to upload — I don't have an image.
- **sapphire-alpha reality check**: `scripts/deploy/deploy_sapphire_alpha.sh` targets project `sapphire-479610` (project number 267358751314), which per the 2026-04-15 cloud audit has **zero** Cloud Run services and billing disabled. So `VITE_ALPHA_BASE_URL=https://sapphire-alpha-267358751314.us-central1.run.app` points to a service that was never deployed (or got torn down). Either (a) run the deploy script against `tho-ai-agent` instead, (b) enable billing on `sapphire-479610` and deploy there, or (c) point the Vite URL at `sapphire-analytics` in `tho-ai-agent` if that's where the alpha engine now lives.
- **Cloudflare tunnels**: `scripts/ops/verify_tunnels.sh` is now written. Once `CLOUDFLARE_API_TOKEN` (scopes: `Account.Cloudflare Tunnel.Read`, `Zone.Read`) and `CLOUDFLARE_ACCOUNT_ID` are set, `bash scripts/ops/verify_tunnels.sh` enumerates every tunnel + its connection health without needing dashboard access. Exits 0 on all-healthy, 2 on any unhealthy.
- **Substack publication**: I got as far as the "Start publishing" flow (logged in as `@arispector`, TOS not yet accepted), then stopped at the publisher-agreement checkbox — accepting ToS is an explicit-permission action that needs Ari. Slug decided: **`agentdev.substack.com`**. Publication display name TBD (recommend "Agent Dev" or "Agent Dev Log"). See `docs/ari-handoff-checklist.md` §1 for paste-ready tagline + about copy.

### What remains gated on Ari

| # | Action | Time |
|---|--------|------|
| 1 | Accept Substack publisher ToS, finish wizard for `agentdev.substack.com` (name/tagline/about in handoff §1) | 5 min |
| 2 | Sign up Resend + verify `kadima.digital` + `texashomeoutlet.com` domains | 10 min + DNS propagation |
| 3 | Buy $5–$10 of X credits (optional — for live X posting) | 2 min |
| 4 | Sign 6 free on-chain API signups + drop keys into `.env.integrations` | 15 min |
| 5 | Generate Cloudflare API token (scoped read-only) | 2 min |
| 6 | LinkedIn profile headline + Kadima company page + dev app (easiest from Brave where you're already signed in) | 30 min |
| 7 | Decide sapphire-alpha target (deploy to `tho-ai-agent`, enable billing on `sapphire-479610`, or repoint VITE_ALPHA_BASE_URL) | 5 min |
| 8 | Upload profile picture to X (`@rariwrld`) — I can't provide the image | 1 min |

GCP health check is one-liner if you want it scripted:
`gcloud run services list --project=tho-ai-agent --format='table(name,status.url,updateTime)'`

*Generated from this session's work. See `docs/web-integrations.md` for the full reference — endpoints, rate limits, DNS templates, smoke tests.*
