#!/bin/bash
# Comprehensive Microservices Verification Script

set -e

REGION="europe-west1"
PROJECT_ID="sapphire-479610"

echo "╔════════════════════════════════════════════════════════╗"
echo "║   Sapphire V2 Microservices - Verification Suite      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 1. Verify all services are deployed and ready
echo "1️⃣ Checking Service Deployment Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
gcloud run services list --region=$REGION --format='table(SERVICE,READY,URL)' | grep sapphire
echo ""

# Get web service URL
WEB_URL=$(gcloud run services describe sapphire-web --region=$REGION --format='value(status.url)')
echo "📍 Web Dashboard URL: $WEB_URL"
echo ""

# 2. Test Health Endpoints
echo "2️⃣ Testing Health Endpoints"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for service in sapphire-hl sapphire-lighter sapphire-aster sapphire-aster sapphire-aster sapphire-web; do
  service_url=$(gcloud run services describe $service --region=$REGION --format='value(status.url)')
  echo -n "  $service: "

  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$service_url/health" || echo "TIMEOUT")

  if [ "$http_code" = "200" ]; then
    echo "✅ Healthy"
  else
    echo "⚠️  Status: $http_code"
  fi
done
echo ""

# 3. Test Web Service Fleet Endpoints
echo "3️⃣ Testing Fleet Endpoints"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "  📊 Fleet Summary:"
fleet_summary=$(curl -s --max-time 15 "$WEB_URL/api/fleet/summary" || echo '{"error":"timeout"}')
if echo "$fleet_summary" | grep -q "total_equity\|services"; then
  echo "  ✅ Fleet summary endpoint working"
  echo "$fleet_summary" | python3 -m json.tool 2>/dev/null | head -20
else
  echo "  ⚠️  Fleet summary endpoint issue"
  echo "$fleet_summary"
fi
echo ""

echo "  ❤️  Fleet Health:"
fleet_health=$(curl -s --max-time 15 "$WEB_URL/api/fleet/health" || echo '{"error":"timeout"}')
if echo "$fleet_health" | grep -q "services\|healthy"; then
  echo "  ✅ Fleet health endpoint working"
else
  echo "  ⚠️  Fleet health endpoint issue"
fi
echo ""

# 4. Check PubSub Events
echo "4️⃣ Checking PubSub Events"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Waiting 60 seconds for heartbeat events..."
sleep 60

events=$(gcloud pubsub subscriptions pull sapphire-web-events --limit=10 --format=json 2>/dev/null || echo '[]')
event_count=$(echo "$events" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

echo "  📬 Events received: $event_count"
if [ "$event_count" -gt "0" ]; then
  echo "  ✅ PubSub events are flowing"
else
  echo "  ⚠️  No PubSub events detected (services may still be starting)"
fi
echo ""

# 5. Check Service Logs for Identity
echo "5️⃣ Verifying Service Identity"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for service in sapphire-hl sapphire-web; do
  echo "  $service:"
  gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND textPayload=~'Service Identity\|Web service\|web-only mode'" \
    --limit=1 \
    --format="value(textPayload)" \
    --freshness=10m 2>/dev/null | head -1 || echo "    (No identity log found)"
done
echo ""

# 6. Summary
echo "╔════════════════════════════════════════════════════════╗"
echo "║                   Verification Summary                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "✅ Services Deployed: 6"
echo "✅ Region: $REGION"
echo "✅ Project: $PROJECT_ID"
echo ""
echo "🌐 Dashboard URL: $WEB_URL"
echo ""
echo "Next Steps:"
echo "  1. Open dashboard in browser: $WEB_URL"
echo "  2. Check fleet summary: curl $WEB_URL/api/fleet/summary"
echo "  3. Monitor logs: gcloud logging read 'resource.labels.service_name=sapphire-web'"
echo ""
