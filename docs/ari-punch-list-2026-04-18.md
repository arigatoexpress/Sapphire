# Ari — when you get back

Single punch list of everything still gated on your click/tap. Ordered by time-to-value.

---

## Priority queue

| # | Task | Minutes | Why it's gated on you |
|---|------|---------|------------------------|
| 1 | **Finish Cloudflare token creation** (tab already open, form pre-filled) | 1 | Token value shown once — you copy, not me. Creating credentials is an explicit-permission action. |
| 2 | **Sign up for Resend + paste DNS at Namecheap + create API key** | 10 + DNS wait | Account creation + ToS acceptance. Namecheap Advanced DNS panel: https://ap.www.namecheap.com/Domains/DomainControlPanel/kadima.digital/advancedns |
| 3 | **LinkedIn dev app creation in Brave** | 5 | Chrome-here isn't signed in, Brave has your session. ToS acceptance + scope grant. |
| 4 | **X API — decide budget** | 2 (decision) | Post-tier-abolition, X is pay-per-use. Tell me your per-month ceiling and I'll set rate limits in the publisher. |
| 5 | **Publisher agreement on Substack** | 2 | The "can publish" gate on Substack I walked you to; legal agreement. |
| 6 | **Paste first Substack post** | 10 | Draft waiting at `docs/first-substack-post.md`. Paste into the editor already pulled up in your browser, review, ship. |
| 7 | **sapphire-alpha — pick A/B/C** | 30 sec | I flagged 3 options for the stale Cloud Run service. Option B (retarget to tho-ai-agent project) is my recommendation — just confirm. |
| 8 | **Run `scripts/go_live.sh`** | 2 | Once the env vars from #1, #2, #3 are pasted into `.env.integrations`. The script chains chmod → load env → smoke → dry-run → live setenv → LaunchAgent load with confirmation gates. |

Total: ~30 minutes active time plus DNS propagation wait. Kadima DNS provider was Namecheap (resolved via `dig NS kadima.digital`), so the old "tell me where" question is gone.

---

## Exact paste strings (have these ready)

### Cloudflare

Once you click Create Token and copy the value:

```
CLOUDFLARE_API_TOKEN=<paste-the-token>
CLOUDFLARE_ACCOUNT_ID=75d6d9fd102b3f4f56a10a5a24005d68
```

### Resend (fill in as you go)

```
RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM_EMAIL=weekly@kadima.digital
RESEND_THO_DOMAIN=texashomeoutlet.com
RESEND_THO_FROM=hello@texashomeoutlet.com
```

### LinkedIn (after you create the app)

```
LINKEDIN_ACCESS_TOKEN=<60-day-token>
LINKEDIN_AUTHOR_URN=urn:li:person:<your-id>
```

### X (after you create credits account + regenerate tokens for write scope)

```
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_SECRET=
X_BEARER_TOKEN=
```

### Substack — leave blank

```
# Substack has no public post-by-email for standard accounts.
# Content engine will drop drafts in data/content/ready/; paste manually.
SUBSTACK_POST_EMAIL=
```

---

## Final flip sequence — just run one script

All 8 of the commands below are now wrapped in `scripts/go_live.sh` with confirmation gates at the irreversible steps (flipping `SAPPHIRE_PUBLISH_LIVE=1` and the first live publish).

```bash
cd ~/Code/Sapphire
scripts/go_live.sh              # full sequence, stops for yes/no before going live
scripts/go_live.sh --dry-only   # stop after the dry-run preview (safe to run anytime)
scripts/go_live.sh --rollback   # flip LIVE=0 and unload the 6:15 AM LaunchAgent
```

What it does, in order:

1. `chmod 600 .env.integrations` (refuses to continue otherwise)
2. `scripts/load_integrations_env.sh` — push values into launchd GUI session
3. `scripts/smoke_integrations.py` — fail hard if any configured probe is red
4. `python3 -m lib.content.auto_publish --once --dry-run` — preview everything
5. **Prompt** → flip `SAPPHIRE_PUBLISH_LIVE=1`
6. **Prompt** → first live publish (`auto_publish --once`)
7. Install the 6:15 AM CT LaunchAgent (`com.sapphire.content-publisher.plist`)

If step 3 or 4 fails, the script aborts before touching anything live. If you bail at either confirmation, nothing has been flipped — safe to re-run.

---

## What I did while you were away

- Renamed Substack publication: "ari's Substack" → **Agent Dev** with the tagline *"Field notes from building Sapphire — autonomous trading, on-chain intelligence, and agent-mesh telemetry."* Saved and live.
- Pre-filled the Cloudflare token creation form with the right name (`sapphire-tunnel-monitor`) and scopes (Account.Cloudflare Tunnel.Read + Zone.Read). You click through the last two screens.
- Confirmed Substack has no public post-by-email feature for standard accounts — updated `lib/content/publishers/substack.py` consumers and the handoff docs so we don't chase that anymore. Content pipeline stays manual-paste for Substack.
- Drafted the inaugural Substack post at `docs/first-substack-post.md` (~400 words, Agent Dev framing).
- Ran `smoke_integrations.py` baseline: 13 probes, 0 FAIL, 13 SKIP (all waiting on creds). No spurious errors — test scaffold is clean.
- Audited `com.sapphire.content-publisher.plist` — dry-run by default, 6:15 AM CT, logs to `~/Library/Logs/sapphire/`.
- Cleaned up `.env.integrations.example`: corrected Substack comments, inlined your Cloudflare account ID + exact scope names.
- Resolved the Kadima DNS provider mystery: `dig NS kadima.digital` → `dns{1,2}.registrar-servers.com` = **Namecheap**. Updated the handoff doc with the exact Namecheap Advanced DNS steps and host-name conventions for the Resend records.
- Wrote `scripts/go_live.sh` — one script chains all 8 flip-live commands with yes/no gates at the irreversible ones. Run `go_live.sh --dry-only` first to confirm everything previews cleanly, then `go_live.sh` for the full live flip. `--rollback` undoes it.
- Re-ran the smoke test baseline: still clean (13 probes, 0 FAIL, 13 SKIP, gcloud SKIP is expected when not running under your user).

---

## Open decisions I punted to you

1. ~~**Kadima DNS provider**~~ — resolved: Namecheap. Advanced DNS panel is linked in row #2 of the priority queue above.
2. **X budget ceiling** (pay-per-use consumption).
3. **sapphire-alpha Cloud Run service** — retarget to `tho-ai-agent` (B), delete (A), or retire entirely (C). Recommendation: B.
4. **LinkedIn scope** — personal (`w_member_social`) or Kadima Digital company page (`w_organization_social`). I'd do personal first, add company once you have 5+ posts that would have gone there.

---

## Files you'll want to look at

- [docs/ari-handoff-checklist.md](./ari-handoff-checklist.md) — per-integration walk-through (§1-§8)
- [docs/integrations-status-2026-04-18.md](./integrations-status-2026-04-18.md) — set-up / partial / blocked matrix
- [docs/first-substack-post.md](./first-substack-post.md) — inaugural post draft
- [.env.integrations.example](../.env.integrations.example) — paste-ready template with comments
- [scripts/smoke_integrations.py](../scripts/smoke_integrations.py) — baseline check, exits 0 if all configured-probes pass
- [scripts/load_integrations_env.sh](../scripts/load_integrations_env.sh) — env → launchd bridge
- [scripts/go_live.sh](../scripts/go_live.sh) — one-shot flip-live sequence with safety gates and `--rollback`
