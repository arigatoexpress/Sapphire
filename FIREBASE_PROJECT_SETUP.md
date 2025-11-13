# Firebase Project Setup Guide

## Current Status

✅ **GCP Project**: `sapphireinfinite` exists  
✅ **Firebase CLI**: Project is configured  
✅ **Firebase APIs**: All enabled  
⚠️ **Firebase Console**: May need to be added manually

## The Issue

The project exists in GCP and Firebase CLI, but you might not see it in the Firebase Console. This happens when:
- The GCP project exists but hasn't been "added" to Firebase Console
- You need to link the GCP project to Firebase Console

## Solution: Add Existing GCP Project to Firebase

### Step 1: Go to Firebase Console
1. Visit: https://console.firebase.google.com/
2. You should see a list of projects or an "Add project" button

### Step 2: Add Existing Project
1. Click **"Add project"** (or "Create a project")
2. Select **"Add Firebase to an existing Google Cloud project"**
3. Choose **"sapphireinfinite"** from the dropdown
4. Click **"Continue"**

### Step 3: Configure Firebase Services
1. **Google Analytics**: Optional (you can skip or enable)
2. Click **"Create project"** (or "Add Firebase")
3. Wait for setup to complete (~1-2 minutes)

### Step 4: Initialize Firebase Hosting
Once the project is added, you can:

**Via Console:**
1. Go to: https://console.firebase.google.com/project/sapphireinfinite/hosting
2. Click "Get started" if prompted
3. Follow the setup wizard

**Via CLI (already done):**
```bash
cd trading-dashboard
firebase init hosting
# Select: Use an existing project
# Select: sapphireinfinite
# Public directory: dist
# Configure as single-page app: Yes
# Set up automatic builds: No (or Yes if you want)
```

## Verify Setup

### Check in Console
1. Go to: https://console.firebase.google.com/project/sapphireinfinite
2. You should see:
   - Project overview
   - Hosting section
   - All Firebase services

### Check via CLI
```bash
firebase projects:list
# Should show sapphireinfinite

firebase hosting:sites:list --project=sapphireinfinite
# Should show the hosting site
```

### Check Current Deployment
```bash
firebase hosting:channel:list --project=sapphireinfinite
# Should show deployment channels
```

## Current Configuration

- **Project ID**: `sapphireinfinite`
- **Project Number**: `342943608894`
- **Firebase Site**: `sapphireinfinite`
- **Default URL**: https://sapphireinfinite.web.app

## Next Steps

1. **Add project to Firebase Console** (if not visible)
   - Go to Firebase Console
   - Add existing GCP project `sapphireinfinite`

2. **Verify Hosting is set up**
   - Check: https://console.firebase.google.com/project/sapphireinfinite/hosting
   - Should see deployment history

3. **Add custom domain** (optional)
   - Go to Hosting → Custom domains
   - Add `sapphiretrade.xyz`

## Troubleshooting

### If project doesn't appear in dropdown:
- Make sure you're logged into the correct Google account
- Check that you have "Owner" or "Editor" permissions on the GCP project
- Try refreshing the Firebase Console

### If you get permission errors:
```bash
# Check your GCP permissions
gcloud projects get-iam-policy sapphireinfinite --flatten="bindings[].members" --filter="bindings.members:user:YOUR_EMAIL"

# You should have roles like:
# - roles/owner
# - roles/editor
# - roles/firebase.admin
```

### If Hosting isn't working:
```bash
# Re-initialize hosting
cd trading-dashboard
firebase init hosting --project=sapphireinfinite
```

---

**Quick Link**: https://console.firebase.google.com/project/sapphireinfinite

