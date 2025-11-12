#!/bin/bash
echo "🚀 PRODUCTION READINESS MONITOR - SAPPHIRE TRADING"
echo "=================================================="

READY=false
ATTEMPTS=0
MAX_ATTEMPTS=30  # 15 minutes max wait

while [ "$READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    echo ""
    echo "🔍 Readiness Check #$((ATTEMPTS+1)) - $(date '+%H:%M:%S')"

    # Check Cloud Build status
    BUILD_COUNT=$(gcloud builds list --project=sapphireinfinite --filter="status=WORKING" --format="value(name)" 2>/dev/null | wc -l)
    FAILED_BUILDS=$(gcloud builds list --project=sapphireinfinite --limit=1 --filter="status=FAILURE" --format="value(name)" 2>/dev/null | wc -l)

    if [ "$FAILED_BUILDS" -gt 0 ]; then
        echo "❌ BUILD FAILURE DETECTED"
        echo "Check: gcloud builds list --project=sapphireinfinite --filter='status=FAILURE' --limit=1"
        exit 1
    fi

    # Check pod health
    READY_PODS=$(kubectl get pods -n trading --no-headers 2>/dev/null | grep "1/1" | wc -l)
    TOTAL_PODS=$(kubectl get pods -n trading --no-headers 2>/dev/null | wc -l)

    # Check infrastructure
    LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)

    # Check API health
    API_HEALTH="N/A"
    if [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ]; then
        API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "failed")
    fi

    echo "🏗️  Cloud Builds: $BUILD_COUNT working"
    echo "📦 Pods: $READY_PODS/$TOTAL_PODS ready"
    echo "🌐 Load Balancer: ${LB_IP:-pending}"
    echo "🔒 SSL Certificate: ${CERT_STATUS:-pending}"
    echo "🔗 API Health: ${API_HEALTH:-pending}"

    # Check if everything is ready
    if [ "$BUILD_COUNT" -eq 0 ] && [ "$READY_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -eq 7 ] && [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ] && [ "$API_HEALTH" = "200" ]; then
        echo ""
        echo "🎉 🎉 🎉 ALL SYSTEMS GO! 🎉 🎉 🎉"
        echo ""
        echo "✅ Cloud Builds completed successfully"
        echo "✅ All 7 pods running (4 AI agents + 2 cloud-trader + 1 system)"
        echo "✅ Load balancer active: $LB_IP"
        echo "✅ SSL certificate active"
        echo "✅ API responding (HTTP $API_HEALTH)"
        echo ""

        # Run comprehensive E2E tests
        echo "🧪 Running Comprehensive End-to-End Tests..."
        echo "=========================================="
        ./comprehensive_e2e_test.sh

        TEST_EXIT_CODE=$?
        if [ $TEST_EXIT_CODE -eq 0 ]; then
            echo ""
            echo "🚀 PRODUCTION DEPLOYMENT SUCCESSFUL!"
            echo "=================================="
            echo ""
            echo "🎯 FINAL GO-LIVE STEPS:"
            echo "======================"
            echo "1. 🌐 Update DNS: sapphiretrade.xyz → CNAME: sapphireinfinite.web.app"
            echo "2. 🌐 Update DNS: api.sapphiretrade.xyz → A record: $LB_IP"
            echo "3. ⚡ Enable live trading: kubectl set env deployment/cloud-trader ENABLE_PAPER_TRADING=false -n trading"
            echo "4. 📱 Monitor enhanced Telegram bot notifications"
            echo "5. 📊 Track first live trades"
            echo ""
            echo "💎 SAPPHIRE TRADING IS NOW LIVE! 💎"
            echo ""
            echo "🎉 Congratulations! Your enterprise-grade autonomous trading platform is operational."
        else
            echo ""
            echo "⚠️  E2E TESTS FAILED - MANUAL REVIEW REQUIRED"
            echo "=============================================="
            echo "Some tests failed. Please review the output above and address any issues before proceeding."
        fi

        READY=true
    else
        if [ "$BUILD_COUNT" -gt 0 ]; then
            echo "⏳ Builds still in progress... ($BUILD_COUNT working)"
        elif [ "$READY_PODS" -ne "$TOTAL_PODS" ] || [ "$TOTAL_PODS" -ne 7 ]; then
            echo "⏳ Pods still starting... ($READY_PODS/$TOTAL_PODS ready)"
        elif [ -z "$LB_IP" ]; then
            echo "⏳ Load balancer still provisioning..."
        elif [ "$CERT_STATUS" != "Active" ]; then
            echo "⏳ SSL certificate still activating..."
        elif [ "$API_HEALTH" != "200" ]; then
            echo "⏳ API still initializing..."
        fi

        echo "⏳ Waiting 30s for completion..."
        sleep 30
        ((ATTEMPTS++))
    fi
done

if [ "$READY" = false ]; then
    echo ""
    echo "⏰ TIMEOUT: System deployment incomplete"
    echo "========================================"
    echo "The system is taking longer than expected to fully deploy."
    echo ""
    echo "🔧 TROUBLESHOOTING STEPS:"
    echo "1. Check build status: gcloud builds list --project=sapphireinfinite"
    echo "2. Check pod status: kubectl get pods -n trading"
    echo "3. Check logs: kubectl logs -n trading deployment/cloud-trader"
    echo "4. Check ingress: kubectl get ingress -n trading"
    echo "5. Run manual tests: ./comprehensive_e2e_test.sh"
    echo ""
    echo "The system may still be deploying. Try running this script again."
fi
