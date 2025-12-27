#!/bin/bash
echo "🔍 MONITORING INFRASTRUCTURE COMPLETION"
echo "======================================="
echo ""

READY=false
ATTEMPTS=0
MAX_ATTEMPTS=30  # 5 minutes with 10s intervals

while [ "$READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    echo "Attempt $((ATTEMPTS+1))/$MAX_ATTEMPTS - $(date '+%H:%M:%S')"

    # Check load balancer
    LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)

    # Check certificate
    CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)

    if [ -n "$LB_IP" ] && [ "$CERT_STATUS" = "Active" ]; then
        echo ""
        echo "🎉 INFRASTRUCTURE READY!"
        echo "======================="
        echo "✅ Load Balancer IP: $LB_IP"
        echo "✅ SSL Certificate: $CERT_STATUS"
        echo ""

        # Test the API
        echo "🧪 TESTING API ENDPOINTS..."
        HEALTH_TEST=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "failed")

        if [ "$HEALTH_TEST" = "200" ]; then
            echo "✅ API Health Check: PASSED"
            echo ""
            echo "🚀 SYSTEM FULLY OPERATIONAL!"
            echo "==========================="
            echo "Frontend: https://sapphireinfinite.web.app"
            echo "API: https://api.sapphiretrade.xyz"
            echo "DNS Current: sapphiretrade.xyz → Old service"
            echo ""
            echo "📋 NEXT STEPS:"
            echo "1. Update DNS: sapphiretrade.xyz → Firebase Hosting"
            echo "2. Update DNS: api.sapphiretrade.xyz → $LB_IP"
            echo "3. Test end-to-end functionality"
            echo "4. Verify trading bots are operational"
            READY=true
        else
            echo "⚠️  API not responding yet (HTTP $HEALTH_TEST)"
            echo "   Load balancer may still be configuring..."
        fi
    else
        if [ -z "$LB_IP" ]; then
            echo "⏳ Load Balancer: Still provisioning..."
        else
            echo "✅ Load Balancer: $LB_IP"
        fi

        if [ "$CERT_STATUS" != "Active" ]; then
            echo "⏳ SSL Certificate: $CERT_STATUS"
        else
            echo "✅ SSL Certificate: $CERT_STATUS"
        fi
    fi

    if [ "$READY" = false ]; then
        echo "⏳ Waiting 10 seconds..."
        sleep 10
        ((ATTEMPTS++))
    fi
    echo ""
done

if [ "$READY" = false ]; then
    echo "⏰ TIMEOUT: Infrastructure still provisioning after 5 minutes"
    echo "   GKE load balancers can take 10-20 minutes to fully provision"
    echo "   Run this script again or check manually:"
    echo "   kubectl get ingress -n trading"
    echo "   kubectl get managedcertificate -n trading"
fi
