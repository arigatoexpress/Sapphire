#!/bin/bash
# Comprehensive deployment test script

set -e

echo "🚀 FULL DEPLOYMENT TEST"
echo "======================="
echo ""

# Direct service URLs
CLOUD_TRADER_URL="https://cloud-trader-cfxefrvooa-uc.a.run.app"
DASHBOARD_URL="https://cloud-trader-dashboard-880429861698.us-central1.run.app"

echo "1️⃣ Testing Cloud Trader API directly:"
echo "--------------------------------------"
echo "Root endpoint:"
curl -s $CLOUD_TRADER_URL/api | jq . 2>/dev/null || echo "Response: $(curl -s $CLOUD_TRADER_URL/api)"
echo ""
echo "Health endpoint:"
curl -s $CLOUD_TRADER_URL/api/healthz | jq . 2>/dev/null || echo "Response: $(curl -s $CLOUD_TRADER_URL/api/healthz)"
echo ""

echo "2️⃣ Testing Dashboard directly:"
echo "------------------------------"
curl -s -I $DASHBOARD_URL | grep -E "HTTP|content-type"
echo ""

echo "3️⃣ Testing through Load Balancer:"
echo "---------------------------------"
echo "Frontend (sapphiretrade.xyz):"
curl -s -I https://sapphiretrade.xyz | grep -E "HTTP|content-type"
echo ""
echo "Dashboard content:"
curl -s https://sapphiretrade.xyz | grep -o '<title>.*</title>' | head -1
echo ""

echo "4️⃣ Testing API subdomain:"
echo "------------------------"
echo "Should route to cloud-trader:"
curl -s https://api.sapphiretrade.xyz/api | jq . 2>/dev/null || echo "Response: $(curl -s https://api.sapphiretrade.xyz/api)"
echo ""

echo "5️⃣ Checking Trading Status:"
echo "---------------------------"
# Check if live trading is enabled
echo "Trading configuration:"
gcloud run services describe cloud-trader \
  --region=us-central1 \
  --format="table(spec.template.spec.containers[0].env[name='ENABLE_PAPER_TRADING'].value)" \
  --project=sapphireinfinite | grep -v NAME | xargs echo "ENABLE_PAPER_TRADING:"

echo ""
echo "Recent trading activity:"
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="cloud-trader" AND (textPayload:"order" OR textPayload:"trade" OR textPayload:"position")' \
  --limit=5 \
  --format="table(timestamp.date('%H:%M:%S'), textPayload)" \
  --project=sapphireinfinite 2>/dev/null | head -10

echo ""
echo "6️⃣ Load Balancer Configuration:"
echo "-------------------------------"
echo "URL map host rules:"
gcloud compute url-maps describe aster-url-map \
  --global \
  --format="table(hostRules[].hosts.flatten())" \
  --project=sapphireinfinite

echo ""
echo "✅ Test complete!"
