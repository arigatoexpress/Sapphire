# Ari — when you get back

Single punch list of everything still gated on your click/tap. Ordered by time-to-value. Current as of 2026-04-18 evening.

---

## Status of the 8 integrations

| # | Integration | Status |
|---|-------------|--------|
| 1 | Cloudflare API token | ✅ **DONE** — token verified + saved to `.env.integrations`, account id `75d6d9fd102b3f4f56a10a5a24005d68` |
| 2 | Resend API key | ✅ **DONE** — sending-scoped key saved; smoke probe recognises it as PASS |
| 3 | Resend domain verification (`kadima.digital`) | ⏳ Gated on DNS paste at Namecheap — [`docs/resend-dns-paste-guide.md`](./resend-dns-paste-guide.md) has the exact values |
| 4 | Substack publisher agreement + first post | ⏳ Gated on you (ToS + paste) |
| 5 | X API budget + token regen | ⏳ Gated on you (dev console + budget decision) |
| 6 | LinkedIn org page + dev app | 🟡 **DEFERRED 7 days** — org creation hit LinkedIn's page-creation rate limit (anti-spam, ~2-3 pages/week). Earliest retry: **~April 25, 2026**. |
| 7 | On-chain providers (6) | ⏳ Optional — signups when you get to them |
| 8 | GCP / sapphire-alpha reconciliation | ⏳ Pick A/B/C — playbook ready at [`docs/sapphire-alpha-abc-playbook.md`](./sapphire-alpha-abc-playbook.md) |

---

## Priority queue — what to do next

| # | Task | Minutes | Why it's gated on you |
|---|------|---------|------------------------|
| 1 | **Paste Resend DNS at Namecheap** for `kadima.digital` (3 records) | 5 + DNS wait | Requires your Namecheap session. Guide: [`docs/resend-dns-paste-guide.md`](./resend-dns-paste-guide.md). Then click **Verify Domain** in Resend. |
| 2 | **Substack publisher agreement** | 2 | Legal agreement — click-through at the checkbox I walked you to. |
| 3 | **Paste first Substack post** | 10 | Draft at [`docs/first-substack-post.md`](./first-substack-post.md). Paste into the editor, review, ship. |
| 4 | **X — decide budget + regenerate tokens with write scope** | 5 | Pay-per-use post-tier-abolition. Tell me the per-month ceiling and I'll set publisher rate limits. When tokens are in hand, run [`scripts/finish_x_setup.sh`](../scripts/finish_x_setup.sh) — prompts you for the 5 values, writes them to `.env.integrations` in place, re-runs the smoke probe. |
| 5 | **sapphire-alpha — pick A/B/C** | 30 sec | One-line decision. Full playbook with exact commands: [`docs/sapphire-alpha-abc-playbook.md`](./sapphire-alpha-abc-playbook.md). Recommendation: **B** (retarget to `tho-ai-agent`). |
| 6 | **Run `scripts/go_live.sh`** | 2 | Once Resend DNS verifies + Substack agreement signed. Chains chmod → load env → smoke → dry-run → live setenv → LaunchAgent load with confirmation gates at the two irreversible steps. |
| 7 | **LinkedIn page + dev app** (when cooldown lifts ~April 25) | 15 | Try the org page again after 7 days. When token is in hand, run [`scripts/finish_linkedin_setup.sh`](../scripts/finish_linkedin_setup.sh) — prompts for the token, auto-extracts your author URN via `/v2/userinfo`, writes both vars. |

Total active time without LinkedIn: ~25 minutes + DNS propagation wait. LinkedIn adds ~15 minutes once the cooldown lifts.

---

## Exact paste strings (what still needs filling)

### Resend DNS records — ready to go

See [`docs/resend-dns-paste-guide.md`](./resend-dns-paste-guide.md) for the Namecheap-specific paste tables. Two of the three values are deterministic (Amazon SES `us-east-1`); only the DKIM hash comes from the Resend dashboard.

### X (when you regenerate tokens with Read+Write scope)

The `.env.integrations` already has placeholder lines for these — the finish-setup script will fill them:

```
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_SECRET=
X_BEARER_TOKEN=    # optional
```

Then: `scripts/finish_x_setup.sh` (hidden-input prompts, verifies bearer, writes in place, reloads launchd, re-runs smoke probe).

### LinkedIn (deferred 7 days, but here when you get there)

```
LINKEDIN_ACCESS_TOKEN=<60-day-token>
LINKEDIN_AUTHOR_URN=urn:li:person:<your-id>  # auto-filled by finish_linkedin_setup.sh
```

Then: `scripts/finish_linkedin_setup.sh`.

### Substack — leave blank

Standard Substack has no post-by-email for programmatic publishing. Content engine drops drafts in `data/content/ready/`; you paste them manually. No env var needed.

---

## Final flip sequence — one script

```bash
cd ~/Code/Sapphire
scripts/go_live.sh              # full sequence, stops for yes/no before going live
scripts/go_live.sh --dry-only   # stop after the dry-run preview (safe any time)
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

## What I did while you were away (2026-04-18 session)

**Verified live:**
- Cloudflare token you created: active, 0 tunnels, 0 zones (matches — Namecheap is DNS authoritative). Saved to `.env.integrations`.
- Resend API key: verified as sending-scoped (least-privilege, correct). Patched `probe_resend()` to recognise `restricted_api_key` 401 as PASS with a clear status note.

**Wrote:**
- [`docs/resend-dns-paste-guide.md`](./resend-dns-paste-guide.md) — Namecheap-specific paste tables for all 3 Resend records + dig verification commands. Two values pre-filled because SES is deterministic; only DKIM is unique.
- [`docs/sapphire-alpha-abc-playbook.md`](./sapphire-alpha-abc-playbook.md) — three one-command paths (delete, retarget to `tho-ai-agent`, enable billing on `sapphire-479610`). Each is ~5 lines of copy-pastable gcloud.
- [`scripts/go_live.sh`](../scripts/go_live.sh) — one-shot flip-live sequence with `--dry-only` and `--rollback` modes.
- [`scripts/finish_linkedin_setup.sh`](../scripts/finish_linkedin_setup.sh) — prompts for LinkedIn token, verifies via `/v2/userinfo`, extracts author URN, writes `.env.integrations` in place, reloads launchd, re-runs smoke probe.
- [`scripts/finish_x_setup.sh`](../scripts/finish_x_setup.sh) — same pattern for the OAuth 1.0a quartet + optional bearer.
- Five Kadima logo variants at [`docs/brand/`](./brand/): lemniscate-based marks (recursive, quadrilemniscate, 3-level fractal, golden-ratio concentric, lobe-ripples) + PNG renders at 64/300/800 + Gemini prompt variants + brand README. Primary mark: **kadima-mark-e-lobe-ripples.svg** (closest to the Gemini Variant C aesthetic you liked).

**Resolved / documented:**
- Kadima DNS provider = Namecheap (`dig NS kadima.digital` → `dns{1,2}.registrar-servers.com`).
- LinkedIn org page creation hit LinkedIn's 7-day rate limit — deferred, parked a retry reminder for ~April 25.
- Smoke baseline: 2 PASS (Cloudflare, Resend), remaining SKIP — all waiting on credentials, no spurious reds.

---

## Open decisions I punted to you

1. **X budget ceiling** (pay-per-use consumption model). Pick a per-month ceiling so I can set publisher rate limits.
2. **sapphire-alpha Cloud Run service** — pick A/B/C per the playbook. Recommendation: **B** (retarget to `tho-ai-agent`).
3. **LinkedIn scope** — personal (`w_member_social`) or Kadima Digital company page (`w_organization_social`). I'd do personal first after the cooldown, add company once you have 5+ posts that would have gone there.

---

## Files you'll want

- [docs/resend-dns-paste-guide.md](./resend-dns-paste-guide.md) — **new** — Namecheap paste steps
- [docs/sapphire-alpha-abc-playbook.md](./sapphire-alpha-abc-playbook.md) — **new** — A/B/C gcloud commands
- [docs/ari-handoff-checklist.md](./ari-handoff-checklist.md) — per-integration walk-through
- [docs/integrations-status-2026-04-18.md](./integrations-status-2026-04-18.md) — set-up / partial / blocked matrix
- [docs/first-substack-post.md](./first-substack-post.md) — inaugural post draft
- [docs/brand/](./brand/) — 5 logo variants + prompt file + README
- [.env.integrations.example](../.env.integrations.example) — paste-ready template with comments
- [scripts/smoke_integrations.py](../scripts/smoke_integrations.py) — baseline check
- [scripts/load_integrations_env.sh](../scripts/load_integrations_env.sh) — env → launchd bridge
- [scripts/go_live.sh](../scripts/go_live.sh) — one-shot flip-live with safety gates
- [scripts/finish_linkedin_setup.sh](../scripts/finish_linkedin_setup.sh) — **new** — post-token helper
- [scripts/finish_x_setup.sh](../scripts/finish_x_setup.sh) — **new** — post-token helper
