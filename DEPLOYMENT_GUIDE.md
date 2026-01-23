# Sapphire V2 Deployment Guide

## Summary of Changes Made

### 1. Fixed Telegram Conflict (HTTP 409 Error)
- **Issue**: Both `TelegramListener` and `MonitoringService` were using the same bot token with long polling
- **Fix**: Disabled `TelegramListener` in `cloud_trader/core/orchestrator.py` (lines 205-212)
- **Result**: Only `MonitoringService` handles Telegram notifications now

### 2. Configured Vertex AI (Gemini API)
- **Added**: Vertex AI API key support in credentials
- **Updated**: `cloud_trader/core/orchestrator.py` to prioritize `vertex_api_key` over `gemini_api_key` (lines 155-161)
- **API Key**: Configured in GCP Secret Manager as `vertex_api_key_v1`

### 3. Cloud NAT with Static IP
- **Purpose**: Ensure consistent IP for API whitelist (Aster, etc.)
- **Components**:
  - VPC: `sapphire-vpc`
  - Subnet: `sapphire-subnet` (10.8.0.0/28)
  - VPC Connector: `sapphire-conn-us` (already configured in cloudbuild.yaml)
  - Static IP: `sapphire-static-ip`
  - Cloud Router: `sapphire-nat-router`
  - Cloud NAT: `sapphire-nat`

## Quick Deployment

### Option 1: Full Automated Deployment
```bash
cd sapphire_repo
./deploy_sapphire_v2.sh
```

This script will:
1. Configure Vertex API key secret
2. Set up Cloud NAT with static IP
3. Build and deploy to Cloud Run
4. Display your static IP for whitelisting

### Option 2: Step-by-Step Deployment

#### Step 1: Configure Secrets
```bash
./setup_secrets.sh
```

#### Step 2: Set up Cloud NAT
```bash
./setup_cloud_nat.sh
```

This will output your static IP address. **Whitelist this IP in your Aster API settings.**

#### Step 3: Deploy to Cloud Run
```bash
gcloud builds submit --config=cloudbuild.yaml --project=sapphire-479610
```

## Verify Deployment

### Check Service Status
```bash
gcloud run services describe sapphire-v2 \
  --region=us-central1 \
  --project=sapphire-479610
```

### View Recent Logs
```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2"' \
  --limit=50 \
  --project=sapphire-479610 \
  --format=json
```

### Check for Specific Log Messages

✅ **Expected Success Indicators**:
```bash
# System started
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND "Sapphire V2 is ONLINE"' --limit=5 --project=sapphire-479610

# Telegram configured
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND "Telegram notifications configured"' --limit=5 --project=sapphire-479610

# Aster initialized
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND "Aster Client Initialized"' --limit=5 --project=sapphire-479610

# Vertex AI configured
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND "Using Vertex AI API key"' --limit=5 --project=sapphire-479610
```

❌ **Check for Errors**:
```bash
# No Telegram 409 errors
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND severity>=ERROR AND "409"' --limit=10 --project=sapphire-479610

# No Aster IP whitelist errors
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND severity>=ERROR AND "2015"' --limit=10 --project=sapphire-479610
```

## Get Your Static IP

```bash
gcloud compute addresses describe sapphire-static-ip \
  --region=us-central1 \
  --project=sapphire-479610 \
  --format="get(address)"
```

## Whitelist Static IP

### Aster Exchange
1. Log in to your Aster account
2. Navigate to API Key settings
3. Add the static IP to the whitelist
4. OR enable "Allow all IPs" if preferred

### Other Exchanges
Repeat the above process for any other exchanges that require IP whitelisting.

## Troubleshooting

### Issue: Container crashes on startup
**Check**: Look for `AttributeError` in logs
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND severity>=ERROR AND "AttributeError"' --limit=10 --project=sapphire-479610
```

### Issue: No trades happening
**Check**:
1. Aster API errors (Error -2015 = IP not whitelisted)
2. AI model errors (Vertex API key not loaded)
3. Risk checks blocking trades

### Issue: No Telegram notifications
**Check**:
1. `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Secret Manager
2. No HTTP 409 errors (indicates conflict)
3. `MonitoringService` initialized successfully

## Configuration Files Modified

1. `cloud_trader/core/orchestrator.py`
   - Disabled TelegramListener (line 205-212)
   - Added Vertex AI key injection (line 155-161)

2. `cloudbuild.yaml`
   - Already configured with VPC connector (no changes needed)

3. New deployment scripts:
   - `setup_secrets.sh` - Configure Vertex API key
   - `setup_cloud_nat.sh` - Set up Cloud NAT with static IP
   - `deploy_sapphire_v2.sh` - Complete deployment automation

## Secrets in GCP Secret Manager

The following secrets should exist in `sapphire-479610`:

- `ASTER_API_KEY` - Aster exchange API key
- `ASTER_SECRET_KEY` - Aster exchange secret
- `vertex_api_key_v1` - Vertex AI / Gemini API key ✨ NEW
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications
- `HL_SECRET_KEY` - Hyperliquid private key
- `HL_ACCOUNT_ADDRESS` - Hyperliquid wallet address
- `SOLANA_PRIVATE_KEY` - Solana private key for Drift
- `SYMPHONY_API_KEY` - Symphony API key (optional)

## Post-Deployment Checklist

- [ ] Static IP obtained and whitelisted in Aster
- [ ] Service is running (check `gcloud run services list`)
- [ ] No startup errors in logs
- [ ] Telegram notifications working (check for startup message)
- [ ] Trading loop running (check for "Cycle #X complete" logs)
- [ ] AI models responding (no "fallback response" warnings)
- [ ] Trades executing (check for trade notifications)

## Release Notes (Commit 888aca4)

### Hyperliquid Take Profit / Stop Loss
- **Feature**: TP/SL trigger orders are now placed automatically upon successful trade entry.
    - Take Profit: +5%
    - Stop Loss: -3%
- **Logic**: Implemented in `PlatformRouter` to trigger immediately after entry fill.

### Lighter Integration (Partial)
- **Status**: SDK wrapper implemented (`LighterClient`), credentials stored, `LIGHTER` added to `PlatformRouter`.
- **Note**: Trigger orders for Lighter are currently deferred.

### Dependency Fix
- **Fix**: Downgraded `urllib3<2.1.0` to resolve conflict with `lighter-sdk` and `requests`.

## Verification Steps
1.  **Deploy**: `gcloud builds submit ...` (or check build logs for `5c34bf58`)
2.  **Verify Lighter**: Check logs for `🔌 Lighter Client Initialized`
3.  **Verify TP/SL**:
    - Monitor logs for `✅ [Hyperliquid] TP Set` or `✅ [Hyperliquid] SL Set`
    - Check Hyperliquid UI for open Trigger orders attached to positions.

## Support

If issues persist:
1. Check Cloud Run logs for detailed error messages
2. Verify all secrets are accessible in Secret Manager
3. Ensure VPC connector and Cloud NAT are properly configured
4. Check that static IP is whitelisted in exchange APIs
