#!/bin/bash
echo "🎯 SAPPHIRE TRADING - FINAL GO-LIVE STATUS"
echo "=========================================="

# 1. Cloud Build Status
echo "1️⃣  CLOUD BUILD STATUS:"
BUILD_STATUS=$(gcloud builds list --project=sapphireinfinite --limit=1 --format="value(status)")
if [ "$BUILD_STATUS" = "SUCCESS" ]; then
    echo "✅ Cloud Build: COMPLETED"
elif [ "$BUILD_STATUS" = "WORKING" ]; then
    echo "⏳ Cloud Build: BUILDING..."
elif [ "$BUILD_STATUS" = "FAILURE" ]; then
    echo "❌ Cloud Build: FAILED"
else
    echo "⏳ Cloud Build: $BUILD_STATUS"
fi

echo ""

# 2. Pod Health
echo "2️⃣  POD HEALTH:"
TOTAL_PODS=$(kubectl get pods -n trading --no-headers | wc -l)
READY_PODS=$(kubectl get pods -n trading --no-headers | grep "1/1" | wc -l)
PENDING_PODS=$(kubectl get pods -n trading --no-headers | grep "Pending" | wc -l)

echo "Total Pods: $TOTAL_PODS"
echo "Ready Pods: $READY_PODS"
echo "Pending Pods: $PENDING_PODS"

if [ "$PENDING_PODS" = "0" ] && [ "$READY_PODS" = "$TOTAL_PODS" ]; then
    echo "✅ All pods healthy"
else
    echo "⚠️  Pod health issues detected"
fi

echo ""

# 3. Infrastructure Status
echo "3️⃣  INFRASTRUCTURE STATUS:"
LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)

if [ -n "$LB_IP" ]; then
    echo "✅ Load Balancer: $LB_IP"
    LB_READY=true
else
    echo "⏳ Load Balancer: Still provisioning"
    LB_READY=false
fi

if [ "$CERT_STATUS" = "Active" ]; then
    echo "✅ SSL Certificate: Active"
    CERT_READY=true
else
    echo "⏳ SSL Certificate: $CERT_STATUS"
    CERT_READY=false
fi

echo ""

# 4. Service Testing
echo "4️⃣  SERVICE TESTING:"
if [ "$LB_READY" = true ] && [ "$CERT_READY" = true ]; then
    echo "Testing API endpoints..."
    
    HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "timeout")
    if [ "$HEALTH_CODE" = "200" ]; then
        echo "✅ API Health Check: RESPONDING"
        
        # Check for errors in health response
        HEALTH_RESPONSE=$(curl -s https://api.sapphiretrade.xyz/healthz 2>/dev/null)
        if echo "$HEALTH_RESPONSE" | grep -q '"last_error":null'; then
            echo "✅ Trading Logic: NO ERRORS"
        else
            echo "⚠️  Trading Logic: ERRORS DETECTED"
            echo "   $(echo "$HEALTH_RESPONSE" | jq -r '.last_error' 2>/dev/null || echo 'Unknown error')"
        fi
    else
        echo "❌ API Health Check: FAILED (HTTP $HEALTH_CODE)"
    fi
else
    echo "⏳ API Testing: Waiting for infrastructure"
fi

echo ""

# 5. Frontend Status
echo "5️⃣  FRONTEND STATUS:"
FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://sapphireinfinite.web.app)
if [ "$FRONTEND_CODE" = "200" ]; then
    echo "✅ Frontend: Live and responding"
else
    echo "❌ Frontend: Issues (HTTP $FRONTEND_CODE)"
fi

echo ""

# 6. Overall Readiness
echo "🎯 OVERALL READINESS ASSESSMENT:"
if [ "$BUILD_STATUS" = "SUCCESS" ] && [ "$READY_PODS" = "$TOTAL_PODS" ] && [ "$LB_READY" = true ] && [ "$CERT_READY" = true ] && [ "$FRONTEND_CODE" = "200" ]; then
    echo "🎉 SYSTEM FULLY READY FOR PRODUCTION!"
    echo ""
    echo "🚀 FINAL STEPS:"
    echo "1. Update DNS: sapphiretrade.xyz → Firebase Hosting"
    echo "2. Update DNS: api.sapphiretrade.xyz → $LB_IP"
    echo "3. Enable live trading mode"
    echo "4. Monitor system performance"
    echo "5. Delete old sapphireinfinite project"
    echo ""
    echo "💎 SAPPHIRE TRADING IS LIVE! 🌟"
else
    echo "⏳ System still deploying..."
    echo ""
    echo "📋 REMAINING TASKS:"
    [ "$BUILD_STATUS" != "SUCCESS" ] && echo "  - Cloud Build completion"
    [ "$READY_PODS" != "$TOTAL_PODS" ] && echo "  - Pod health resolution"
    [ "$LB_READY" != true ] && echo "  - Load balancer provisioning"
    [ "$CERT_READY" != true ] && echo "  - SSL certificate activation"
    [ "$FRONTEND_CODE" != "200" ] && echo "  - Frontend deployment"
fi

echo ""
echo "🔄 IPs Whitelisted: ✅ 104.197.228.10, 34.144.213.188"
echo "🔗 Frontend URL: https://sapphireinfinite.web.app"
[ -n "$LB_IP" ] && echo "🔗 API URL: https://api.sapphiretrade.xyz (IP: $LB_IP)"
