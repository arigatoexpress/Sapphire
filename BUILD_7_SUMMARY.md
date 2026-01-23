# Build #7 - Final Microservices Deployment

## Build Information
- **Build ID**: 949e2754-5cd5-43f0-8975-268bafef6b54
- **Started**: 2026-01-20 21:07 UTC
- **Status**: IN PROGRESS
- **Expected Completion**: ~21:25 UTC

## Critical Fix Applied
**File**: `cloud_trader/main_v2.py` (lines 99-105)

**Issue**: sapphire-web was still running the trading orchestrator because main_v2.py unconditionally called `orchestrator.start()` without checking SERVE_FRONTEND.

**Fix**:
```python
# MICROSERVICES: Skip trading system if this is the web-only service
serve_frontend = os.getenv("SERVE_FRONTEND", "false").lower() == "true"
if serve_frontend:
    logger.info("🌐 Running in web-only mode (SERVE_FRONTEND=true) - skipping trading orchestrator")
else:
    # Start trading system
    await orchestrator.start()
```

## All Fixes Included in Build #7

1. ✅ **cloud_trader/trading_service.py** (lines 449-456)
   - Skip trading loop when SERVE_FRONTEND=true

2. ✅ **cloud_trader/api.py** (lines 280-300)
   - Skip V2 initialization when SERVE_FRONTEND=true

3. ✅ **cloud_trader/core/orchestrator.py** (lines 56-57)
   - OrchestratorConfig reads enable_drift and enable_symphony from Settings

4. ✅ **cloud_trader/main_v2.py** (lines 99-105)
   - Skip orchestrator.start() when SERVE_FRONTEND=true **(NEW in Build #7)**

5. ✅ **cloudbuild_microservices.yaml**
   - Added --project=$PROJECT_ID flag to all 6 deployment steps
   - Memory: 2Gi, CPU: 2 for all services

## Pre-Deployment Verification ✅

### Code Quality
- [x] Python syntax validated (no errors)
- [x] All imports verified
- [x] No duplicate code

### Infrastructure
- [x] 6 Cloud Run services (no duplicates):
  - sapphire-hl (Hyperliquid)
  - sapphire-lighter (Lighter.xyz)
  - sapphire-drift (Drift Protocol)
  - sapphire-aster (AsterDEX)
  - sapphire-symphony (Agent Orchestration)
  - sapphire-web (Dashboard/Frontend)

- [x] PubSub Resources:
  - Topic: sapphire-service-events ✅
  - Subscription: sapphire-web-events ✅

### Environment Configuration
Each service has correct environment variables:

**Trading Services** (hl, lighter, drift, aster, symphony):
```
ENABLE_<PLATFORM>=true
SERVE_FRONTEND=false
ENABLE_PUBSUB=true
GCP_PROJECT_ID=sapphire-479610
```

**Web Service**:
```
ENABLE_HYPERLIQUID=false
ENABLE_LIGHTER=false
ENABLE_DRIFT=false
ENABLE_SYMPHONY=false
ENABLE_ASTER=false
SERVE_FRONTEND=true
ENABLE_PUBSUB=true
GCP_PROJECT_ID=sapphire-479610
```

## Expected Behavior After Deployment

### sapphire-web (Dashboard)
- ❌ Should NOT run trading orchestrator
- ❌ Should NOT execute trades
- ✅ Should show `"trading_loop": false` in health endpoint
- ✅ Should aggregate data from other services via PubSub
- ✅ Should serve fleet endpoints:
  - `/api/fleet/summary`
  - `/api/fleet/health`
  - `/api/fleet/positions`

### Trading Services (hl, lighter, drift, aster, symphony)
- ✅ Should run trading orchestrator
- ✅ Should execute trades on their respective platforms
- ✅ Should publish events to PubSub topic
- ✅ Should show `"trading_loop": true` in health endpoint

## Verification Steps After Deployment

### 1. Check sapphire-web Logs
```bash
gcloud logging read 'resource.labels.service_name="sapphire-web"' \
  --limit=50 --format='value(textPayload,jsonPayload.message)' \
  --freshness=5m | grep -E "(web-only|orchestrator|ROUTER|BUY|SELL)"
```

**Expected**: Should see "🌐 Running in web-only mode" message, NO trading activity

### 2. Check Trading Service Logs (e.g., sapphire-hl)
```bash
gcloud logging read 'resource.labels.service_name="sapphire-hl"' \
  --limit=50 --format='value(textPayload,jsonPayload.message)' \
  --freshness=5m | grep -E "(Starting|ROUTER|BUY|SELL)"
```

**Expected**: Should see trading activity and order execution

### 3. Test Health Endpoints
```bash
# Web service (should show trading_loop: false)
curl https://sapphire-web-s77j6bxyra-ew.a.run.app/health | jq '.orchestrator.components.trading_loop'

# Trading service (should show trading_loop: true)
curl https://sapphire-hl-s77j6bxyra-ew.a.run.app/health | jq '.orchestrator.components.trading_loop'
```

### 4. Test Fleet Endpoints
```bash
# Fleet summary (aggregated data)
curl https://sapphire-web-s77j6bxyra-ew.a.run.app/api/fleet/summary | jq '.'

# Fleet health (all services status)
curl https://sapphire-web-s77j6bxyra-ew.a.run.app/api/fleet/health | jq '.'
```

### 5. Check PubSub Events
```bash
# Wait for heartbeat events (every 30s)
sleep 60

# Pull events
gcloud pubsub subscriptions pull sapphire-web-events --limit=10 --format='value(message.data)'
```

**Expected**: Should see events from all 5 trading services

## Build History

| Build | Status | Issue | Fix |
|-------|--------|-------|-----|
| #1 | ❌ FAILED | Memory 512MB too low | Increased to 1Gi |
| #2 | ✅ SUCCESS | Web service trading | Added trading_service.py check |
| #3 | ✅ SUCCESS | Web service still trading | Partial fix only |
| #4 | ❌ FAILED | Missing --project flag | Added flag to cloudbuild |
| #5 | ✅ SUCCESS | Web service still trading | Config bug |
| #6 | ✅ SUCCESS | Web service still trading | Fixed OrchestratorConfig |
| #7 | 🔄 IN PROGRESS | Web service still trading | Fixed main_v2.py entry point |

## Root Cause Analysis

The application had **THREE separate entry points** where trading could be started:

1. ✅ `trading_service.start()` - Fixed in Build #2
2. ✅ `api.py lifespan` (V2 initialization) - Fixed in Build #3
3. ❌ `main_v2.py lifespan` (orchestrator.start()) - **Fixed in Build #7**

The third entry point was missed because:
- The Dockerfile uses `CMD ["python", "-m", "cloud_trader.main_v2"]`
- main_v2.py has its own lifespan function that directly calls `orchestrator.start()`
- This bypassed all the checks in trading_service.py and api.py

## Service URLs

- Dashboard: https://sapphire-web-s77j6bxyra-ew.a.run.app
- Hyperliquid: https://sapphire-hl-s77j6bxyra-ew.a.run.app
- Lighter: https://sapphire-lighter-s77j6bxyra-ew.a.run.app
- Drift: https://sapphire-drift-s77j6bxyra-ew.a.run.app
- Aster: https://sapphire-aster-s77j6bxyra-ew.a.run.app
- Symphony: https://sapphire-symphony-s77j6bxyra-ew.a.run.app

## Success Criteria

Build #7 will be considered successful when:

- [  ] Build completes successfully
- [  ] All 6 services deploy without errors
- [  ] sapphire-web does NOT execute trades
- [  ] 5 trading services DO execute trades
- [  ] PubSub events flow from trading services to web
- [  ] Fleet endpoints return aggregated data
- [  ] Health endpoints show correct trading_loop status
