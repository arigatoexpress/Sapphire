# 🚀 Deploy Sapphire V2 Now

## Changes Completed ✅

### 1. Fixed Telegram Conflict
- Disabled `TelegramListener` to prevent HTTP 409 error
- Only `MonitoringService` handles notifications now
- File: `cloud_trader/core/orchestrator.py` (lines 205-212)

### 2. Configured Vertex AI API Key
- Added support for your Vertex AI API key
- Credentials will be loaded from GCP Secret Manager
- File: `cloud_trader/core/orchestrator.py` (lines 155-161)

### 3. Created Cloud NAT Setup Scripts
- Scripts ready to create static IP for API whitelisting
- Ensures Aster and other exchanges can whitelist your IP

## 📋 Deployment Steps (Run from Terminal)

### Prerequisites
Make sure you have:
- [ ] Google Cloud SDK installed (`gcloud` command)
- [ ] Authenticated: `gcloud auth login`
- [ ] Docker running (for local testing)

### Step 1: Navigate to Project Directory
```bash
cd /Users/aribs/Documents/Sapphire_Claude_V1.0/sapphire_repo
```

### Step 2: Authenticate with Google Cloud
```bash
gcloud auth login
gcloud config set project sapphire-479610
```

### Step 3: Run Full Deployment
```bash
./deploy_sapphire_v2.sh
```

**This will:**
1. ✅ Add Vertex API key to Secret Manager
2. ✅ Set up Cloud NAT with static IP
3. ✅ Build and deploy to Cloud Run
4. ✅ Show you the static IP to whitelist

### Alternative: Manual Step-by-Step

If you prefer to run each step manually:

```bash
# 1. Configure Vertex API key secret
./setup_secrets.sh

# 2. Set up Cloud NAT with static IP
./setup_cloud_nat.sh

# Note the static IP address shown at the end!

# 3. Deploy to Cloud Run
gcloud builds submit --config=cloudbuild.yaml --project=sapphire-479610
```

## ⚡ Quick Commands

### Get Your Static IP
```bash
gcloud compute addresses describe sapphire-static-ip \
  --region=us-central1 \
  --project=sapphire-479610 \
  --format="get(address)"
```

### Check Deployment Status
```bash
gcloud run services describe sapphire-v2 \
  --region=us-central1 \
  --project=sapphire-479610
```

### View Logs
```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2"' \
  --limit=50 \
  --project=sapphire-479610
```

### Check for Errors
```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND severity>=ERROR' \
  --limit=20 \
  --project=sapphire-479610
```

## 🎯 Post-Deployment Actions

### 1. Whitelist Your Static IP in Aster
After deployment completes:
1. Note the static IP shown in the output
2. Go to Aster API settings
3. Add the static IP to whitelist
4. **Previously you whitelisted: 34.34.233.16**
5. **New static IP will be shown after setup**

### 2. Verify System is Working

Check logs for these success messages:

```bash
# System started successfully
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "Sapphire V2 is ONLINE"' --limit=1 --project=sapphire-479610

# Telegram configured
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "Telegram notifications configured"' --limit=1 --project=sapphire-479610

# Using Vertex AI
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "Using Vertex AI API key"' --limit=1 --project=sapphire-479610

# Trading loop running
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "Cycle #"' --limit=5 --project=sapphire-479610
```

### 3. Check for Issues

```bash
# No Telegram conflicts
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "409"' --limit=5 --project=sapphire-479610

# No Aster IP errors
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "2015"' --limit=5 --project=sapphire-479610

# No AI model failures
gcloud logging read 'resource.labels.service_name="sapphire-v2" AND "fallback response"' --limit=5 --project=sapphire-479610
```

## 🔍 Expected Results

After successful deployment, you should see:

1. ✅ **Telegram Working**
   - No HTTP 409 errors
   - Startup notification received
   - Trade notifications working

2. ✅ **Trading Active**
   - "Cycle #X complete" messages in logs
   - AI models responding (Vertex AI)
   - No "Error -2015" (IP whitelist)

3. ✅ **Static IP Configured**
   - All egress traffic uses same IP
   - Can be whitelisted in Aster and other exchanges

## 📞 Troubleshooting

### If deployment fails:
1. Check that you have necessary GCP permissions
2. Ensure billing is enabled on project
3. Verify all required APIs are enabled:
   - Cloud Run API
   - Cloud Build API
   - Secret Manager API
   - Compute Engine API
   - VPC Access API

### Enable required APIs:
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  vpcaccess.googleapis.com \
  --project=sapphire-479610
```

## 📝 What Changed in Code

### Modified Files:
1. **cloud_trader/core/orchestrator.py**
   - Lines 205-212: Disabled TelegramListener
   - Lines 155-161: Added Vertex AI key injection

### New Files:
1. **setup_secrets.sh** - Configures Vertex API key in Secret Manager
2. **setup_cloud_nat.sh** - Sets up Cloud NAT with static IP
3. **deploy_sapphire_v2.sh** - Full automated deployment
4. **DEPLOYMENT_GUIDE.md** - Detailed deployment documentation
5. **DEPLOY_NOW.md** - This file (quick start guide)

### Unchanged (Already Configured):
- **cloudbuild.yaml** - Already has VPC connector configured
- **Dockerfile** - No changes needed
- All other trading logic remains the same

## 🎉 Summary

All code changes are complete. You just need to:
1. Run `./deploy_sapphire_v2.sh` from terminal
2. Whitelist the static IP in Aster
3. Verify logs show successful startup

The system will then:
- ✅ Send Telegram notifications
- ✅ Execute trades using AI models
- ✅ Use consistent static IP for APIs
- ✅ No more HTTP 409 or API -2015 errors

**Ready to deploy!** 🚀
