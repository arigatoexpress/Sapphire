# Agent Symphony Quick Reference

## 🚀 Deployment Commands

### Backend (Cloud Trader)
```bash
gcloud builds submit --config cloudbuild_trader.yaml . --project sapphire-479610
gcloud run deploy cloud-trader --image gcr.io/sapphire-479610/cloud-trader \
  --platform managed --region northamerica-northeast1 \
  --vpc-connector sapphire-conn --vpc-egress all-traffic \
  --allow-unauthenticated --project sapphire-479610
```

### Symphony Conductor
```bash
gcloud builds submit --config cloudbuild_conductor.yaml . --project sapphire-479610
gcloud run deploy symphony-conductor --image gcr.io/sapphire-479610/symphony-conductor \
  --platform managed --region northamerica-northeast1 \
  --allow-unauthenticated --project sapphire-479610
```

### Frontend (Dashboard)
```bash
cd trading-dashboard
npm run build
firebase deploy --only hosting --project sapphire-479610
```

## 🔍 Debugging Commands

### View Logs
```bash
# Cloud Trader logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cloud-trader" \
  --limit 50 --format "value(textPayload)" --order desc

# Search for specific patterns
gcloud logging read "resource.type=cloud_run_revision AND textPayload:\"NEW TRADE\"" \
  --limit 20 --format "value(textPayload)" --order desc
```

### Check Service Status
```bash
gcloud run services describe cloud-trader --region northamerica-northeast1 \
  --format "value(status.url,status.traffic[0].revisionName)"
```

### View Secrets
```bash
gcloud secrets list --project sapphire-479610
gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN --project sapphire-479610
```

## 📊 Monitoring URLs

| Service | URL |
|---------|-----|
| Dashboard | https://sapphiretrade.xyz |
| Cloud Trader API | https://cloud-trader-267358751314.northamerica-northeast1.run.app |
| GCP Console | https://console.cloud.google.com/run?project=sapphire-479610 |
| Cloud Build | https://console.cloud.google.com/cloud-build/builds?project=sapphire-479610 |

## 🛠️ Local Development

```bash
# Start backend locally
python -m cloud_trader.api

# Start frontend locally
cd trading-dashboard && npm run dev

# Run with environment
source .env && python -m cloud_trader.api
```

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GCP_PROJECT_ID` | ✅ | `sapphire-479610` |
| `ASTER_API_KEY` | ✅ | Exchange API key |
| `ASTER_SECRET_KEY` | ✅ | Exchange secret |
| `GEMINI_API_KEY` | ✅ | AI analysis |
| `REDIS_URL` | ✅ | State cache |
| `DATABASE_URL` | ✅ | Trade history |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | Notifications |
| `TELEGRAM_CHAT_ID` | ⚠️ | Notification target |

## 🐛 Common Issues

| Issue | Solution |
|-------|----------|
| IP Restriction Error | Verify VPC connector is attached |
| Build Timeout | Add `.gcloudignore` to exclude venv/node_modules |
| Telegram Silent | Check bot token, ensure user did /start |
| No New Trades | Check confidence threshold (needs >= 0.65) |
| WebSocket Fails | Verify VITE_API_URL in .env.production |
