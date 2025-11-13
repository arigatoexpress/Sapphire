# Deploy via Firebase Console - Step by Step

## Quick Steps

### Step 1: Open Firebase Hosting
1. Go to: **https://studio.firebase.google.com/sapphire-22470816/hosting**
2. Or: Go to project dashboard → Click **"Hosting"** in left sidebar

### Step 2: Get Started (if needed)
- If you see **"Get started"** button, click it
- If hosting is already set up, skip to Step 3

### Step 3: Find Deploy Option
Look for one of these:
- **"Deploy"** button (top right or center)
- **"Add files"** or **"Upload files"** button
- **"Deploy manually"** option
- Drag-and-drop area

### Step 4: Upload Files
**Option A: Upload Folder**
1. Click **"Upload folder"** or **"Choose folder"**
2. Navigate to: `/Users/aribs/AIAster/trading-dashboard/dist`
3. Select the `dist` folder
4. Click **"Open"** or **"Upload"**

**Option B: Drag and Drop**
1. Open Finder (Mac) or File Explorer (Windows)
2. Navigate to: `/Users/aribs/AIAster/trading-dashboard/dist`
3. Select all files in the `dist` folder
4. Drag them into the Firebase Console upload area

**Option C: Zip and Upload**
1. Zip the `dist` folder: `cd /Users/aribs/AIAster/trading-dashboard && zip -r dist.zip dist/`
2. Upload the `dist.zip` file
3. Firebase will extract it

### Step 5: Wait for Deployment
- Firebase will upload and process files
- Usually takes 1-2 minutes
- You'll see a progress indicator

### Step 6: Get Your URL
Once deployment completes:
- You'll see: **"Deployment complete"**
- Your URL: **https://sapphire-22470816.web.app**
- Click it to view your site!

## What to Upload

Upload everything from the `dist` folder:
- ✅ `index.html`
- ✅ `assets/` folder (with all JS/CSS files)
- ✅ `manifest.json`
- ✅ `sapphire-icon.svg`
- ✅ `sw.js` (service worker)

## Troubleshooting

### If you don't see "Upload" option:
- Make sure you're in the Hosting section
- Check if hosting is fully set up
- Try refreshing the page

### If upload fails:
- Make sure all files are selected
- Try uploading files one by one
- Check file sizes (should be small)

### If site doesn't load:
- Wait 2-3 minutes for DNS propagation
- Clear browser cache
- Try incognito mode

---

**Quick Link**: https://studio.firebase.google.com/sapphire-22470816/hosting

