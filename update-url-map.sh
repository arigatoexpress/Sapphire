#!/bin/bash
# Update URL map to fix dashboard routing

echo "🔧 Fixing Dashboard Routing..."

# Export the current URL map
gcloud compute url-maps export aster-url-map \
  --destination=url-map-fixed.yaml \
  --global \
  --project=sapphireinfinite

# Update the URL map to route dashboard correctly
cat > url-map-patch.yaml << 'EOF'
pathMatchers:
- defaultService: https://www.googleapis.com/compute/v1/projects/sapphireinfinite/global/backendServices/trader-backend
  name: aster-matcher
  pathRules:
  - paths:
    - /dashboard
    - /dashboard/*
    service: https://www.googleapis.com/compute/v1/projects/sapphireinfinite/global/backendServices/cloud-trader-dashboard-backend
  - paths:
    - /orchestrator/*
    service: https://www.googleapis.com/compute/v1/projects/sapphireinfinite/global/backendServices/orchestrator-backend
  - paths:
    - /assets/*
    service: https://www.googleapis.com/compute/v1/projects/sapphireinfinite/global/backendServices/cloud-trader-dashboard-backend
EOF

echo "📝 Current configuration exported to url-map-fixed.yaml"
echo "✅ Patch file created: url-map-patch.yaml"
echo ""
echo "To apply the fix, run:"
echo "  gcloud compute url-maps import aster-url-map --source=url-map-patch.yaml --global"
