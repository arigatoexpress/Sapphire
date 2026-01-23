# 💻 Setup Sapphire V2 on New Computer

**Purpose:** Continue Drift perpetuals development on another computer
**Last Updated:** 2026-01-23
**Status:** Complete setup guide

---

## 🚀 QUICK START (15 Minutes)

### Step 1: Clone Repository (2 minutes)
```bash
# Clone the repository
git clone https://github.com/arigatoexpress/Sapphire.git

# Navigate to project
cd Sapphire

# Check you're on main branch with latest commit
git log -1 --oneline
# Should show: be30440 🚀 Add Drift Perpetuals Integration - Complete Trading Platform
```

---

### Step 2: Install Google Cloud SDK (5 minutes)

**Mac:**
```bash
# Install gcloud CLI
brew install google-cloud-sdk

# Or download from: https://cloud.google.com/sdk/docs/install
```

**Linux:**
```bash
# Download and install
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

**Windows:**
Download from: https://cloud.google.com/sdk/docs/install

---

### Step 3: Authenticate with GCP (3 minutes)
```bash
# Login to your Google account
gcloud auth login

# Set project
gcloud config set project sapphire-479610

# Verify
gcloud config list
```

---

### Step 4: Install Python Dependencies (5 minutes)
```bash
# Navigate to sapphire_repo
cd sapphire_repo

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python3 -c "import google.cloud; print('✅ GCP libraries installed')"
```

---

## 📁 PROJECT STRUCTURE

After cloning, you'll have:

```
Sapphire/
├── sapphire_repo/                    # Main codebase (in GitHub)
│   ├── cloud_trader/
│   │   ├── drift_client.py          # ✅ Drift perpetuals (8 methods)
│   │   ├── position_monitor.py      # ✅ Real-time monitoring
│   │   ├── platform_router.py       # ✅ Smart routing
│   │   ├── definitions.py           # ✅ 15 perp markets
│   │   └── telegram_enhanced.py     # ✅ Enhanced notifications
│   ├── cloudbuild_all_microservices.yaml  # Deployment config
│   ├── requirements.txt
│   └── services/                    # Microservices
│       ├── bot-drift/
│       └── bot-jupiter/
└── README.md
```

**Note:** Documentation files are NOT in the repo (they're in the project root on your main computer). You'll need to recreate or reference them as needed.

---

## 🔐 CREDENTIALS SETUP

### Option A: Use Existing GCP Account (Recommended)
```bash
# Login with your Google account
gcloud auth login

# Verify access
gcloud run services list --region us-central1 --project=sapphire-479610
```

**Expected:** You should see 6 services (sapphire-drift, jupiter, aster, etc.)

### Option B: Create Service Account Key (If needed)
```bash
# Create service account key
gcloud iam service-accounts keys create ~/sapphire-key.json \
  --iam-account=YOUR_SERVICE_ACCOUNT@sapphire-479610.iam.gserviceaccount.com

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS=~/sapphire-key.json

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'export GOOGLE_APPLICATION_CREDENTIALS=~/sapphire-key.json' >> ~/.bashrc
```

---

## 🧪 VERIFY SETUP

### Test 1: Check GCP Connection
```bash
# List Cloud Run services
gcloud run services list --region us-central1 --project=sapphire-479610

# Expected: 6 services all showing "True" status
```

### Test 2: Check Secrets Access
```bash
# Try to access a secret (should work if permissions are correct)
gcloud secrets versions access latest --secret="TELEGRAM_BOT_TOKEN" --project=sapphire-479610
```

**If this fails:** You may need additional IAM permissions

### Test 3: Check Repository is Up-to-Date
```bash
cd sapphire_repo

# Check for Drift changes
git log --oneline --grep="Drift" -5

# Should show recent Drift perpetuals commit
```

---

## 📚 DOCUMENTATION ACCESS

### Critical Docs (Not in Repo - Need to Recreate or Reference)

These files were created in the project root on your main computer:

1. **DRIFT_PERPETUALS_COMPLETE.md** - Full technical guide
2. **QUICK_START_DRIFT_PERPS.md** - Quick start guide
3. **VERIFICATION_CHECKLIST.md** - Testing checklist
4. **SYSTEM_READY.md** - Readiness status
5. **EXECUTE_NOW.md** - Action plan
6. **SESSION_SUMMARY_2026-01-23_DRIFT.md** - Session summary

**To recreate on new computer:**

Option 1: Copy from main computer
```bash
# On main computer
scp /Users/aribs/Documents/Sapphire_Claude_V1.0/*.md USER@NEW_COMPUTER:~/Sapphire/
```

Option 2: Reference from the codebase
- The actual code has comments explaining functionality
- Check `cloud_trader/drift_client.py` for method documentation
- Check `DEPLOYMENT_GUIDE.md` in repo for deployment info

Option 3: Ask Claude to regenerate
- All information is in the git commit message
- Code is fully documented with docstrings

---

## 🚀 DEPLOYMENT FROM NEW COMPUTER

### Deploy All Services
```bash
cd sapphire_repo

# Submit build
gcloud builds submit \
  --config=cloudbuild_all_microservices.yaml \
  --project=sapphire-479610

# Monitor progress
gcloud builds log $(gcloud builds list --limit=1 --format='value(id)') \
  --project=sapphire-479610 \
  --stream
```

### Deploy Single Service (Faster)
```bash
# Deploy just Drift service
gcloud run deploy sapphire-drift \
  --source . \
  --region us-central1 \
  --project=sapphire-479610
```

---

## 🔧 DEVELOPMENT WORKFLOW

### Make Changes
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes to code
# ... edit files ...

# Test locally (if possible)
python3 -m pytest tests/

# Commit changes
git add .
git commit -m "feat: your feature description"

# Push to GitHub
git push origin feature/your-feature-name
```

### Deploy Changes
```bash
# Merge to main
git checkout main
git merge feature/your-feature-name
git push origin main

# Deploy to production
gcloud builds submit \
  --config=cloudbuild_all_microservices.yaml \
  --project=sapphire-479610
```

---

## 🐛 TROUBLESHOOTING

### Issue: "Permission denied" when accessing GCP
**Solution:**
```bash
# Re-authenticate
gcloud auth login

# Or use service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### Issue: "Module not found" errors
**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Or recreate venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Issue: Can't access secrets
**Solution:**
```bash
# Check your permissions
gcloud projects get-iam-policy sapphire-479610 \
  --flatten="bindings[].members" \
  --filter="bindings.members:YOUR_EMAIL"

# You need: roles/secretmanager.secretAccessor
```

### Issue: Git clone fails
**Solution:**
```bash
# Use HTTPS if SSH fails
git clone https://github.com/arigatoexpress/Sapphire.git

# Or setup SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"
# Add to GitHub: Settings → SSH Keys
```

---

## 💡 USEFUL COMMANDS

### Check System Status
```bash
# All services
gcloud run services list --region us-central1 --project=sapphire-479610

# Drift service specifically
gcloud run services describe sapphire-drift \
  --region us-central1 \
  --project=sapphire-479610

# Recent logs
gcloud run services logs read sapphire-drift \
  --region us-central1 \
  --limit=50
```

### Monitor Builds
```bash
# List recent builds
gcloud builds list --limit=5 --project=sapphire-479610

# Stream logs of latest build
gcloud builds log $(gcloud builds list --limit=1 --format='value(id)') \
  --project=sapphire-479610 \
  --stream
```

### Access Secrets (for debugging)
```bash
# List all secrets
gcloud secrets list --project=sapphire-479610

# View secret value (be careful!)
gcloud secrets versions access latest \
  --secret="DRIFT_SOLANA_PRIVATE_KEY" \
  --project=sapphire-479610
```

---

## 🎯 WHAT'S INCLUDED IN REPO

### Drift Perpetuals Code ✅
- `cloud_trader/drift_client.py` - 8 trading methods (400+ lines)
- `cloud_trader/position_monitor.py` - Real-time monitoring (350+ lines)
- `cloud_trader/platform_router.py` - Smart routing
- `cloud_trader/definitions.py` - 15 markets defined
- `cloud_trader/telegram_enhanced.py` - Enhanced notifications

### Deployment Config ✅
- `cloudbuild_all_microservices.yaml` - Main deployment
- `cloudbuild_microservices.yaml` - Alternative deployment
- `env-vars-production.yaml` - Environment variables

### Microservices ✅
- `services/bot-drift/` - Drift microservice
- `services/bot-jupiter/` - Jupiter microservice
- `services/shared/` - Shared libraries

### Tests ✅
- `tests/test_drift.py` - Drift tests
- `tests/test_jupiter.py` - Jupiter tests
- `tests/test_all_platforms.py` - Integration tests

---

## 📊 SYSTEM OVERVIEW (Quick Reference)

### Deployed Services (6 Total)
1. **sapphire-drift** - Drift perpetuals (rev 00003-7pp)
2. **sapphire-jupiter** - Jupiter spot swaps (rev 00003-fzn)
3. **sapphire-aster** - Aster DEX (rev 00003-zcj)
4. **sapphire-hyperliquid** - Hyperliquid (rev 00003-7n7)
5. **sapphire-symphony** - Symphony (rev 00003-lm7)
6. **sapphire-v2** - Main orchestrator (rev 00002-khb)

### Wallets (Important!)
- **Jupiter (Spot):** 4jnvRT5uk7MzXp1swJpbcXStKVecnuDCLjxe6ccsVTik
- **Drift (Perps):** B1UUWzWr9hWYfUE2xLEDVpyWzWWNWcTPv7Ea2j6guEZD

### GCP Project
- **Project ID:** sapphire-479610
- **Region:** us-central1
- **Platform:** Cloud Run

---

## 🎉 YOU'RE READY!

After completing this setup:

✅ **Repository cloned** from GitHub
✅ **GCP authenticated** and configured
✅ **Dependencies installed** (Python packages)
✅ **Access verified** to Cloud Run services
✅ **Ready to develop** and deploy changes

### Next Steps:
1. **Familiarize** with the codebase
2. **Check service logs** to understand current state
3. **Review** `drift_client.py` and `position_monitor.py`
4. **Test** deployment from new computer (optional)

---

## 📞 QUICK REFERENCE LINKS

**GitHub Repository:** https://github.com/arigatoexpress/Sapphire
**GCP Console:** https://console.cloud.google.com/run?project=sapphire-479610
**Drift App:** https://app.drift.trade/
**Drift Docs:** https://docs.drift.trade/

---

## 🔄 KEEPING IN SYNC

### Pull Latest Changes
```bash
# Always pull before making changes
git pull origin main

# Check what changed
git log --oneline -10
```

### Push Your Changes
```bash
# Commit and push
git add .
git commit -m "Your commit message"
git push origin main
```

### Handle Conflicts
```bash
# If you have conflicts
git pull origin main  # This will show conflicts

# Manually resolve conflicts in files
# Then:
git add .
git commit -m "Merge conflicts resolved"
git push origin main
```

---

**Setup Complete!** You can now continue development on any computer with access to the GitHub repository and GCP project.

---

**Last Commit:** be30440 - Drift Perpetuals Integration
**Total Changes:** 76 files, 11,705 insertions
**Repository:** https://github.com/arigatoexpress/Sapphire
**Status:** ✅ Ready for multi-computer development
