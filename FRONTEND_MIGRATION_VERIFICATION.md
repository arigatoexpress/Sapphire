# Frontend Migration Verification & Disconnection Instructions

## ✅ Current Frontend Status

### Firebase Configuration
- **Firebase Project**: `sapphireinfinite` ✅
- **Firebase Site**: `sapphireinfinite` ✅
- **API Endpoint**: `https://api.sapphiretrade.xyz` ✅
- **Firebase Config**: Using new project ID and credentials ✅

### Frontend Code
- **API Base URL**: `https://api.sapphiretrade.xyz` (hardcoded in `TradingContext.tsx`)
- **Firebase Config**: `sapphireinfinite` project (in `firebase.ts`)
- **No old project references** in frontend code ✅

## ⚠️ Potential Issues

### 1. Old Firebase Project Still Exists
The old project `quant-ai-trader-credits` (342943608894) still exists in your Firebase projects list.

**Risk**: If you accidentally deploy to the old project, the frontend could be served from there.

### 2. DNS Routing
Verify that `sapphiretrade.xyz` is pointing to the correct Firebase hosting or load balancer.

## 🔍 Verification Steps

### Step 1: Verify Current Firebase Deployment
```bash
cd trading-dashboard

# Check which project is active
firebase use

# Should show: sapphireinfinite

# List hosting sites
firebase hosting:sites:list --project=sapphireinfinite

# Check current deployment
firebase hosting:channel:list --project=sapphireinfinite
```

### Step 2: Verify Frontend is Using Correct API
```bash
# Check the built frontend code
cd trading-dashboard/dist
grep -r "api.sapphiretrade.xyz" . || echo "No API references found in build"

# Check for old project references
grep -r "342943608894\|quant-ai-trader" . || echo "No old project references found"
```

### Step 3: Test Frontend Endpoints
```bash
# Test main domain
curl -I https://sapphiretrade.xyz

# Test Firebase default domain
curl -I https://sapphireinfinite.web.app

# Test API endpoint
curl -I https://api.sapphiretrade.xyz/healthz
```

### Step 4: Check DNS Configuration
```bash
# Check DNS for main domain
nslookup sapphiretrade.xyz

# Should point to Firebase hosting IP or your load balancer
```

## 🛡️ Instructions to Ensure Complete Disconnection

### 1. Set Firebase Default Project (CRITICAL)
```bash
cd trading-dashboard

# Explicitly set the default project
firebase use sapphireinfinite

# Verify it's set
firebase use

# Should output: "Now using project sapphireinfinite"
```

### 2. Remove Old Project from Firebase CLI (Optional but Recommended)
```bash
# List all projects
firebase projects:list

# Remove old project from local config (doesn't delete the project)
# This prevents accidental deployment to old project
firebase projects:remove sapphireinfinite
```

### 3. Verify .firebaserc Configuration
The `.firebaserc` file should only reference `sapphireinfinite`:
```json
{
  "projects": {
    "default": "sapphireinfinite"
  },
  "targets": {
    "sapphireinfinite": {
      "hosting": {
        "sapphire-prod": [
          "sapphireinfinite"
        ]
      }
    }
  }
}
```

### 4. Rebuild and Redeploy Frontend (Recommended)
To ensure the frontend is using the latest configuration:

```bash
cd trading-dashboard

# Clean build
rm -rf dist node_modules/.vite

# Install dependencies
npm install

# Build with explicit API URL
VITE_API_BASE_URL=https://api.sapphiretrade.xyz npm run build

# Verify build
ls -la dist/

# Deploy to Firebase (will use sapphireinfinite project)
firebase deploy --only hosting --project=sapphireinfinite

# Verify deployment
firebase hosting:channel:list --project=sapphireinfinite
```

### 5. Verify Environment Variables
Check for any `.env` files that might override settings:

```bash
cd trading-dashboard

# Check for .env files
ls -la .env* 2>/dev/null || echo "No .env files found"

# If .env files exist, verify they use new project
cat .env.local 2>/dev/null | grep -i "api\|firebase\|project" || echo "No relevant vars"
```

### 6. Check Browser Console for Errors
1. Open https://sapphiretrade.xyz in browser
2. Open Developer Tools (F12)
3. Check Console for any errors
4. Check Network tab - verify all API calls go to `api.sapphiretrade.xyz`
5. Look for any references to old project URLs

### 7. Verify DNS Routing
```bash
# Check DNS for main domain
dig +short sapphiretrade.xyz

# Should resolve to Firebase hosting or your load balancer IP
# NOT to old project resources
```

### 8. Test API Connectivity from Frontend
1. Visit https://sapphiretrade.xyz
2. Open browser console
3. Run: `fetch('https://api.sapphiretrade.xyz/healthz').then(r => r.json()).then(console.log)`
4. Should return health status from new project

## 🚨 Critical Checks Before Going Live

### Pre-Deployment Checklist
- [ ] `firebase use` shows `sapphireinfinite`
- [ ] `.firebaserc` only references `sapphireinfinite`
- [ ] No `.env` files with old project references
- [ ] Built frontend uses `api.sapphiretrade.xyz`
- [ ] DNS points to correct infrastructure
- [ ] Browser console shows no errors
- [ ] API calls go to `api.sapphiretrade.xyz`

### Post-Deployment Verification
- [ ] Frontend loads at https://sapphiretrade.xyz
- [ ] API calls succeed (check Network tab)
- [ ] No 404s or CORS errors
- [ ] Dashboard shows real data
- [ ] No references to old project in network requests

## 🔧 Troubleshooting

### If Frontend Still Points to Old Project

1. **Clear Browser Cache**
   ```bash
   # Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
   # Or clear cache in browser settings
   ```

2. **Check Firebase Hosting**
   ```bash
   firebase hosting:channel:list --project=sapphireinfinite
   # Verify latest deployment is to sapphireinfinite
   ```

3. **Force Redeploy**
   ```bash
   cd trading-dashboard
   firebase deploy --only hosting --project=sapphireinfinite --force
   ```

4. **Check DNS Cache**
   ```bash
   # Clear local DNS cache
   sudo dscacheutil -flushcache  # macOS
   # or
   sudo systemd-resolve --flush-caches  # Linux
   ```

### If API Calls Fail

1. **Verify API Endpoint**
   ```bash
   curl https://api.sapphiretrade.xyz/healthz
   # Should return JSON with status
   ```

2. **Check CORS Configuration**
   - Verify backend allows requests from `https://sapphiretrade.xyz`
   - Check browser console for CORS errors

3. **Verify SSL Certificate**
   ```bash
   kubectl get managedcertificate -n trading cloud-trader-cert
   # Should show Active status
   ```

## 📝 Summary

**Current Status**: ✅ Frontend is configured for new project
**Action Required**: Verify deployment and test connectivity
**Risk Level**: Low (configuration is correct, just need verification)

**Next Steps**:
1. Run verification steps above
2. Rebuild and redeploy if needed
3. Test in browser
4. Monitor for any issues

