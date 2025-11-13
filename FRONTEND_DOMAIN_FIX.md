# Frontend Domain Fix - sapphiretrade.xyz

## Issue Identified

The frontend is not accessible at `sapphiretrade.xyz` because:

1. **DNS Mismatch**: 
   - DNS A records point to: `199.36.158.100-103` (Firebase hosting IPs)
   - Actual resolution shows: `136.110.138.66` (different IP - possibly old load balancer)

2. **Custom Domain Not Configured**:
   - `sapphiretrade.xyz` needs to be added as a custom domain in Firebase Hosting
   - Currently only `sapphireinfinite.web.app` is configured

3. **Old Content Being Served**:
   - Site is responding but with old content (last-modified: Nov 11)
   - Old CSP headers with old Cloud Run URLs

## Solution

### Option 1: Add Custom Domain to Firebase (Recommended)

1. **Via Firebase Console**:
   - Go to: https://console.firebase.google.com/project/sapphireinfinite/hosting
   - Click "Add custom domain"
   - Enter: `sapphiretrade.xyz`
   - Follow the verification steps
   - Update DNS records as instructed

2. **Via CLI** (if supported):
   ```bash
   firebase hosting:channel:create live --project=sapphireinfinite
   # Then add custom domain via console
   ```

### Option 2: Update DNS to Point Directly to Firebase

If Firebase provides specific IPs for custom domains, update DNS:

```bash
# Get Firebase hosting IPs
dig +short sapphireinfinite.web.app

# Update DNS A records to match Firebase hosting IPs
# (Firebase will provide specific IPs when you add custom domain)
```

### Option 3: Use Load Balancer (Current Setup)

If using the load balancer setup:
- The load balancer should route `sapphiretrade.xyz` to Firebase hosting
- Check if `sapphire-frontend-backend-bucket` exists and is configured correctly
- Verify the URL map is routing correctly

## Current Status

- ✅ Firebase default domain works: `sapphireinfinite.web.app`
- ✅ Frontend deployed successfully
- ❌ Custom domain `sapphiretrade.xyz` not configured in Firebase
- ⚠️ DNS pointing to wrong IP or old configuration

## Next Steps

1. **Add custom domain in Firebase Console**:
   - Go to Firebase Hosting
   - Add `sapphiretrade.xyz` as custom domain
   - Follow verification steps

2. **Update DNS records** as instructed by Firebase

3. **Wait for DNS propagation** (10-30 minutes)

4. **Verify**:
   ```bash
   curl -I https://sapphiretrade.xyz
   # Should show new content and correct CSP headers
   ```

## Quick Fix

**Temporary**: Use Firebase default domain:
- https://sapphireinfinite.web.app ✅ (works now)

**Permanent**: Add custom domain via Firebase Console

