# Resend DNS — Namecheap paste guide (for kadima.digital)

When you open Resend → Domains → `kadima.digital`, you'll see three DNS records to add. Two of them (**MX** and **SPF/TXT**) are deterministic because Resend uses Amazon SES in `us-east-1`; you can pre-fill those mentally before you even look at the dashboard. Only the **DKIM** CNAME value is unique per domain.

**Namecheap URL:** https://ap.www.namecheap.com/Domains/DomainControlPanel/kadima.digital/advancedns

For each row below: click **ADD NEW RECORD** at Namecheap, pick the Type, paste the Host and Value, set TTL to `Automatic`, hit the green checkmark.

Namecheap auto-appends `.kadima.digital` to whatever you put in the Host field — so you paste only the subdomain label (`send`, `resend._domainkey`, etc.), not the full FQDN.

---

## Record 1 — MX (priority 10)

| Field | Value |
|-------|-------|
| Type | `MX Record` |
| Host | `send` |
| Value (Mail Server) | `feedback-smtp.us-east-1.amazonses.com` |
| Priority | `10` |
| TTL | `Automatic` |

## Record 2 — SPF (TXT)

| Field | Value |
|-------|-------|
| Type | `TXT Record` |
| Host | `send` |
| Value | `v=spf1 include:amazonses.com ~all` |
| TTL | `Automatic` |

> **Heads-up:** If `kadima.digital` already has an SPF record at the root (i.e., a TXT with `v=spf1 ...` on the `@` host), leave it — this new one is on the `send` subdomain and doesn't collide. If you see the Resend dashboard warning about nested SPF, tell me and I'll reconcile.

## Record 3 — DKIM (CNAME)

This one is unique per domain. Resend will show you two values:

| Field | Value |
|-------|-------|
| Type | `CNAME Record` |
| Host | `resend._domainkey` *(or whatever prefix Resend shows — usually `resend._domainkey`)* |
| Value | `<copy from Resend dashboard>.dkim.amazonses.com` *(looks like `abc123def456.dkim.amazonses.com`)* |
| TTL | `Automatic` |

The DKIM value is a long hash followed by `.dkim.amazonses.com`. Copy it exactly from the Resend dashboard — Namecheap will auto-append a period for the FQDN canonicalization; don't add one yourself.

---

## After pasting all three

1. In Namecheap, you should see 3 new rows under Advanced DNS — `send` (MX, priority 10), `send` (TXT), `resend._domainkey` (CNAME).
2. Wait 10–30 minutes for Namecheap → global DNS propagation.
3. Back at Resend → Domains → `kadima.digital`, click **Verify Domain**. Resend will probe all three records and flip the status to **Verified** once DNS lookups resolve.
4. Once verified, run:
   ```bash
   cd ~/Code/Sapphire
   python3 scripts/smoke_integrations.py resend
   ```
   The probe note will change from *"sending-scoped key — verify domains in the Resend dashboard"* to *"verified: kadima.digital"* — that's the green light.

## If verification fails after 30 minutes

Check propagation directly:

```bash
dig MX send.kadima.digital +short       # expect: "10 feedback-smtp.us-east-1.amazonses.com."
dig TXT send.kadima.digital +short      # expect: "v=spf1 include:amazonses.com ~all"
dig CNAME resend._domainkey.kadima.digital +short   # expect: "<hash>.dkim.amazonses.com."
```

If any of those returns empty: the record isn't saved at Namecheap (check the green-checkmark state) or Namecheap hasn't published yet. If they return the correct values but Resend still shows unverified, it's a Resend-side delay — wait another 15 min and re-click **Verify**.

## Same pattern for texashomeoutlet.com

Repeat records 1–3 in the Namecheap control panel for `texashomeoutlet.com` (different URL — swap the domain in the Namecheap URL above). THO uses the same Resend account; each domain gets its own DKIM hash, the MX + SPF pattern is identical.

**Skip THO today if you want to keep the scope small** — `weekly@kadima.digital` is all the content engine needs to function. THO transactional email is a separate workflow we can light up later.
