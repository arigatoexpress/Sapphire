# How to Add sapphiretrade.xyz to Firebase Hosting

## Issue

The frontend is deployed and working at `sapphireinfinite.web.app`, but `sapphiretrade.xyz` is not configured as a custom domain in Firebase Hosting.

## Solution: Add Custom Domain via Firebase Console

### Step 1: Open Firebase Console
1. Go to: https://console.firebase.google.com/project/sapphireinfinite/hosting
2. Click on the "Hosting" section in the left sidebar

### Step 2: Add Custom Domain
1. Click the "Add custom domain" button (or "Connect domain")
2. Enter: `sapphiretrade.xyz`
3. Click "Continue"

### Step 3: Verify Domain Ownership
Firebase will provide verification steps. You may need to:
- Add a TXT record to your DNS
- Or verify via other methods Firebase provides

### Step 4: Update DNS Records
Firebase will provide specific DNS records to add. Typically:
- **A records** pointing to Firebase hosting IPs (already done - 199.36.158.100-103)
- **TXT record** for verification (if required)

### Step 5: Wait for Verification
- Firebase will verify domain ownership
- This usually takes a few minutes
- You'll see a green checkmark when verified

### Step 6: SSL Certificate
- Firebase automatically provisions SSL certificates
- This may take 10-30 minutes
- The site will be available at `https://sapphiretrade.xyz` once complete

## Current DNS Status

Your DNS is already configured correctly:
- A records: `199.36.158.100`, `199.36.158.101`, `199.36.158.102`, `199.36.158.103` ✅

## Alternative: Check if Domain is Already Added

If the domain was previously added, check:
1. Firebase Console → Hosting → Custom domains
2. Look for `sapphiretrade.xyz` in the list
3. Check its status (Active, Pending, etc.)

## Troubleshooting

### If DNS Resolution Shows Wrong IP
The DNS might be cached. Wait 10-30 minutes for propagation, or:
```bash
# Clear DNS cache (macOS)
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder

# Check DNS from different servers
dig +short sapphiretrade.xyz @8.8.8.8
dig +short sapphiretrade.xyz @1.1.1.1
```

### If Site Shows Old Content
1. Verify the latest deployment is live
2. Clear browser cache
3. Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)

## Quick Test

While waiting for custom domain setup, use:
- **Firebase default domain**: https://sapphireinfinite.web.app ✅ (works now)

## Expected Timeline

1. **Add domain in Firebase**: 2-5 minutes
2. **Domain verification**: 5-10 minutes
3. **SSL certificate**: 10-30 minutes
4. **DNS propagation**: 10-30 minutes (if needed)

**Total**: 30-60 minutes for full setup

---

**Next Step**: Go to Firebase Console and add `sapphiretrade.xyz` as a custom domain.

