# Deploy After Adding Web App

## Current Status

⏳ **Waiting for**: Web app to be added in Firebase Console  
⏳ **Waiting for**: Project to sync with Firebase CLI

## Steps You're Doing Now

1. ✅ Adding web app in Firebase Console
2. ✅ Checking "Also set up Firebase Hosting"
3. ⏳ Registering the app

## After You Add the Web App

### Step 1: Wait for Sync (1-2 minutes)
After adding the web app, wait 1-2 minutes for the project to sync with Firebase CLI.

### Step 2: Check if Project Appears
```bash
cd trading-dashboard
firebase projects:list
# Should show sapphire-22470816
```

### Step 3: Switch to New Project
```bash
firebase use sapphire-22470816
```

### Step 4: Deploy
```bash
firebase deploy --only hosting
```

## If Project Still Doesn't Appear

### Option 1: Wait Longer
Sometimes it takes 5-10 minutes for new projects to fully sync.

### Option 2: Try Direct Deploy
```bash
firebase deploy --only hosting --project=sapphire-22470816
```

### Option 3: Manual Deploy via Console
1. Go to Firebase Console → Hosting
2. Click "Get started" if needed
3. Use "Deploy manually" option
4. Upload the `dist` folder

## What We Have Ready

✅ **Configuration files updated**:
- `.firebaserc` → `sapphire-22470816`
- `firebase.json` → `sapphire-22470816`
- `dist/` folder built and ready

✅ **Just waiting for**:
- Web app to be added
- Project to sync with CLI

## Next Steps

1. **Complete adding the web app** in Firebase Console
2. **Wait 1-2 minutes** for sync
3. **Run**: `firebase projects:list` to check
4. **Then deploy** once project appears

---

**Status**: ⏳ Waiting for web app to be added and project to sync

