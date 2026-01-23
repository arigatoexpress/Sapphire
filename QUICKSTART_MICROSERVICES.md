# Sapphire V2 Microservices - Quick Start Guide

## TL;DR

```bash
# 1. Setup PubSub infrastructure
cd /path/to/sapphire_repo
export GCP_PROJECT_ID="your-project-id"
./scripts/setup-pubsub.sh

# 2. Deploy all services
gcloud builds submit --config=cloudbuild_microservices.yaml

# 3. Verify deployment
gcloud run services list --region=europe-west1

# 4. Access dashboard
WEB_URL=$(gcloud run services describe sapphire-web --region=europe-west1 --format="value(status.url)")
open "$WEB_URL"
```

## What You Get

After deployment, you'll have **6 Cloud Run services** running in `europe-west1`:

| Service            | URL                                | Purpose                    |
|--------------------|------------------------------------|----------------------------|
| `sapphire-hl`      | https://sapphire-hl-xxx.a.run.app  | Hyperliquid trading        |
| `sapphire-lighter` | https://sapphire-lighter-xxx...    | Lighter.xyz trading        |
| `sapphire-drift`   | https://sapphire-drift-xxx...      | Drift Protocol trading     |
| `sapphire-aster`   | https://sapphire-aster-xxx...      | AsterDEX trading           |
| `sapphire-symphony`| https://sapphire-symphony-xxx...   | Agent orchestration        |
| `sapphire-web`     | https://sapphire-web-xxx...        | **Dashboard (use this!)** |

## Verification Steps

### 1. Check Services are Running

```bash
gcloud run services list --region=europe-west1
```

Expected output:
```
SERVICE             REGION        URL                                    LAST DEPLOYED
sapphire-hl         europe-west1  https://sapphire-hl-xxx.a.run.app      2026-01-19
sapphire-lighter    europe-west1  https://sapphire-lighter-xxx...        2026-01-19
sapphire-drift      europe-west1  https://sapphire-drift-xxx...          2026-01-19
sapphire-aster      europe-west1  https://sapphire-aster-xxx...          2026-01-19
sapphire-symphony   europe-west1  https://sapphire-symphony-xxx...       2026-01-19
sapphire-web        europe-west1  https://sapphire-web-xxx...            2026-01-19
```

All should show status `Ready`.

### 2. Verify Event Flow

Wait 60 seconds for services to send heartbeats, then:

```bash
gcloud pubsub subscriptions pull sapphire-web-events --limit=5
```

Expected output:
```
┌──────────────────────────────────────┬──────────────┬────────────────┐
│ DATA                                 │ MESSAGE_ID   │ PUBLISH_TIME   │
├──────────────────────────────────────┼──────────────┼────────────────┤
│ {"event_type":"heartbeat",...}       │ 123456789    │ 2026-01-19...  │
│ {"event_type":"heartbeat",...}       │ 123456790    │ 2026-01-19...  │
└──────────────────────────────────────┴──────────────┴────────────────┘
```

If you see `HEARTBEAT` events, PubSub is working! ✅

### 3. Test Dashboard API

```bash
WEB_URL=$(gcloud run services describe sapphire-web --region=europe-west1 --format="value(status.url)")

# Test fleet summary endpoint
curl -s "$WEB_URL/api/fleet/summary" | jq

# Expected output:
{
  "total_equity": 12500.45,
  "total_positions": 8,
  "services": {
    "sapphire-hl": {
      "balance": 5000.12,
      "positions": 3,
      "health": {"status": "healthy", ...}
    },
    ...
  },
  "timestamp": 1706123471.92
}
```

If you see service data, aggregation is working! ✅

### 4. Check Logs

```bash
# View logs for a specific service
gcloud logging read "resource.labels.service_name=sapphire-hl" \
    --limit=20 \
    --format=json

# Look for service identity confirmation
gcloud logging read "resource.labels.service_name=sapphire-hl AND textPayload=~'Service Identity'" \
    --limit=1

# Expected:
# 💧 [sapphire-hl] 🆔 Service Identity: ServiceIdentity(service_type=HYPERLIQUID, ...)
```

### 5. Open Dashboard

```bash
open "$WEB_URL"
```

You should see:
- ✅ **Total Equity**: Sum of all service balances
- ✅ **Positions**: From all platforms (marked with service name)
- ✅ **Health Indicators**: 🟢 green for healthy services
- ✅ **Per-Service Breakdown**: Individual balances and position counts

## Troubleshooting

### Problem: Dashboard shows $0 equity

**Diagnosis:**
```bash
# Check if trading services are publishing events
gcloud pubsub subscriptions pull sapphire-web-events --limit=10
```

**If no messages**: Trading services aren't publishing
- Check `ENABLE_PUBSUB=true` in service env vars
- Verify IAM permissions (pubsub.publisher role)

**If messages exist**: Aggregator might not be processing
- Check sapphire-web logs for errors:
  ```bash
  gcloud logging read "resource.labels.service_name=sapphire-web AND severity>=ERROR"
  ```

### Problem: Service shows "down" status

**Diagnosis:**
```bash
# Check service logs
gcloud logging read "resource.labels.service_name=sapphire-hl" --limit=50

# Check if service is actually running
gcloud run services describe sapphire-hl --region=europe-west1 --format="value(status.conditions)"
```

**Common causes:**
- Crash loop (check logs for errors)
- Missing credentials (ASTER_API_KEY, HL_SECRET_KEY)
- Network timeout (increase timeout in Cloud Run config)

### Problem: Positions not showing up

**Check:**
1. Service is actually trading (check logs for "Trade executed")
2. `POSITION_OPENED` events are published (check PubSub)
3. Aggregator is processing events (check sapphire-web logs)

```bash
# Pull position events specifically
gcloud pubsub subscriptions pull sapphire-web-events --limit=20 | grep POSITION
```

## Configuration Reference

### Environment Variables

Each service needs these env vars (set via `cloudbuild_microservices.yaml`):

**Trading Services (hl, lighter, drift, aster):**
```
ENABLE_{PLATFORM}=true      # One platform per service
ENABLE_PUBSUB=true          # Enable event publishing
GCP_PROJECT_ID={project}    # Your GCP project ID
ASTER_API_KEY=...           # Platform credentials
HL_SECRET_KEY=...
SOLANA_PRIVATE_KEY=...
LOG_LEVEL=INFO
```

**Web Service:**
```
SERVE_FRONTEND=true
ENABLE_PUBSUB=true
GCP_PROJECT_ID={project}
# All ENABLE_* flags = false
```

### PubSub Resources

- **Topic**: `projects/{project}/topics/sapphire-service-events`
- **Subscription**: `projects/{project}/subscriptions/sapphire-web-events`

To delete and recreate:
```bash
gcloud pubsub subscriptions delete sapphire-web-events
gcloud pubsub topics delete sapphire-service-events
./scripts/setup-pubsub.sh
```

## Monitoring

### Key Metrics to Watch

1. **Service Health**
   - Dashboard: Check health indicators (🟢/🟡/🔴)
   - Alert if any service is "down" for >5 minutes

2. **Event Processing Rate**
   - Cloud Console → Pub/Sub → Topic → Metrics
   - Should see steady flow of messages (>1/sec during trading)

3. **API Latency**
   - Cloud Console → Cloud Run → sapphire-web → Metrics
   - `/api/fleet/summary` should respond in <200ms

4. **Error Rate**
   - Cloud Console → Logging → Log Explorer
   - Query: `severity>=ERROR`
   - Should be near zero in steady state

### Alerting (Optional)

Set up alerts in Cloud Monitoring:

```yaml
# Example alert policy
displayName: "Sapphire Service Down"
conditions:
  - displayName: "Heartbeat age > 2 minutes"
    conditionThreshold:
      filter: 'metric.type="custom.googleapis.com/microservices/heartbeat_age"'
      comparison: COMPARISON_GT
      thresholdValue: 120
      duration: 180s
```

## Scaling

### Auto-Scaling (Default)

Services auto-scale from **0 to 1000 instances** based on:
- CPU utilization (target: 60%)
- Request concurrency (target: 80)

### Manual Scaling

To keep a service warm (avoid cold starts):

```bash
gcloud run services update sapphire-hl \
    --region=europe-west1 \
    --min-instances=1 \
    --max-instances=5
```

**Cost**: ~$10/month per warm instance

## Cost Estimation

Based on typical usage:

| Service       | Requests/day | Cost/month |
|---------------|--------------|------------|
| sapphire-hl   | 10,000       | $5         |
| sapphire-web  | 50,000       | $10        |
| PubSub        | 1M messages  | $15        |
| Firestore     | 100K writes  | $5         |
| **Total**     |              | **~$50**   |

**Cost Optimization:**
- Use `--min-instances=0` for low-traffic services
- Set `--max-instances=3` to cap scaling
- Enable request compression (`GZipMiddleware` already added)

## Rollback

If something goes wrong:

```bash
# Option 1: Rollback to previous revision
gcloud run services update-traffic sapphire-hl \
    --region=europe-west1 \
    --to-revisions=sapphire-hl-00012-abc=100

# Option 2: Disable microservices features
gcloud run services update sapphire-web \
    --region=europe-west1 \
    --set-env-vars="ENABLE_PUBSUB=false"

# Option 3: Revert to monolith
gcloud builds submit --config=cloudbuild.yaml  # Old config
```

## Next Steps

1. **Add Secrets**: Store API keys in Secret Manager (not env vars)
2. **Enable Monitoring**: Set up dashboards in Cloud Monitoring
3. **Load Testing**: Simulate high-volume trading
4. **Frontend Updates**: Integrate fleet endpoints (see `MICROSERVICES_ARCHITECTURE.md`)
5. **Backup Strategy**: Export Firestore data regularly

## Support

- **Architecture Details**: See `MICROSERVICES_ARCHITECTURE.md`
- **Full Refactoring Summary**: See `REFACTORING_SUMMARY.md`
- **Issues**: Check Cloud Run logs and PubSub metrics

---

**Quick Start Version**: 1.0
**Last Updated**: 2026-01-19
