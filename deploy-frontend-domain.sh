#!/bin/bash
# Deploy frontend to sapphiretrade.xyz with proper routing

set -e

echo "🌐 SETTING UP SAPPHIRETRADE.XYZ FRONTEND"
echo "========================================"
echo ""

PROJECT_ID="quant-ai-trader-credits"
REGION="us-central1"

# 1. Create a proper URL map configuration
echo "1️⃣ Creating URL map configuration..."
cat > url-map-complete.yaml << 'EOF'
hostRules:
- hosts:
  - 'sapphiretrade.xyz'
  - 'www.sapphiretrade.xyz'  
  - 'trader.sapphiretrade.xyz'
  pathMatcher: frontend-matcher
- hosts:
  - 'api.sapphiretrade.xyz'
  pathMatcher: api-matcher
pathMatchers:
- name: frontend-matcher
  defaultService: projects/quant-ai-trader-credits/global/backendServices/cloud-trader-dashboard-backend
  pathRules:
  - paths:
    - '/api'
    - '/api/*'
    service: projects/quant-ai-trader-credits/global/backendServices/trader-backend
- name: api-matcher
  defaultService: projects/quant-ai-trader-credits/global/backendServices/trader-backend
  pathRules:
  - paths:
    - '/orchestrator'
    - '/orchestrator/*'
    service: projects/quant-ai-trader-credits/global/backendServices/orchestrator-backend
EOF

# 2. Check if NEG exists, create if not
echo "2️⃣ Setting up Network Endpoint Group..."
if ! gcloud compute network-endpoint-groups describe cloud-trader-dashboard-neg --region=$REGION --project=$PROJECT_ID &>/dev/null; then
  echo "Creating NEG..."
  gcloud compute network-endpoint-groups create cloud-trader-dashboard-neg \
    --region=$REGION \
    --network-endpoint-type=serverless \
    --cloud-run-service=cloud-trader-dashboard \
    --project=$PROJECT_ID
fi

# 3. Check if backend service exists, create if not  
echo "3️⃣ Setting up Backend Service..."
if ! gcloud compute backend-services describe cloud-trader-dashboard-backend --global --project=$PROJECT_ID &>/dev/null; then
  echo "Creating backend service..."
  gcloud compute backend-services create cloud-trader-dashboard-backend \
    --global \
    --load-balancing-scheme=EXTERNAL \
    --project=$PROJECT_ID
    
  gcloud compute backend-services add-backend cloud-trader-dashboard-backend \
    --global \
    --network-endpoint-group=cloud-trader-dashboard-neg \
    --network-endpoint-group-region=$REGION \
    --project=$PROJECT_ID
fi

# 4. Update the URL map
echo "4️⃣ Updating URL Map..."
# Export current config
gcloud compute url-maps export aster-url-map \
  --destination=url-map-current.yaml \
  --global \
  --project=$PROJECT_ID || true

# Apply the new configuration
echo "Applying new URL map configuration..."
# Note: You'll need to manually update the URL map in the console or via gcloud

echo ""
echo "✅ SETUP COMPLETE!"
echo ""
echo "📝 NEXT STEPS:"
echo "1. Go to: https://console.cloud.google.com/net-services/loadbalancing/advanced/urlMaps"
echo "2. Edit 'aster-url-map'"
echo "3. Update host rules as shown in url-map-complete.yaml"
echo "4. Save changes"
echo ""
echo "🔗 Your site will be available at:"
echo "   - https://sapphiretrade.xyz (frontend)"
echo "   - https://api.sapphiretrade.xyz (API)"
echo "   - https://api.sapphiretrade.xyz/orchestrator (orchestrator)"
echo ""

# 5. Test direct access
echo "5️⃣ Testing direct dashboard access..."
curl -s -I https://cloud-trader-dashboard-880429861698.us-central1.run.app | grep "HTTP" || true
echo ""
echo "Direct dashboard URL: https://cloud-trader-dashboard-880429861698.us-central1.run.app"
