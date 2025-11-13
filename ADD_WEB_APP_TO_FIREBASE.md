# How to Add Web App to Firebase

## Step-by-Step Instructions

### Step 1: Open Firebase Console
1. Go to: https://studio.firebase.google.com/sapphire-22470816
2. Make sure you're in the project dashboard (not the setup screen)

### Step 2: Add Web App
1. Look for **"Add app"** button or the **web icon (</>)** 
   - Usually in the center of the dashboard
   - Or in the top section with app icons
2. Click the **web icon (</>)** or **"Add app"** → **"Web"**

### Step 3: Register the App
1. **App nickname**: Enter a name (e.g., "Sapphire Trading Dashboard" or "Sapphire Web")
2. **Also set up Firebase Hosting**: ✅ **Check this box** (important!)
3. Click **"Register app"**

### Step 4: Copy Firebase Config
After registering, Firebase will show you the config object. It looks like:
```javascript
const firebaseConfig = {
  apiKey: "AIza...",
  authDomain: "sapphire-22470816.firebaseapp.com",
  projectId: "sapphire-22470816",
  storageBucket: "sapphire-22470816.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abc123..."
};
```

### Step 5: Update Our Config
Once you have the config, I'll update:
- `trading-dashboard/src/lib/firebase.ts` with the new config
- Then we can deploy!

## Alternative: If You Don't See "Add App"

If you don't see the "Add app" button:
1. Go to **Project Settings** (gear icon ⚙️)
2. Scroll down to **"Your apps"** section
3. Click **"Add app"** or the **web icon (</>)**

## What This Does

Adding a web app:
- ✅ Registers your app with Firebase
- ✅ Generates the Firebase config
- ✅ Sets up Firebase Hosting (if you checked the box)
- ✅ Creates the hosting site

After this, the project should appear in Firebase CLI and we can deploy!

---

**Next Step**: Add the web app in Firebase Console, then share the config values with me so I can update the code.

