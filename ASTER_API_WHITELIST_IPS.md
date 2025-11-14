# Aster DEX API Whitelist IPs

## Current IP Addresses to Whitelist

### Static/Global IPs
- **34.144.213.188** - Google Cloud static IP (`cloud-trader-ip`)
  - This is your reserved static IP for the trading system

### Load Balancer/Service IPs
- **34.49.212.244** - `api.sapphiretrade.xyz`
  - Main API endpoint for the trading system
- **34.117.165.111** - `trader.sapphiretrade.xyz`
  - Trading dashboard and agent services

### Cloud Run IP Range
- **34.143.72.0/29** - Cloud Run service range (`wallet-orchestrator`)
  - Individual IPs in range: `34.143.72.2` - `34.143.79.2`
  - Used for the wallet orchestrator service

## How to Whitelist

### For Aster DEX Dashboard:
1. Log into your Aster DEX account
2. Go to API Settings/Security
3. Add each IP address to the whitelist
4. For the Cloud Run range, you can either:
   - Add the CIDR range: `34.143.72.0/29`
   - Add individual IPs: `34.143.72.2, 34.143.73.2, 34.143.74.2, 34.143.75.2, 34.143.76.2, 34.143.77.2, 34.143.78.2, 34.143.79.2`

## Important Notes

### IP Address Changes
- **Static IP (34.144.213.188)**: Should remain stable unless you manually change it
- **Load Balancer IPs**: May change if you redeploy infrastructure or if Google rotates them
- **Cloud Run IPs**: These are Google's Cloud Run IP ranges and should be stable, but monitor for updates

### Monitoring IP Changes
To check if IPs have changed:
```bash
# Check current DNS resolution
dig api.sapphiretrade.xyz +short
dig trader.sapphiretrade.xyz +short

# Check Cloud Run service
dig wallet-orchestrator-880429861698.us-central1.run.app +short

# Check Google Cloud static IP
gcloud compute addresses list --global --project sapphireinfinite
```

### Security Considerations
- Only whitelist the minimum required IPs
- Regularly audit API access logs
- Consider using API key rotation
- Monitor for unauthorized access attempts

## Update Process

If you need to update these IPs in the future:

1. **Check current IPs** using the commands above
2. **Update Aster DEX whitelist** with new IPs
3. **Update this document** with new IP information
4. **Test API connectivity** after changes

## Emergency Contact

If you lose API access after an IP change:
- Check which IPs changed using the monitoring commands above
- Update the Aster DEX whitelist immediately
- Temporarily disable trading if needed
