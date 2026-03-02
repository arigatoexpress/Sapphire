# Command Deck v3.0 Deployment Guide

## Local Testing (Recommended First Step)

```bash
cd services/workbench/command_deck
./run_local.sh
```

Then test:
- http://localhost:8082/health
- http://localhost:8082/api/dashboard
- http://localhost:8082/api/status

## Cloud Run Deployment

### Option 1: Deploy via Cloud Console (Easiest)

1. Go to [Cloud Run Console](https://console.cloud.google.com/run?project=sapphire-479610)
2. Click "Create Service"
3. Select "Continuously deploy new revisions from a source repository"
4. Connect your GitHub repo and select the `services/workbench/command_deck` folder
5. Set environment variables:
   ```
   PM_HUB_URL=https://agentic-pm-hub-267358751314.us-central1.run.app
   GATEWAY_URL=https://sapphire-gateway-267358751314.us-central1.run.app
   ENABLE_AUTH=true
   AUTH_USERNAME=sapphire
   AUTH_PASSWORD=your-secure-password
   ```
6. Deploy

### Option 2: Deploy via gcloud CLI

If you have proper permissions:

```bash
gcloud run deploy sapphire-command-deck \
  --source . \
  --region us-central1 \
  --project sapphire-479610 \
  --set-env-vars "PM_HUB_URL=https://agentic-pm-hub-267358751314.us-central1.run.app,GATEWAY_URL=https://sapphire-gateway-267358751314.us-central1.run.app,ENABLE_AUTH=true" \
  --memory 512Mi \
  --timeout 60 \
  --max-instances 2 \
  --allow-unauthenticated
```

### Option 3: Build and Push Container Manually

If Cloud Build has permission issues:

```bash
# Build locally
docker build -t gcr.io/sapphire-479610/sapphire-command-deck:v3.0 .

# Push (requires gcloud docker auth)
gcloud auth configure-docker
docker push gcr.io/sapphire-479610/sapphire-command-deck:v3.0

# Deploy from container
gcloud run deploy sapphire-command-deck \
  --image gcr.io/sapphire-479610/sapphire-command-deck:v3.0 \
  --region us-central1 \
  --project sapphire-479610 \
  --set-env-vars "PM_HUB_URL=https://agentic-pm-hub-267358751314.us-central1.run.app,GATEWAY_URL=https://sapphire-gateway-267358751314.us-central1.run.app" \
  --memory 512Mi
```

### Option 4: Deploy to Pi (rari1)

For local network access:

```bash
# SSH to rari1
ssh rari@100.120.191.1

# Clone/pull latest
cd /opt/sapphire
git pull origin main

# Install dependencies
pip install -r services/workbench/command_deck/requirements.txt

# Run with systemd or screen
export GCP_PROJECT=sapphire-479610
export PM_HUB_URL=https://agentic-pm-hub-267358751314.us-central1.run.app
export ENABLE_AUTH=true
cd services/workbench/command_deck
python3 app.py
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT` | Yes | `sapphire-479610` | GCP Project ID |
| `PM_HUB_URL` | Yes | - | AI PM Manager URL |
| `GATEWAY_URL` | No | (set) | API Gateway URL |
| `ENABLE_AUTH` | No | `true` | Enable basic auth |
| `AUTH_USERNAME` | No | `sapphire` | Auth username |
| `AUTH_PASSWORD` | No | `alpha2024` | Auth password |
| `CACHE_DURATION` | No | `10` | Cache TTL in seconds |

## Testing After Deployment

```bash
# Get the service URL
URL=$(gcloud run services describe sapphire-command-deck --region us-central1 --format 'value(status.url)')

echo "Testing $URL..."

# Health check
curl -s $URL/health | jq .

# Dashboard (requires auth if enabled)
curl -s -u sapphire:alpha2024 $URL/api/dashboard | jq .

# PM Integration
curl -s -u sapphire:alpha2024 $URL/api/pm/projects | jq .
curl -s -u sapphire:alpha2024 $URL/api/pm/tasks | jq .

# Terminal commands
curl -s -X POST -u sapphire:alpha2024 \
  -H "Content-Type: application/json" \
  -d '{"command":"status"}' \
  $URL/api/terminal | jq .
```

## Troubleshooting

### Permission Denied (Cloud Build)
- Use Cloud Console UI instead
- Or grant Storage Admin role to compute service account

### Firestore Connection Failed
- Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set
- Or run `gcloud auth application-default login`

### PM Hub Unreachable
- Check PM Hub is deployed: `https://agentic-pm-hub-267358751314.us-central1.run.app/health`
- Verify URL in environment variables

### Gateway Unreachable
- Check Gateway status
- Some endpoints will still work without Gateway

## Post-Deployment URL

After successful deployment, your Command Deck will be available at:

```
https://sapphire-command-deck-267358751314.us-central1.run.app
```

Or if using custom domain:
```
https://command.sapphirealpha.xyz
```
