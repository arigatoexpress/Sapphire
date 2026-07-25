# DNS for sapphirealpha.xyz

**The domain is on Google Cloud DNS, not Cloudflare.** This file was previously
`CLOUDFLARE_DNS_SETUP.md` and documented a Cloudflare setup that was never the
live configuration. Verified against production 2026-07-25.

## Authoritative zone — and the orphan

Two Cloud DNS managed zones both claim `sapphirealpha.xyz`. Only one is real.

| Project | Zone NS | Status |
|---|---|---|
| `sapphire-479610` | `ns-cloud-e1..e4.googledomains.com` | **Authoritative — edit here** |
| `tho-ai-agent` | `ns-cloud-c1..c4.googledomains.com` | **Orphaned — edits have no effect** |

The registrar delegates to the `e*` nameservers. Confirm before touching DNS:

```bash
dig +short sapphirealpha.xyz NS      # must return ns-cloud-e1..e4
```

Proof the `tho-ai-agent` zone is dead: `terminal.sapphirealpha.xyz` exists only
in that zone and does not resolve at all.

> **Trap:** writing records into the `tho-ai-agent` zone reports success and
> changes nothing. It also touches the fenced THO production project for no
> benefit. Always pass `--project=sapphire-479610` for this domain.

## Live records

Apex and `www` are the only names backed by a working Cloud Run domain mapping.

| Name | Type | Target | Backend | Status |
|---|---|---|---|---|
| `sapphirealpha.xyz` | A / AAAA | `216.239.3{2,4,6,8}.21` | `sapphire-alpha-dashboard` (`sapphire-479610`) | **live** |
| `www` | CNAME | `ghs.googlehosted.com.` | `sapphire-alpha-dashboard` | **live** |
| `tho` | CNAME | `ghs.googlehosted.com.` | `project-go-forward` (`tho-ai-agent`) | live — **retired, see below** |
| `gpu` | A | `34.29.235.86` | — | responds 401 |

### Dangling records

These resolve in DNS but have **no domain mapping**, so TLS fails and nothing
serves. They are safe to delete and must not be advertised:

`dashboard` · `gateway` · `pm` · `hack` · `regional` · `wildfire` ·
`delivery-markets` · `trading`

The earlier version of this file listed `dashboard` and `gateway` as
"✅ Active". Both are dead.

### `tho.sapphirealpha.xyz` is retired

THO's frontend was hosted here only during the testing phase, before
`texashomeoutlet.com` was available. That migration is complete — THO now serves
from `texashomeoutlet.com` and `www.texashomeoutlet.com`, both mapped to
`project-go-forward` in `tho-ai-agent`. The `tho.sapphirealpha.xyz` mapping is
leftover and is queued for removal in
`docs/ops/tho-project-sapphire-cleanup-runbook.md`.

## Adding a record

Always target the authoritative project:

```bash
gcloud dns record-sets create <name>.sapphirealpha.xyz. \
    --project=sapphire-479610 \
    --zone=sapphirealpha-xyz \
    --type=CNAME --ttl=300 \
    --rrdatas=ghs.googlehosted.com.
```

A CNAME alone is not enough — Cloud Run will not serve the name until a domain
mapping exists:

```bash
gcloud beta run domain-mappings create \
    --project=sapphire-479610 --region=us-central1 \
    --service=<service> --domain=<name>.sapphirealpha.xyz
```

Skipping the second step is exactly how the eight dangling records above were
created.

## Verifying

```bash
dig +short sapphirealpha.xyz A
gcloud beta run domain-mappings list --project=sapphire-479610 --region=us-central1
python3 scripts/ops/sapphirealpha_production_smoke.py    # 8 read-only probes
```

Certificate provisioning after a new mapping takes ~5-30 minutes; DNS
propagation at TTL 300 is ~1-5 minutes.

### IPv6 note

The apex publishes AAAA records. On networks that cannot route IPv6, browsers
preferring IPv6 may report the site unreachable while IPv4 is healthy. Force
IPv4 to confirm:

```bash
curl -4 https://sapphirealpha.xyz/api/v1/live
```

### Do not probe `/healthz`

Google Front End reserves that path on Cloud Run and intercepts it before the
container, so it returns 404 even though the route is registered. Use
`/api/health`, which exists specifically to work around this.

The backend also registers `/{catchall:path}` returning `index.html` at **HTTP
200**, so a dropped API route serves HTML at 200 rather than 404. Status-code
monitoring alone is blind to this — the smoke script sniffs `content-type`.
