# Sapphire V2 Microservices - Deployment Summary

## Current Build Status

**Build #6 (Critical Fix):**
- Build ID: 49a19ee7-27e1-41e7-8192-9822109864a5
- Started: 2026-01-20 20:42 UTC
- Status: IN PROGRESS
- Expected completion: ~20:55 UTC

**Critical Fix Applied:**
- cloud_trader/core/orchestrator.py - OrchestratorConfig now reads enable_drift and enable_symphony from Settings/environment variables (lines 56-57)

**Root Cause Identified:**
Build #5 deployed successfully but sapphire-web was still running trading components because:
1. OrchestratorConfig.__init__() only passed enable_aster to config (line 55)
2. enable_drift and enable_symphony were using hardcoded defaults (True)
3. Even though ENABLE_DRIFT=false and ENABLE_SYMPHONY=false were set in environment, the Orchestrator ignored them

**All Previous Fixes:**
1. cloud_trader/trading_service.py - Skip trading loop when SERVE_FRONTEND=true
2. cloud_trader/api.py - Skip V2 initialization when SERVE_FRONTEND=true
3. cloudbuild_microservices.yaml - Added --project=$PROJECT_ID flag
4. cloud_trader/core/orchestrator.py - Pass enable_drift and enable_symphony to config

**Previous Builds:**
- Build #5 (673e2464): SUCCESS - But config bug prevented it from working
- Build #4 (5576d6f0): FAILED - Missing --project flag
- Build #3 (f738afcd): SUCCESS - Partial fix (trading_service.py only)
- Build #2 (027212f6): SUCCESS - But web service still trading
- Build #1 (b4ff08e7): FAILED - Memory limit too low (512MB)

## Service URLs

- sapphire-web: https://sapphire-web-s77j6bxyra-ew.a.run.app
- sapphire-hl: https://sapphire-hl-267358751314.europe-west1.run.app  
- sapphire-lighter: https://sapphire-lighter-267358751314.europe-west1.run.app
- sapphire-drift: https://sapphire-drift-267358751314.europe-west1.run.app
- sapphire-aster: https://sapphire-aster-267358751314.europe-west1.run.app
- sapphire-symphony: https://sapphire-symphony-267358751314.europe-west1.run.app

## Verification After Deployment

```bash
# 1. Check all services deployed
gcloud run services list --region=europe-west1

# 2. Get dashboard URL
WEB_URL=$(gcloud run services describe sapphire-web --region=europe-west1 --format='value(status.url)')

# 3. Test health (should show trading_loop: false for web)
curl "$WEB_URL/health"

# 4. Test fleet summary
curl "$WEB_URL/api/fleet/summary"

# 5. Check PubSub events (wait 60s for heartbeats)
sleep 60
gcloud pubsub subscriptions pull sapphire-web-events --limit=10
```

## Architecture

6 microservices:
- 5 trading services (hl, lighter, drift, aster, symphony) - ENABLE_*=true
- 1 web service (web) - SERVE_FRONTEND=true

Communication: Trading services → PubSub → Web aggregator → Fleet API
