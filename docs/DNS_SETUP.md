# DNS Setup for sapphirealpha.xyz

## Domain Registrar
Your domain uses **Google Domains** (now Squarespace) name servers.

## DNS Records to Add

Log into your [Google Domains](https://domains.google.com) or [Squarespace Domains](https://account.squarespace.com/domains) account and add these DNS records:

### A Records (Root Domain → Command Deck)

| Type | Host | Value | TTL |
|------|------|-------|-----|
| A | @ | 216.239.32.21 | 1 hour |
| A | @ | 216.239.34.21 | 1 hour |
| A | @ | 216.239.36.21 | 1 hour |
| A | @ | 216.239.38.21 | 1 hour |

### AAAA Records (IPv6 - Optional but recommended)

| Type | Host | Value | TTL |
|------|------|-------|-----|
| AAAA | @ | 2001:4860:4802:32::15 | 1 hour |
| AAAA | @ | 2001:4860:4802:34::15 | 1 hour |
| AAAA | @ | 2001:4860:4802:36::15 | 1 hour |
| AAAA | @ | 2001:4860:4802:38::15 | 1 hour |

### CNAME Record (Dashboard Subdomain)

| Type | Host | Value | TTL |
|------|------|-------|-----|
| CNAME | dashboard | ghs.googlehosted.com | 1 hour |

---

## Step-by-Step Instructions

### For Google Domains:

1. Go to [Google Domains](https://domains.google.com)
2. Click on **sapphirealpha.xyz**
3. Click **DNS** in the left menu
4. Scroll to **Custom resource records**
5. Add the A and CNAME records above
6. Click **Save**

### For Squarespace (if migrated):

1. Go to [Squarespace Domains](https://account.squarespace.com/domains)
2. Click on **sapphirealpha.xyz**
3. Click **DNS Settings**
4. Click **Add Record**
5. Add each A and CNAME record
6. Click **Save**

---

## Verification

After adding records, verify with:

```bash
# Check A records
dig sapphirealpha.xyz A

# Should return:
# 216.239.32.21
# 216.239.34.21
# 216.239.36.21
# 216.239.38.21

# Check CNAME
dig dashboard.sapphirealpha.xyz CNAME

# Should return:
# ghs.googlehosted.com
```

---

## Certificate Provisioning

After DNS is configured:

1. Google will automatically detect the DNS changes
2. SSL certificate provisioning begins (5-30 minutes)
3. Check status:

```bash
gcloud beta run domain-mappings describe \
    --domain sapphirealpha.xyz \
    --region us-central1 \
    --project sapphire-479610
```

Look for:
- `type: CertificateProvisioned` → status: 'True'
- `type: Ready` → status: 'True'

---

## Final URLs

| URL | Service | Status |
|-----|---------|--------|
| https://sapphirealpha.xyz | Command Deck v2.0 | 🆕 |
| https://dashboard.sapphirealpha.xyz | Old Dashboard | 🔄 |
| https://gateway.sapphirealpha.xyz | API Gateway | ✅ |
| https://pm.sapphirealpha.xyz | PM Hub | ✅ |

---

## Troubleshooting

### "CertificatePending" for >1 hour?

1. Double-check DNS records match exactly
2. Ensure no conflicting records
3. Try flushing DNS cache: `sudo killall -HUP mDNSResponder`

### Domain not resolving?

DNS propagation can take up to 24 hours, but usually happens in minutes with Google Domains.

---

## Support

If issues persist:
1. Check [Cloud Run Domain Mapping docs](https://cloud.google.com/run/docs/mapping-custom-domains)
2. Verify in [Google Cloud Console](https://console.cloud.google.com/run/domains)
