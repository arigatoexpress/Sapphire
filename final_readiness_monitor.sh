#!/bin/bash
echo "🔍 FINAL READINESS MONITOR - SAPPHIRE TRADING"
echo "============================================"

READY=false
ATTEMPTS=0
MAX_ATTEMPTS=20

while [ "$READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    echo ""
    echo "📡 Readiness Check #$((ATTEMPTS+1)) - $(date '+%H:%M:%S')"
    
    # Check Cloud Build status
    BUILD_STATUS=$(gcloud builds list --project=sapphireinfinite --limit=1 --format="value(status)" 2>/dev/null)
    
    # Check pod health
    READY_PODS=$(kubectl get pods -n trading --no-headers 2>/dev/null | grep "1/1" | wc -l)
    TOTAL_PODS=$(kubectl get pods -n trading --no-headers 2>/dev/null | wc -l)
    
    # Check infrastructure
    LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)
    
    # Check API health (if infra is ready)
    API_HEALTH="N/A"
    if [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ]; then
        API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "failed")
    fi
    
    echo "🏗️  Cloud Build: $BUILD_STATUS"
    echo "📦 Pods: $READY_PODS/$TOTAL_PODS ready"
    echo "🌐 Load Balancer: ${LB_IP:-pending}"
    echo "🔒 SSL Certificate: ${CERT_STATUS:-pending}"
    echo "🔗 API Health: ${API_HEALTH:-pending}"
    
    # Check if everything is ready
    if [ "$BUILD_STATUS" = "SUCCESS" ] && [ "$READY_PODS" = "$TOTAL_PODS" ] && [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ] && [ "$API_HEALTH" = "200" ]; then
        echo ""
        echo "🎉 🎉 🎉 ALL SYSTEMS GO! 🎉 🎉 🎉"
        echo ""
        echo "🚀 READY FOR GO-LIVE:"
        echo "====================="
        echo "✅ Code deployed successfully"
        echo "✅ All pods healthy ($READY_PODS/$TOTAL_PODS)"
        echo "✅ Load balancer active: $LB_IP"
        echo "✅ SSL certificate active"
        echo "✅ API responding (HTTP $API_HEALTH)"
        echo ""
        echo "📋 FINAL STEPS:"
        echo "1. Update DNS: sapphiretrade.xyz → Firebase Hosting"
        echo "2. Update DNS: api.sapphiretrade.xyz → $LB_IP"
        echo "3. Enable live trading: ENABLE_PAPER_TRADING=false"
        echo "4. Monitor first live trades"
        echo ""
        echo "🌟 SAPPHIRE TRADING IS PRODUCTION READY! 💎"
        READY=true
    else
        if [ "$BUILD_STATUS" = "FAILURE" ]; then
            echo ""
            echo "❌ BUILD FAILURE DETECTED"
            echo "Check logs: gcloud builds log <build-id> --project=sapphireinfinite"
            exit 1
        fi
        
        echo "⏳ Still provisioning... (waiting 30s)"
        sleep 30
        ((ATTEMPTS++))
    fi
done

if [ "$READY" = false ]; then
    echo ""
    echo "⏰ TIMEOUT: System still provisioning"
    echo "Infrastructure may take longer than expected"
    echo "Check status manually or run this script again"
fi
