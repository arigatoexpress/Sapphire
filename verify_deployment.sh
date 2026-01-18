#!/bin/bash
# Verification Script for Sapphire V2 Deployment
# Run this after deployment to check if everything is working

set -e

PROJECT_ID="sapphire-479610"
REGION="us-central1"
SERVICE_NAME="sapphire-v2"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Sapphire V2 Deployment Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Check Service Status
echo "1️⃣  Checking Cloud Run Service Status..."
SERVICE_STATUS=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="get(status.conditions[0].status)" 2>/dev/null || echo "NOT_FOUND")

if [ "$SERVICE_STATUS" = "True" ]; then
    echo "   ✅ Service is HEALTHY"
else
    echo "   ❌ Service is NOT HEALTHY: $SERVICE_STATUS"
fi

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="get(status.url)" 2>/dev/null || echo "")

echo "   URL: $SERVICE_URL"
echo ""

# 2. Get Static IP
echo "2️⃣  Static IP Configuration..."
STATIC_IP=$(gcloud compute addresses describe sapphire-static-ip \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="get(address)" 2>/dev/null || echo "NOT_CONFIGURED")

echo "   Static IP: $STATIC_IP"
if [ "$STATIC_IP" != "NOT_CONFIGURED" ]; then
    echo "   ✅ Static IP is configured"
    echo "   ⚠️  Make sure this IP is whitelisted in Aster API settings"
else
    echo "   ❌ Static IP not found - run ./setup_cloud_nat.sh"
fi
echo ""

# 3. Check Recent Logs
echo "3️⃣  Checking Recent Logs (last 2 minutes)..."
echo ""

# Check for startup success
echo "   📱 Checking system startup..."
STARTUP_LOGS=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND \"Sapphire V2 is ONLINE\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$STARTUP_LOGS" ]; then
    echo "   ✅ System started successfully at: $STARTUP_LOGS"
else
    echo "   ⚠️  No startup log found - system may still be starting"
fi

# Check Telegram
echo ""
echo "   📱 Checking Telegram notifications..."
TELEGRAM_LOGS=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND \"Telegram notifications configured\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$TELEGRAM_LOGS" ]; then
    echo "   ✅ Telegram configured successfully"
else
    echo "   ⚠️  Telegram configuration not found in logs"
fi

# Check for Telegram conflicts
TELEGRAM_409=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR AND \"409\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$TELEGRAM_409" ]; then
    echo "   ❌ TELEGRAM CONFLICT DETECTED (HTTP 409 error)"
    echo "      Multiple bots using same token!"
else
    echo "   ✅ No Telegram conflicts"
fi

# Check Vertex AI
echo ""
echo "   🤖 Checking Vertex AI / Gemini..."
VERTEX_LOGS=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND \"Using Vertex AI API key\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$VERTEX_LOGS" ]; then
    echo "   ✅ Vertex AI key loaded successfully"
else
    echo "   ⚠️  Vertex AI log not found - may be using Gemini API key instead"
fi

# Check for AI fallback
AI_FALLBACK=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND \"Using fallback response\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$AI_FALLBACK" ]; then
    echo "   ⚠️  AI models unavailable - using fallback"
else
    echo "   ✅ AI models responding"
fi

# Check Trading Loop
echo ""
echo "   💹 Checking Trading Activity..."
TRADING_LOGS=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND \"Cycle #\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(textPayload)" 2>/dev/null || echo "")

if [ -n "$TRADING_LOGS" ]; then
    echo "   ✅ Trading loop is active"
    echo "   Latest: $TRADING_LOGS"
else
    echo "   ⚠️  No trading activity detected yet"
fi

# Check for Aster IP errors
echo ""
echo "   🔐 Checking Aster API Access..."
ASTER_ERROR=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR AND \"2015\"" \
  --limit=1 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null || echo "")

if [ -n "$ASTER_ERROR" ]; then
    echo "   ❌ ASTER IP WHITELIST ERROR DETECTED"
    echo "      Your IP $STATIC_IP is NOT whitelisted!"
    echo "      Add it to Aster API key settings"
else
    echo "   ✅ No Aster IP errors"
fi

# Check for any recent errors
echo ""
echo "   ⚠️  Checking for Recent Errors..."
ERROR_COUNT=$(gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR AND timestamp>\"$(date -u -v-5M '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')\"" \
  --limit=100 \
  --project=$PROJECT_ID \
  --format="value(timestamp)" 2>/dev/null | wc -l || echo "0")

echo "   Recent errors (last 5 min): $ERROR_COUNT"
if [ "$ERROR_COUNT" -gt 10 ]; then
    echo "   ⚠️  High error count - check logs with:"
    echo "      gcloud logging read 'resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR' --limit=20"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Verification Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Service Status: $SERVICE_STATUS"
echo "Static IP: $STATIC_IP"
echo "Service URL: $SERVICE_URL"
echo ""

# Health check
if [ -n "$SERVICE_URL" ]; then
    echo "Testing health endpoint..."
    HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health" 2>/dev/null || echo "{}")
    echo "$HEALTH_RESPONSE" | head -c 200
    echo ""
fi

echo ""
echo "🔧 Quick Actions:"
echo ""
echo "  View live logs:"
echo "    gcloud logging tail 'resource.labels.service_name=\"$SERVICE_NAME\"' --project=$PROJECT_ID"
echo ""
echo "  Check all errors:"
echo "    gcloud logging read 'resource.labels.service_name=\"$SERVICE_NAME\" AND severity>=ERROR' --limit=20 --project=$PROJECT_ID"
echo ""
echo "  Get static IP:"
echo "    gcloud compute addresses describe sapphire-static-ip --region=$REGION --project=$PROJECT_ID --format='get(address)'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
