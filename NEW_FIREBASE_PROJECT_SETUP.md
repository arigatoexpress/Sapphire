# Setting Up New Firebase Project: sapphire-22470816

## Current Status

✅ **Configuration Updated**: Files updated to use `sapphire-22470816`  
⏳ **Project Sync**: Waiting for project to appear in Firebase CLI  
📋 **Next Steps**: Initialize hosting once project is available

## What I've Done

1. ✅ Updated `.firebaserc` to use `sapphire-22470816`
2. ✅ Updated `firebase.json` to use the new project
3. ✅ Updated CSP headers for new Firebase domains

## Project Sync Delay

When you create a new Firebase project, it can take **1-2 minutes** to:
- Sync with Firebase CLI
- Appear in the project list
- Be accessible via CLI commands

## Steps to Complete Setup

### Step 1: Verify Project in Console
1. Go to: https://studio.firebase.google.com/sapphire-22470816
2. Make sure the project is fully loaded
3. Check the project ID (should be `sapphire-22470816`)

### Step 2: Wait for Sync (1-2 minutes)
The project needs to sync with Firebase CLI. Wait a moment, then:

```bash
cd trading-dashboard
firebase projects:list
# Should show sapphire-22470816
```

### Step 3: Switch to New Project
```bash
firebase use sapphire-22470816
```

### Step 4: Initialize Firebase Hosting
If hosting isn't set up yet:

```bash
firebase init hosting
# Select: Use an existing project
# Select: sapphire-22470816
# Public directory: dist
# Configure as single-page app: Yes
# Set up automatic builds: No (or Yes if you want)
```

### Step 5: Deploy
```bash
firebase deploy --only hosting
```

## Alternative: Initialize Now

If the project still doesn't appear, you can try initializing hosting directly:

```bash
cd trading-dashboard
firebase init hosting --project=sapphire-22470816
```

This will:
- Create the hosting site if it doesn't exist
- Set up the configuration
- Allow you to deploy

## Verify Configuration

After setup, check:

```bash
# Check current project
firebase use

# List hosting sites
firebase hosting:sites:list

# Should show:
# sapphire-22470816 | https://sapphire-22470816.web.app
```

## Current Configuration Files

### `.firebaserc`
```json
{
  "projects": {
    "default": "sapphire-22470816"
  }
}
```

### `firebase.json`
- Site: `sapphire-22470816`
- Public directory: `dist`
- CSP headers updated for new Firebase domains

## Expected URLs

After deployment:
- **Default URL**: https://sapphire-22470816.web.app
- **Firebase App URL**: https://sapphire-22470816.firebaseapp.com

## Troubleshooting

### If project doesn't appear:
1. Wait 2-3 minutes for sync
2. Refresh: `firebase projects:list`
3. Check you're logged into the correct Google account
4. Verify project exists in Console

### If you get permission errors:
- Make sure you're the project owner
- Check Firebase Console → Project Settings → Users and permissions

### If hosting initialization fails:
- Try: `firebase init hosting --project=sapphire-22470816`
- Or create hosting site manually in Console

---

**Next Action**: Wait 1-2 minutes, then run `firebase projects:list` to see if the project appears.

