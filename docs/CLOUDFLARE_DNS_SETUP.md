# Cloudflare DNS Setup for sapphirealpha.xyz

## Current Domain Mappings

| Domain | Service | Status |
|--------|---------|--------|
| `sapphirealpha.xyz` | sapphire-command-deck | ⏳ Pending DNS |
| `dashboard.sapphirealpha.xyz` | sapphire-dashboard | ✅ Active |
| `gateway.sapphirealpha.xyz` | sapphire-gateway | ✅ Active |
| `pm.sapphirealpha.xyz` | agentic-pm-hub | ⚠️ Stale mapping; service not present in `sapphire-479610` |

`pm.sapphirealpha.xyz` should not be advertised as a live public Sapphire
surface until the domain mapping is remapped or removed through a dedicated
rollback-reviewed infrastructure change. The protected historical
`agentic-pm-hub` service belongs to the separate AgenticArigato/THO-adjacent
lane and must not be changed from this Sapphire DNS checklist.

---

## Cloudflare DNS Configuration

If you're using Cloudflare (recommended for SSL + caching), add these records:

### 1. Root Domain (sapphirealpha.xyz) → Command Deck

```
Type: A
Name: @
IPv4 address: 216.239.32.21
Proxy status: DNS only (gray cloud) ⚠️ IMPORTANT
TTL: Auto
```

```
Type: A
Name: @
IPv4 address: 216.239.34.21
Proxy status: DNS only (gray cloud)
TTL: Auto
```

```
Type: A
Name: @
IPv4 address: 216.239.36.21
Proxy status: DNS only (gray cloud)
TTL: Auto
```

```
Type: A
Name: @
IPv4 address: 216.239.38.21
Proxy status: DNS only (gray cloud)
TTL: Auto
```

### 2. Dashboard Subdomain

```
Type: CNAME
Name: dashboard
Target: ghs.googlehosted.com
Proxy status: DNS only (gray cloud)
TTL: Auto
```

---

## ⚠️ CRITICAL: Disable Cloudflare Proxy

For Cloud Run custom domains, you MUST disable the Cloudflare proxy (orange cloud) initially:

1. Click the orange cloud icon next to each record
2. It should turn gray ("DNS only")
3. Wait for SSL certificate provisioning (5-30 minutes)
4. After certificate is active, you can re-enable the proxy if desired

---

## Verification Steps

After adding DNS records:

```bash
# Check DNS propagation
dig sapphirealpha.xyz A
dig sapphirealpha.xyz AAAA

# Check certificate status
gcloud beta run domain-mappings describe \
    --domain sapphirealpha.xyz \
    --region us-central1 \
    --project sapphire-479610
```

---

## Troubleshooting

### Certificate Not Provisioning

1. Ensure DNS records are correct
2. Ensure proxy is disabled (gray cloud)
3. Wait up to 60 minutes
4. Check Cloud Run domain mapping status

### SSL Errors After Proxy Enable

If you re-enable Cloudflare proxy (orange cloud) after certificate provisioning:

1. SSL mode should be "Full (strict)" in Cloudflare
2. Or keep it "DNS only" and let Google manage SSL

---

## Expected Timeline

| Step | Time |
|------|------|
| DNS propagation | 1-5 minutes |
| Certificate provisioning | 5-30 minutes |
| Total time to live | ~30 minutes |

---

## URLs After Setup

| URL | What |
|-----|------|
| https://sapphirealpha.xyz | Command Deck v2.0 (NEW) |
| https://dashboard.sapphirealpha.xyz | Old Dashboard |
| https://gateway.sapphirealpha.xyz | API Gateway |
| https://pm.sapphirealpha.xyz | Stale domain mapping; do not advertise as live |

---

## Quick Commands

```bash
# Check domain status
gcloud beta run domain-mappings list --project sapphire-479610

# View certificate details
gcloud beta run domain-mappings describe \
    --domain sapphirealpha.xyz \
    --region us-central1 \
    --project sapphire-479610
```
