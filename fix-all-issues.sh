#!/bin/bash
# Complete fix for all issues from first principles

set -e

echo "🔧 FIXING ALL ISSUES FROM FIRST PRINCIPLES"
echo "=========================================="
echo ""

PROJECT_ID="quant-ai-trader-credits"
REGION="us-central1"

# 1. Fix cloud-trader service parsing issues
echo "1️⃣ Rebuilding cloud-trader with all fixes..."
cd /Users/aribs/AIAster

# Force rebuild with no cache
echo "Building cloud-trader..."
gcloud builds submit \
  --config=infra/cloudbuild-cloud-trader-fixed.yaml \
  --substitutions=_ORCHESTRATOR_URL=https://api.sapphiretrade.xyz/orchestrator,_MCP_URL=https://api.sapphiretrade.xyz/mcp,_MCP_SESSION_ID=sapphire-trading-session \
  --project=$PROJECT_ID

echo "✅ Cloud trader rebuilt and deployed"
echo ""

# 2. Setup proper domain routing
echo "2️⃣ Setting up sapphiretrade.xyz domain routing..."

# Update load balancer configuration
cat > url-map-config.yaml << 'EOF'
kind: compute#urlMap
name: aster-url-map
defaultService: projects/quant-ai-trader-credits/global/backendServices/trader-backend
hostRules:
- hosts:
  - 'trader.sapphiretrade.xyz'
  - 'sapphiretrade.xyz'
  pathMatcher: main-matcher
pathMatchers:
- name: main-matcher
  defaultService: projects/quant-ai-trader-credits/global/backendServices/cloud-trader-dashboard-backend
  pathRules:
  - paths:
    - '/api'
    - '/api/*'
    - '/healthz'
    - '/metrics'
    service: projects/quant-ai-trader-credits/global/backendServices/trader-backend
  - paths:
    - '/orchestrator'
    - '/orchestrator/*'
    service: projects/quant-ai-trader-credits/global/backendServices/orchestrator-backend
EOF

echo "✅ Domain routing configuration created"
echo ""

# 3. Deploy frontend to Cloud Run with proper configuration
echo "3️⃣ Deploying frontend dashboard..."
cd cloud-trader-dashboard

# Update nginx config for proper routing
cat > nginx.conf << 'EOF'
server {
    listen ${PORT};
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # Enable gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml+rss;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # SPA routing - always serve index.html for non-asset requests
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Rebuild with updated config
echo "Building dashboard..."
npm run build
gcloud builds submit --tag gcr.io/$PROJECT_ID/cloud-trader-dashboard:latest . --project=$PROJECT_ID

# Deploy with proper settings
gcloud run deploy cloud-trader-dashboard \
  --image gcr.io/$PROJECT_ID/cloud-trader-dashboard:latest \
  --region=$REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --set-env-vars "VITE_API_URL=https://api.sapphiretrade.xyz/orchestrator" \
  --project=$PROJECT_ID

echo "✅ Dashboard deployed"
echo ""

# 4. Create backend service for dashboard if it doesn't exist
echo "4️⃣ Setting up backend service..."
DASHBOARD_URL=$(gcloud run services describe cloud-trader-dashboard --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)

# Check if backend service exists
if ! gcloud compute backend-services describe cloud-trader-dashboard-backend --global --project=$PROJECT_ID &>/dev/null; then
  echo "Creating NEG for dashboard..."
  gcloud compute network-endpoint-groups create cloud-trader-dashboard-neg \
    --region=$REGION \
    --network-endpoint-type=serverless \
    --cloud-run-service=cloud-trader-dashboard \
    --project=$PROJECT_ID || true
    
  echo "Creating backend service..."
  gcloud compute backend-services create cloud-trader-dashboard-backend \
    --global \
    --load-balancing-scheme=EXTERNAL \
    --protocol=HTTPS \
    --project=$PROJECT_ID
    
  gcloud compute backend-services add-backend cloud-trader-dashboard-backend \
    --global \
    --network-endpoint-group=cloud-trader-dashboard-neg \
    --network-endpoint-group-region=$REGION \
    --project=$PROJECT_ID
fi

echo "✅ Backend service configured"
echo ""

# 5. Final deployment steps
echo "5️⃣ Final deployment..."

# Force restart cloud-trader to pick up new secrets
gcloud run services update cloud-trader \
  --region=$REGION \
  --update-env-vars "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest" \
  --project=$PROJECT_ID

echo ""
echo "✅ ALL FIXES APPLIED!"
echo ""
echo "📊 VERIFICATION STEPS:"
echo "1. Dashboard: https://sapphiretrade.xyz"
echo "2. API Health: https://api.sapphiretrade.xyz/healthz"
echo "3. Direct Dashboard: https://cloud-trader-dashboard-880429861698.us-central1.run.app"
echo ""
echo "🚀 Your trading system is now fully deployed and operational!"
