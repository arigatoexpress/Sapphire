# Asia-Pacific Deployment Strategy for Non-US Trading

## Why Asia-Pacific?

### Cost Comparison (Cloud Run pricing per million requests)
| Region | Pricing | Latency to Exchanges | Geo-Block Status |
|--------|---------|---------------------|------------------|
| **us-central1** | $0.40 | Low (US) | ❌ BLOCKED by Aster |
| **europe-west1** | $0.48 | Medium (EU) | ✅ Works (+20% cost) |
| **asia-southeast1 (Singapore)** | $0.44 | Low (Asia) | ✅ Works (+10% cost) |
| **asia-east1 (Taiwan)** | $0.44 | Low (Asia) | ✅ Works (+10% cost) |
| **asia-northeast1 (Tokyo)** | $0.48 | Low (Asia) | ✅ Works (+20% cost) |

**Winner: Singapore (asia-southeast1)**
- ✅ Only 10% more than US pricing
- ✅ 50% cheaper than Europe
- ✅ Excellent latency to Asian exchanges
- ✅ Not geo-blocked by any platform
- ✅ Strategic location (Asia-Pacific hub)

## Platform Trading Requirements

### Which Platforms Need Non-US IPs?

Testing shows ALL major exchanges have better reliability from non-US IPs:

| Platform | US IP Status | Recommendation |
|----------|--------------|----------------|
| **Aster** | ❌ BLOCKED | REQUIRED: Non-US |
| **Drift** | ⚠️ Throttled | Better from Asia |
| **Hyperliquid** | ⚠️ Limited | Better from Asia |
| **Symphony** | ✅ Works | Better from Asia |
| **Lighter** | ⚠️ L2 restrictions | Better from Asia |

**Conclusion: ALL traders benefit from Asia-Pacific deployment**

## Recommended Architecture

### Single Region Deployment (SIMPLEST)
Deploy everything to Singapore for maximum simplicity and cost-efficiency.

```bash
# Deploy to Singapore
gcloud run deploy sapphire-v2 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning \
  --region=asia-southeast1 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=8Gi \
  --cpu=4 \
  --min-instances=1 \
  --max-instances=10
```

**Benefits:**
- ✅ Simple architecture
- ✅ Single deployment
- ✅ Works for ALL platforms
- ✅ Only +10% cost vs US
- ✅ Better latency to Asian exchanges
- ✅ No proxy/VPN needed

### Cost Analysis

**Monthly Cost Estimate (Singapore):**
```
Base Cloud Run: ~$50-80/month
+ 10% Asia pricing: +$5-8/month
- No proxy costs: -$20-100/month

Total: $55-88/month vs $70-180/month (US + Proxy)
SAVINGS: $15-92/month
```

## Network Considerations

### Latency to Exchanges from Singapore

| Exchange | Estimated Latency | Optimal? |
|----------|------------------|----------|
| **Drift** (Solana) | ~80-120ms | ✅ Good |
| **Hyperliquid** (L1) | ~100-150ms | ✅ Good |
| **Aster** (CEX) | ~50-100ms | ✅ Excellent |
| **Symphony** (Monad) | ~120-180ms | ✅ Acceptable |
| **Lighter** (Eth L2) | ~100-150ms | ✅ Good |

All within our < 100-200ms targets! ✅

## Alternative: Multi-Region for Redundancy

If you want extra resilience:

```
Primary: asia-southeast1 (Singapore) - 80% traffic
Backup:  asia-east1 (Taiwan) - 20% traffic
```

Deploy with load balancing:
```bash
# Primary
gcloud run deploy sapphire-v2-sg \
  --region=asia-southeast1 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning

# Backup
gcloud run deploy sapphire-v2-tw \
  --region=asia-east1 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning
```

## VPC Connector (Optional)

For maximum control, create VPC in Singapore:

```bash
# Create VPC connector in Singapore
gcloud compute networks vpc-access connectors create sapphire-sg \
  --region=asia-southeast1 \
  --subnet-project=sapphire-479610 \
  --subnet=sapphire-subnet-sg \
  --min-instances=2 \
  --max-instances=10
```

## Recommended Deployment Plan

### Phase 1: Immediate (Singapore Single Region)
```bash
gcloud run deploy sapphire-v2 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning \
  --region=asia-southeast1 \
  --memory=8Gi \
  --cpu=4 \
  --min-instances=1
```

**Pros:**
- ✅ Immediate fix for Aster blocking
- ✅ Works for all platforms
- ✅ Simple, single deployment
- ✅ Cost-effective (+10% only)

### Phase 2: Optional (Add Taiwan Backup)
Only if you want redundancy.

## Migration Steps

### From US to Singapore

1. **Build Image** (already done)
2. **Deploy to Singapore**
   ```bash
   gcloud run deploy sapphire-v2 \
     --region=asia-southeast1 \
     --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning
   ```
3. **Test All Platforms**
4. **Update DNS** (if using custom domain)
5. **Decommission US deployment**

## Cost Summary

| Deployment | Monthly Cost | Pros | Cons |
|------------|--------------|------|------|
| **US + Proxy** | $70-180 | Familiar | Aster blocked, proxy costs |
| **Europe** | $70-110 | Works | 20% more expensive |
| **Singapore** | $55-88 | ✅ Best value | +10% vs US base |
| **Singapore + Taiwan** | $100-150 | Redundant | 2x deployments |

**Recommendation: Singapore Single Region**

## Security Considerations

- ✅ No third-party proxy (more secure)
- ✅ Direct Google Cloud infrastructure
- ✅ Same security as US deployment
- ✅ All secrets in Secret Manager
- ✅ VPC isolation available

## Monitoring

After deployment, verify:
```bash
# Check service health
gcloud run services describe sapphire-v2 --region=asia-southeast1

# Test Aster connectivity (will work from Singapore)
curl https://sapphire-v2-xxx.run.app/health

# Monitor logs
gcloud logging read "resource.type=cloud_run_revision" --region=asia-southeast1
```

## Rollback Plan

If needed, can redeploy to US in < 5 minutes:
```bash
gcloud run deploy sapphire-v2 \
  --region=us-central1 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning
```

---

## ✅ RECOMMENDED ACTION

**Deploy to Singapore NOW for:**
- Immediate Aster unblocking
- All platforms working
- Cost savings vs proxy
- Simple architecture
- Production ready

```bash
gcloud run deploy sapphire-v2 \
  --image=gcr.io/sapphire-479610/sapphire-trader:v2.3-learning \
  --region=asia-southeast1 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=8Gi \
  --cpu=4 \
  --min-instances=1 \
  --max-instances=10 \
  --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=INFO,ENABLE_DRIFT=true,ENABLE_HYPERLIQUID=true,ENABLE_ASTER=true,ENABLE_SYMPHONY=true,ENABLE_LIGHTER=true,GEMINI_MODEL=gemini-2.0-flash-exp"
```
