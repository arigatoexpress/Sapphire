#!/bin/bash
# Quick status check for Sapphire V2 deployment

PROJECT_ID="sapphire-479610"
REGION="us-central1"
SERVICE_NAME="sapphire-v2"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Sapphire V2 Deployment Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check latest build
echo "📦 Latest Cloud Build:"
gcloud builds list --limit=1 --project=$PROJECT_ID --format="table(id,status,createTime,duration)"
echo ""

# Check static IP
echo "🌐 Static IP Address:"
STATIC_IP=$(gcloud compute addresses describe sapphire-static-ip --region=$REGION --project=$PROJECT_ID --format="get(address)" 2>/dev/null || echo "Not created yet")
echo "   $STATIC_IP"
echo ""

# Check Cloud Run service
echo "☁️  Cloud Run Service Status:"
if gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID &>/dev/null; then
    gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID --format="table(status.url,status.conditions[0].status,status.conditions[0].reason)"
else
    echo "   Service not yet deployed"
fi
echo ""

# Check for recent errors in logs
echo "⚠️  Recent Errors (last 10 minutes):"
gcloud logging read "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR AND timestamp>=\"$(date -u -v-10M '+%Y-%m-%dT%H:%M:%SZ')\"" \
    --limit=5 \
    --project=$PROJECT_ID \
    --format="value(textPayload)" 2>/dev/null || echo "   No errors found (or service not yet deployed)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
