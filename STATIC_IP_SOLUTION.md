# Static IP Configuration - Final Solution

## Current Status

### ✅ Cloud NAT is ALREADY WORKING!

Your Sapphire V2 service **is already using Cloud NAT** with a static IP address.

**Current Static IP:** `35.238.91.210`

This IP is configured via:
- **NAT Name:** `sapphire-nat-us`
- **Router:** `sapphire-router-us`
- **VPC:** `sapphire-net`
- **Region:** `us-central1`

---

## What Happened

1. **Existing Infrastructure** (before our deployment):
   - VPC: `sapphire-net`
   - VPC Connector: `sapphire-conn-us` → uses `sapphire-net`
   - Cloud NAT: `sapphire-nat-us` → IP: `35.238.91.210`
   - ✅ This was already working!

2. **New Infrastructure** (what we created):
   - VPC: `sapphire-vpc`
   - Cloud NAT: `sapphire-nat` → IP: `34.41.44.213`
   - ⚠️ But the VPC connector still uses the OLD VPC (`sapphire-net`)

3. **Result:**
   - Cloud Run → VPC Connector (`sapphire-conn-us`) → `sapphire-net` → NAT IP: `35.238.91.210`
   - The new VPC and IP we created (`34.41.44.213`) are not being used

---

## Solution: Use Existing IP

### ✅ RECOMMENDED: Whitelist the Current Working IP

**Action Required:**
Add this IP to your Aster API whitelist:
```
35.238.91.210
```

This IP is:
- ✅ Already configured with Cloud NAT
- ✅ Already being used by your Cloud Run service
- ✅ Static and won't change
- ✅ Working correctly (the -2015 errors will stop once whitelisted)

---

## Alternative: Switch to New IP (Optional)

If you prefer to use the new IP `34.41.44.213` instead, follow these steps:

### Step 1: Free up the new IP
```bash
# Delete NAT on new router
gcloud compute routers nats delete sapphire-nat \
  --router=sapphire-nat-router \
  --region=us-central1 \
  --project=sapphire-479610 \
  --quiet
```

### Step 2: Update existing NAT to use new IP
```bash
# Update existing NAT to use the new static IP
gcloud compute routers nats update sapphire-nat-us \
  --router=sapphire-router-us \
  --region=us-central1 \
  --project=sapphire-479610 \
  --nat-external-ip-pool=sapphire-static-ip
```

### Step 3: Whitelist new IP in Aster
```
34.41.44.213
```

### Step 4: Restart Cloud Run service
```bash
gcloud run services update sapphire-v2 \
  --region=us-central1 \
  --project=sapphire-479610 \
  --no-traffic
```

---

## Verification

### Check which IP is currently being used:
```bash
gcloud compute routers nats describe sapphire-nat-us \
  --router=sapphire-router-us \
  --region=us-central1 \
  --project=sapphire-479610 \
  --format="value(natIps)"
```

### Monitor Aster API calls:
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="sapphire-v2" AND textPayload=~"2015"' \
  --limit=10 \
  --project=sapphire-479610 \
  --format="value(textPayload)"
```

Once the IP is whitelisted, the `-2015` errors should disappear.

---

## Summary

**Current Situation:**
- ✅ Cloud NAT is working
- ✅ Static IP exists: `35.238.91.210`
- ⚠️ IP not whitelisted in Aster yet

**Recommended Action:**
Whitelist `35.238.91.210` in your Aster API settings

**Result:**
- ✅ Aster API errors (-2015) will stop
- ✅ System will work with existing infrastructure
- ✅ No additional configuration needed

---

## IP Addresses Reference

| Purpose | IP Address | Status | Action |
|---------|------------|--------|--------|
| **Current NAT IP** (sapphire-net) | `35.238.91.210` | ✅ Active | **WHITELIST THIS** |
| New NAT IP (sapphire-vpc) | `34.41.44.213` | ⚠️ Not in use | Optional replacement |

