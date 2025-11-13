# Frontend Troubleshooting Guide

## ✅ Deployment Status

- **Site**: https://sapphireinfinite.web.app
- **Status**: Deployed and accessible (HTTP 200)
- **Assets**: All JavaScript and CSS files are accessible
- **HTML**: Correct structure with root div

## 🔍 If You See a Blank Page

### Step 1: Hard Refresh Browser
- **Windows/Linux**: `Ctrl + Shift + R`
- **Mac**: `Cmd + Shift + R`
- **Or**: `Ctrl + F5` (Windows) / `Cmd + R` (Mac)

### Step 2: Clear Browser Cache
1. Open Developer Tools (F12)
2. Right-click the refresh button
3. Select "Empty Cache and Hard Reload"

### Step 3: Check Browser Console
1. Open Developer Tools (F12)
2. Go to "Console" tab
3. Look for red error messages
4. Common issues:
   - **CORS errors**: API endpoint not accessible
   - **404 errors**: Missing assets
   - **Network errors**: API connection failed

### Step 4: Try Incognito/Private Mode
- This bypasses cache and extensions
- If it works in incognito, it's a cache/extension issue

### Step 5: Check Network Tab
1. Open Developer Tools (F12)
2. Go to "Network" tab
3. Refresh the page
4. Check if all files load (green = success, red = failed)
5. Look for failed requests to:
   - `/assets/index-*.js`
   - `/assets/vendor-*.js`
   - `https://api.sapphiretrade.xyz/*`

## 🔧 Common Issues

### Issue 1: API Endpoint Not Responding
**Symptom**: Blank page, console shows API errors

**Check**:
```bash
curl https://api.sapphiretrade.xyz/healthz
```

**Solution**: 
- API endpoint may not be active yet (SSL certificate provisioning)
- Wait for SSL certificate to activate
- Or use Firebase default domain temporarily

### Issue 2: CORS Errors
**Symptom**: Console shows CORS policy errors

**Solution**: 
- Check if API endpoint allows requests from `sapphireinfinite.web.app`
- Verify CSP headers are correct

### Issue 3: JavaScript Errors
**Symptom**: Console shows JavaScript errors

**Check**:
- Open Console tab in Developer Tools
- Look for red error messages
- Check if error mentions specific files or functions

### Issue 4: Old Cached Version
**Symptom**: Old UI or features missing

**Solution**:
- Hard refresh (Ctrl+Shift+R)
- Clear browser cache completely
- Wait 5-10 minutes for CDN cache to clear

## 🧪 Quick Tests

### Test 1: Check if HTML loads
```bash
curl https://sapphireinfinite.web.app
# Should show HTML with <div id="root"></div>
```

### Test 2: Check if JavaScript loads
```bash
curl -I https://sapphireinfinite.web.app/assets/index-857589d0.js
# Should return HTTP 200
```

### Test 3: Check API endpoint
```bash
curl https://api.sapphiretrade.xyz/healthz
# Should return JSON (may fail if SSL not active)
```

## 📋 What to Check in Browser

1. **Console Tab**:
   - Any red errors?
   - Any warnings about missing files?

2. **Network Tab**:
   - Are all files loading (status 200)?
   - Any failed requests (status 4xx/5xx)?

3. **Application Tab**:
   - Check if service worker is registered
   - Check if localStorage has data

4. **Elements Tab**:
   - Is `<div id="root"></div>` present?
   - Is it empty or does it have content?

## 🚀 Quick Fixes

### Fix 1: Force Clear Cache
1. Open Developer Tools (F12)
2. Go to Application tab
3. Click "Clear storage"
4. Check all boxes
5. Click "Clear site data"
6. Refresh page

### Fix 2: Disable Service Worker
1. Open Developer Tools (F12)
2. Go to Application tab
3. Click "Service Workers"
4. Click "Unregister" if any are registered
5. Refresh page

### Fix 3: Check API Connection
If the API is not responding, the app may show a blank page. Check:
- Is `https://api.sapphiretrade.xyz` accessible?
- Is SSL certificate active?
- Are there CORS issues?

## 📞 Next Steps

If none of these work:
1. Share a screenshot of the browser console
2. Share any error messages
3. Check if the API endpoint is accessible
4. Try a different browser

---

**Current Status**: Site is deployed and technically working. If you see a blank page, it's likely a browser cache issue or API connectivity problem.

