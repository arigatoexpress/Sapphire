# Complete Migration Instructions - Frontend Disconnection

## 🎯 Objective
Ensure the frontend website is completely disconnected from the old `sapphireinfinite` project and only uses the new `sapphireinfinite` project.

## ✅ Current Status

### Verified ✅
- Firebase project: `sapphireinfinite` (correct)
- Firebase config: Using new project ID
- API endpoint: `api.sapphiretrade.xyz` (correct)
- Source code: No old project references
- Build files: No old project references

### ⚠️ Issue Found
- **Content-Security-Policy header** contains old Cloud Run URLs:
  - `https://cloud-trader-342943608894.us-central1.run.app`
  - `https://cloud-trader-cfxefrvooa-uc.a.run.app`

## 🔧 Fix Instructions

### Step 1: Update firebase.json (DONE)
The `firebase.json` has been updated to include a CSP header that only allows connections to:
- `https://api.sapphiretrade.xyz`
- `https://trader.sapphiretrade.xyz`
- Firebase domains

**File**: `trading-dashboard/firebase.json` ✅ Updated

### Step 2: Rebuild Frontend
```bash
cd trading-dashboard

# Clean previous build
rm -rf dist

# Build with latest configuration
npm run build

# Verify build
ls -la dist/
```

### Step 3: Redeploy to Firebase
```bash
cd trading-dashboard

# Verify you're using correct project
firebase use
# Should show: sapphireinfinite

# Deploy to Firebase hosting
firebase deploy --only hosting --project=sapphireinfinite

# Verify deployment
firebase hosting:channel:list --project=sapphireinfinite
```

### Step 4: Verify Deployment
```bash
# Test frontend
curl -I https://sapphiretrade.xyz

# Check CSP header (should NOT contain old URLs)
curl -sI https://sapphiretrade.xyz | grep -i "content-security-policy"

# Should only show: api.sapphiretrade.xyz and Firebase domains
```

### Step 5: Test in Browser
1. Open https://sapphiretrade.xyz in browser
2. Open Developer Tools (F12)
3. Go to Network tab
4. Refresh page
5. Verify all API calls go to `api.sapphiretrade.xyz`
6. Check Console for any errors
7. Verify no requests to old Cloud Run URLs

## 🛡️ Additional Safeguards

### 1. Remove Old Project from Firebase CLI (Optional)
```bash
# This prevents accidental deployment to old project
# Note: This doesn't delete the project, just removes it from local config
firebase projects:remove sapphireinfinite
```

### 2. Set Explicit Default Project
```bash
cd trading-dashboard
firebase use sapphireinfinite --add
firebase use sapphireinfinite
```

### 3. Verify No Environment Variables Override
```bash
cd trading-dashboard

# Check for .env files
ls -la .env* 2>/dev/null || echo "No .env files found"

# If .env files exist, check they don't reference old project
cat .env.local 2>/dev/null | grep -i "342943608894\|quant-ai-trader" || echo "No old project references"
```

### 4. Check DNS Routing
```bash
# Verify DNS points to correct infrastructure
nslookup sapphiretrade.xyz

# Should resolve to Firebase hosting or your load balancer
# NOT to old project resources
```

## 📋 Verification Checklist

After completing the steps above, verify:

- [ ] `firebase use` shows `sapphireinfinite`
- [ ] `.firebaserc` only references `sapphireinfinite`
- [ ] Frontend builds without errors
- [ ] Deployment succeeds to `sapphireinfinite`
- [ ] CSP header only contains new project URLs
- [ ] Browser console shows no errors
- [ ] All API calls go to `api.sapphiretrade.xyz`
- [ ] No requests to old Cloud Run URLs
- [ ] Dashboard loads and displays data correctly

## 🚨 If Issues Persist

### If CSP header still shows old URLs:
1. Clear Firebase hosting cache (may take a few minutes)
2. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
3. Check if load balancer is adding CSP header (check GCP Console)

### If frontend still connects to old project:
1. Check browser cache - clear completely
2. Verify DNS is correct: `nslookup sapphiretrade.xyz`
3. Check if there's a CDN or proxy in front adding headers
4. Verify Firebase hosting is actually serving the new deployment

### If API calls fail:
1. Verify API endpoint: `curl https://api.sapphiretrade.xyz/healthz`
2. Check CORS configuration on backend
3. Verify SSL certificate is active
4. Check browser console for specific error messages

## 📝 Summary

**Status**: ✅ Configuration is correct, just needs rebuild and redeploy

**Action Required**:
1. ✅ `firebase.json` updated (CSP header fixed)
2. ⏳ Rebuild frontend (`npm run build`)
3. ⏳ Redeploy to Firebase (`firebase deploy --only hosting`)
4. ⏳ Verify CSP header no longer contains old URLs

**Expected Result**: Frontend will only connect to `api.sapphiretrade.xyz` and Firebase services, completely disconnected from old project.

