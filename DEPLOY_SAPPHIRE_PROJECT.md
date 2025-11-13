# Deploy "sapphire" Project - Step by Step

## Project Info
- **Display Name**: sapphire
- **Project ID**: sapphire-22470816
- **Hosting URL**: https://sapphire-22470816.web.app

## Step-by-Step Console Deployment

### Step 1: Open Firebase Console
1. Go to: **https://console.firebase.google.com/**
2. Find and click on **"sapphire"** in your project list

### Step 2: Go to Hosting
1. In the left sidebar, click **"Hosting"**
2. If you see **"Get started"**, click it
3. If hosting is already set up, you'll see the hosting dashboard

### Step 3: Deploy Files
1. Look for **"Deploy"** button (usually top right or center)
2. Click it
3. Choose **"Upload files"** or **"Deploy manually"**

### Step 4: Upload Your Files

**Option A: Upload Zip File (Easiest)**
- File: `/Users/aribs/AIAster/trading-dashboard-dist.zip`
- Click **"Upload"** and select this file
- Firebase will extract it automatically

**Option B: Upload Folder**
- Folder: `/Users/aribs/AIAster/trading-dashboard/dist`
- Click **"Upload folder"** and select the `dist` folder

**Option C: Drag and Drop**
- Open Finder
- Navigate to: `/Users/aribs/AIAster/trading-dashboard/dist`
- Select all files
- Drag into Firebase Console upload area

### Step 5: Wait for Deployment
- Usually takes 1-2 minutes
- You'll see a progress indicator
- Wait for "Deployment complete" message

### Step 6: Get Your URL
Once deployment completes:
- **Hosting URL**: https://sapphire-22470816.web.app
- Click it to view your site!

## What to Upload

Upload everything from the `dist` folder:
- ✅ `index.html`
- ✅ `assets/` folder (with all JS/CSS files)
- ✅ `manifest.json`
- ✅ `sapphire-icon.svg`
- ✅ `sw.js` (service worker)

## Quick Reference

- **Console**: https://console.firebase.google.com/ → Click "sapphire"
- **Hosting**: Left sidebar → "Hosting"
- **Zip file**: `/Users/aribs/AIAster/trading-dashboard-dist.zip`
- **Dist folder**: `/Users/aribs/AIAster/trading-dashboard/dist`
- **Site URL**: https://sapphire-22470816.web.app

---

**Ready to deploy!** Go to Firebase Console → sapphire → Hosting → Deploy

