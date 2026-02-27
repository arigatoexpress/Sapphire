# ✅ DNS Configuration Complete

## DNS Records Added via gcloud CLI

### Zone: `sapphirealpha-xyz`

| Record | Type | TTL | Value |
|--------|------|-----|-------|
| sapphirealpha.xyz | A | 300 | 216.239.32.21, 216.239.34.21, 216.239.36.21, 216.239.38.21 |
| sapphirealpha.xyz | AAAA | 300 | 2001:4860:4802:32::15, 2001:4860:4802:34::15, 2001:4860:4802:36::15, 2001:4860:4802:38::15 |
| dashboard.sapphirealpha.xyz | CNAME | 300 | ghs.googlehosted.com |
| gateway.sapphirealpha.xyz | CNAME | 300 | ghs.googlehosted.com |
| pm.sapphirealpha.xyz | CNAME | 300 | ghs.googlehosted.com |

## Cloud Run Domain Mappings

| Domain | Service | Certificate Status |
|--------|---------|-------------------|
| sapphirealpha.xyz | sapphire-command-deck | ⏳ Provisioning... |
| dashboard.sapphirealpha.xyz | sapphire-dashboard | ⏳ Provisioning... |
| gateway.sapphirealpha.xyz | sapphire-gateway | ✅ Active |
| pm.sapphirealpha.xyz | agentic-pm-hub | ✅ Active |

## Timeline

- DNS records: ✅ Added
- Certificate provisioning: ⏳ 5-30 minutes
- Expected live: ~15 minutes

## Verification Commands

```bash
# Check certificate status
gcloud beta run domain-mappings describe \
    --domain sapphirealpha.xyz \
    --region us-central1 \
    --project sapphire-479610

# Verify DNS
dig sapphirealpha.xyz A
dig dashboard.sapphirealpha.xyz CNAME
```

## Final URLs

Once certificates are ready:

| URL | Service |
|-----|---------|
| https://sapphirealpha.xyz | Command Deck v2.0 |
| https://dashboard.sapphirealpha.xyz | Legacy Dashboard |
| https://gateway.sapphirealpha.xyz | API Gateway |
| https://pm.sapphirealpha.xyz | PM Hub |
