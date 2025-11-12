#!/bin/bash
# Fix deployment script - switch to correct load balancer and clean up

echo "=== Fixing Sapphire AI Trading Stack Deployment ==="

# Step 1: Update the HTTPS target proxy to use aster-url-map instead of sapphire-url-map
echo "1. Switching main domain to use Cloud Run dashboard..."
gcloud compute target-https-proxies update sapphire-https-proxy \
    --url-map=aster-url-map \
    --project=quant-ai-trader-credits

# Step 2: Clear CDN cache to force refresh
echo "2. Invalidating CDN cache..."
gcloud compute url-maps invalidate-cdn-cache aster-url-map \
    --path="/*" \
    --global \
    --project=quant-ai-trader-credits

# Step 3: Optionally disable CDN on the backend bucket (since we're not using it anymore)
echo "3. Updating backend configuration..."
gcloud compute backend-services update cloud-trader-dashboard-backend \
    --global \
    --enable-cdn \
    --cache-mode="FORCE_CACHE_ALL" \
    --default-ttl=10 \
    --max-ttl=60 \
    --project=quant-ai-trader-credits

# Step 4: Deploy latest backend with position closing fix
echo "4. Deploying backend with position closing fix..."
cd /Users/aribs/AIAster
./deploy_cloud_run.sh --skip-tests

# Step 5: Verify the deployment
echo "5. Verifying deployment..."
echo "Main site: https://sapphiretrade.xyz"
echo "API endpoint: https://api.sapphiretrade.xyz/healthz"
echo "Dashboard data: https://api.sapphiretrade.xyz/dashboard"

echo ""
echo "=== Next Steps ==="
echo "1. Wait 2-3 minutes for CDN invalidation"
echo "2. Open sapphiretrade.xyz in incognito/private browsing"
echo "3. You should see the new React dashboard, not the old one"
echo ""
echo "=== Cleanup Recommendations ==="
echo "- Delete duplicate services in sapphire-477307 project"
echo "- Remove old trading-dashboard service"
echo "- Delete sapphire-frontend-live bucket (no longer needed)"
echo "- Consider consolidating to single project"
