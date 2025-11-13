# Deploy via Firebase Console (Manual Upload)

Since the CLI sync is taking time, you can deploy directly via Firebase Console.

## Step-by-Step: Deploy via Console

### Step 1: Open Firebase Hosting
1. Go to: **https://studio.firebase.google.com/sapphire-22470816/hosting**
2. Or: Go to project → Click **"Hosting"** in the left sidebar

### Step 2: Get Started with Hosting
1. If you see **"Get started"**, click it
2. If hosting is already set up, you'll see the hosting dashboard

### Step 3: Deploy Files
1. Look for **"Deploy"** or **"Add files"** button
2. Click it
3. You'll see options:
   - **"Deploy from CLI"** (not available yet)
   - **"Deploy manually"** or **"Upload files"** ← Choose this

### Step 4: Upload dist Folder
1. Click **"Upload folder"** or **"Choose files"**
2. Navigate to: `/Users/aribs/AIAster/trading-dashboard/dist`
3. Select the entire `dist` folder
4. Click **"Upload"** or **"Deploy"**

### Step 5: Wait for Deployment
- Firebase will upload and deploy your files
- This usually takes 1-2 minutes
- You'll see a progress indicator

### Step 6: Get Your URL
Once deployment completes, you'll see:
- **Hosting URL**: `https://sapphire-22470816.web.app`
- Click it to view your site!

## Alternative: If You Don't See Upload Option

Some Firebase Console versions use different interfaces:

### Option A: Drag and Drop
1. Open the `dist` folder on your computer
2. Drag all files from `dist` into the Firebase Console upload area

### Option B: Use Firebase CLI (once it syncs)
Once the project appears in CLI:
```bash
cd /Users/aribs/AIAster/trading-dashboard
firebase login  # Re-login if needed
firebase use sapphire-22470816
firebase deploy --only hosting
```

## What to Upload

Upload everything from the `dist` folder:
- `index.html`
- `assets/` folder (with all JS/CSS files)
- `manifest.json`
- `sapphire-icon.svg`
- `sw.js` (service worker)

## After Deployment

1. Visit: **https://sapphire-22470816.web.app**
2. Your site should be live!
3. No login required (we removed that)

---

**Quick Path**: https://studio.firebase.google.com/sapphire-22470816/hosting → Deploy → Upload files

