# Gemini Prompt for ASTER AI Trading System Fixes

## Overview

This directory contains a comprehensive prompt for Google Gemini AI to analyze and fix critical issues in the ASTER AI Trading System.

## Files Created

1. **`gemini-prompt-for-fixes.txt`** - The complete prompt with all context, issues, and solutions
2. **`gemini-fix-prompt.sh`** - Executable script to run the prompt via `gcloud ai generate-content`

## Issues Identified

### 1. Simplified Test App Deployed
- `cloud_trader/api.py` currently has a minimal test app instead of the full TradingService
- Missing all trading endpoints, CORS, Prometheus metrics

### 2. NEG Size = 0 Problem
- All Network Endpoint Groups show size = 0
- Prevents load balancer from routing to Cloud Run services
- Root cause: NEGs can't discover Cloud Run endpoints

### 3. Load Balancer Routing Broken
- URL map exists but can't route due to NEG issues
- Backend services have no healthy endpoints

### 4. Service Duplication
- Multiple conflicting Cloud Run services and NEGs

## How to Use

### Option 1: Run the Script (Recommended)
```bash
cd /Users/aribs/AIAster
./gemini-fix-prompt.sh
```

### Option 2: Manual Execution
```bash
gcloud ai generate-content \
  --model=gemini-1.5-pro \
  --project=quant-ai-trader-credits \
  --prompt="$(cat gemini-prompt-for-fixes.txt)" \
  --temperature=0.2 \
  --max-output-tokens=8192
```

### Option 3: Copy-Paste Prompt
1. Open `gemini-prompt-for-fixes.txt`
2. Copy the entire contents
3. Run:
```bash
gcloud ai generate-content \
  --model=gemini-1.5-pro \
  --project=quant-ai-trader-credits \
  --prompt="<paste prompt here>"
```

## Expected Output

Gemini should provide:
1. Detailed analysis of each issue
2. Step-by-step fixes with exact commands
3. Verification steps for each fix
4. Priority order for implementation

## Priority Order

1. **FIRST**: Restore full `build_app()` in `cloud_trader/api.py` and redeploy
2. **SECOND**: Fix NEG size = 0 by ensuring Cloud Run traffic allocation and recreating NEGs
3. **THIRD**: Verify load balancer routing works end-to-end
4. **FOURTH**: Clean up duplicate/unused services

## Verification Commands

After applying fixes, verify with:

```bash
# Check NEG sizes (should be > 0)
gcloud compute network-endpoint-groups list \
  --filter="region:us-central1" \
  --project=quant-ai-trader-credits \
  --format="table(name,size,cloudRunService)"

# Test direct Cloud Run endpoint
curl https://cloud-trader-880429861698.us-central1.run.app/healthz

# Test through load balancer
curl https://api.sapphiretrade.xyz/healthz
```

## Next Steps

1. Run the Gemini prompt to get AI-generated fixes
2. Review and apply fixes step by step
3. Test each fix before moving to the next
4. Verify all endpoints are working
5. Monitor logs for any errors

