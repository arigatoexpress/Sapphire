# SAPPHIRE Deployment Troubleshooting Summary

## Issues Identified & Fixed

### ✅ Issue 1: Pod Scheduling (FIXED)
**Problem**: 10 pods running, 1 stuck in Pending due to insufficient CPU
**Solution**: Scaled deployment from 10 to 2 replicas (matching YAML config)
**Status**: ✅ Fixed - 2 pods running, 0 pending

### ✅ Issue 2: DNS Mismatch (FIXED - Propagation Pending)
**Problem**: DNS pointed to `34.135.133.129` (LoadBalancer IP) but Ingress uses static IP `34.144.213.188`
**Solution**: Updated Cloud DNS A record to point to static IP `34.144.213.188`
**Status**: ⏳ DNS change applied, waiting for propagation (5-15 minutes)

### ⏳ Issue 3: SSL Certificate (WAITING FOR DNS PROPAGATION)
**Problem**: Certificate stuck in "Provisioning" with "FailedNotVisible" status
**Root Cause**: DNS mismatch prevented certificate authority from verifying domain ownership
**Solution**: DNS updated, certificate will auto-retry once DNS propagates
**Status**: ⏳ Waiting for DNS propagation, then certificate should activate automatically

## Current State

- **Pods**: 2/2 running ✅
- **Deployment**: Scaled to 2 replicas ✅
- **LoadBalancer**: `34.135.133.129` (service IP)
- **Static IP**: `34.144.213.188` (ingress IP)
- **DNS**: Updated to point to static IP (propagating)
- **SSL Certificate**: Provisioning (will activate after DNS propagation)

## Monitoring Commands

### Check DNS Propagation
```bash
# Should show 34.144.213.188 after propagation
nslookup api.sapphiretrade.xyz
dig +short api.sapphiretrade.xyz
```

### Check Certificate Status
```bash
kubectl get managedcertificate -n trading cloud-trader-cert
kubectl describe managedcertificate -n trading cloud-trader-cert
```

### Check Ingress Status
```bash
kubectl get ingress -n trading cloud-trader-ingress
kubectl describe ingress -n trading cloud-trader-ingress
```

### Quick Status Check
```bash
./check_deployment_status.sh
```

## Expected Timeline

1. **DNS Propagation**: 5-15 minutes (varies by DNS provider cache)
2. **Certificate Verification**: 10-30 minutes after DNS propagates
3. **Ingress Address Assignment**: Should appear once certificate is Active

## Next Steps

1. **Wait 10-15 minutes** for DNS propagation
2. **Verify DNS** points to `34.144.213.188`:
   ```bash
   dig +short api.sapphiretrade.xyz
   ```
3. **Monitor certificate** status:
   ```bash
   watch -n 30 'kubectl get managedcertificate -n trading cloud-trader-cert'
   ```
4. **Once certificate is Active**, the ingress should get an address and HTTPS will work

## Troubleshooting Scripts

- `troubleshoot_deployment.sh` - Comprehensive troubleshooting analysis
- `check_deployment_status.sh` - Quick status check

## Notes

- The LoadBalancer service IP (`34.135.133.129`) is different from the Ingress static IP (`34.144.213.188`)
- This is normal - the Ingress uses a static IP for stability, while the service LoadBalancer gets a dynamic IP
- DNS must point to the Ingress static IP for SSL certificates to work
- The certificate will automatically retry verification once DNS propagates

