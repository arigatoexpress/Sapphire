# Non-US Routing Setup for Geo-Blocked Exchanges

## Problem
Aster CEX blocks US IP addresses. Cloud Run in `us-central1` will be blocked.

## Solutions (Choose One)

### Option 1: HTTP/HTTPS Proxy (Recommended for Quick Setup)
Use a non-US proxy service to route Aster API calls.

**Setup:**
```bash
# Set proxy environment variables in Cloud Run
gcloud run services update sapphire-v2 \
  --region=us-central1 \
  --set-env-vars="HTTP_PROXY=http://your-proxy-server:port,HTTPS_PROXY=http://your-proxy-server:port"
```

**Proxy Services:**
- Bright Data (premium, reliable)
- Oxylabs (enterprise)
- ProxyRack (affordable)
- SmartProxy

**Configuration in Code:**
The `non_us_routing.py` module automatically detects and uses proxy settings.

---

### Option 2: Multi-Region Deployment (Best for Production)
Deploy Aster trader to a European Cloud Run region.

**Deploy to Europe:**
```bash
# Deploy Aster-specific service in Europe
gcloud run deploy sapphire-aster \
  --image=gcr.io/sapphire-479610/sapphire-trader:latest \
  --region=europe-west1 \
  --set-env-vars="ENABLE_ASTER=true,ENABLE_DRIFT=false,ENABLE_HYPERLIQUID=false"
```

**Architecture:**
```
┌─────────────────────────────────────┐
│ US Region (us-central1)             │
│  - Drift trader                     │
│  - Hyperliquid trader               │
│  - Symphony trader                  │
│  - Lighter trader                   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ EU Region (europe-west1)            │
│  - Aster trader (non-US IP)         │
└─────────────────────────────────────┘
```

---

### Option 3: VPC Connector with Cloud NAT
Route egress traffic through a non-US NAT gateway.

**Setup:**
1. Create VPC in non-US region
2. Set up Cloud NAT with non-US IP
3. Connect Cloud Run to VPC
4. Route Aster traffic through NAT

**Complex but Most Secure**

---

## Quick Start (Option 1 - Proxy)

### 1. Get a Proxy Service
Sign up for a proxy service with European or Asian endpoints.

### 2. Configure Environment
```bash
export HTTP_PROXY="http://eu-proxy.example.com:8080"
export HTTPS_PROXY="http://eu-proxy.example.com:8080"

# Update Cloud Run
gcloud run services update sapphire-v2 \
  --region=us-central1 \
  --set-env-vars="HTTP_PROXY=${HTTP_PROXY},HTTPS_PROXY=${HTTPS_PROXY}"
```

### 3. Verify
The `non_us_routing.py` module will automatically:
- Detect Aster as geo-blocked platform
- Route requests through configured proxy
- Log proxy usage

---

## Testing Non-US Routing

```python
from cloud_trader.non_us_routing import get_non_us_router

router = get_non_us_router()

# Check if Aster needs proxy
if router.is_platform_blocked("aster"):
    proxy = router.get_proxy_config("aster")
    print(f"Aster will use proxy: {proxy}")
```

---

## Current Status

⚠️ **NO PROXY CONFIGURED** - Aster will be blocked in current us-central1 deployment!

**Required Action:**
Choose Option 1, 2, or 3 above to enable Aster trading.

---

## Recommendation

**For Immediate Use:** Option 1 (HTTP Proxy)
- Quick to set up (5 minutes)
- Works with current deployment
- Just need proxy credentials

**For Production:** Option 2 (Multi-Region)
- Most reliable
- No third-party dependencies
- Better latency for European markets

---

## Environment Variables

```bash
# Option 1: Proxy
HTTP_PROXY=http://proxy-server:port
HTTPS_PROXY=http://proxy-server:port

# Option 2: Multi-region endpoint
ASTER_NON_US_ENDPOINT=https://sapphire-aster-eu-xyz.run.app
```
