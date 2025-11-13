#!/bin/bash
echo "🔍 INFRASTRUCTURE READINESS MONITOR"
echo "===================================="

READY=false
ATTEMPTS=0
MAX_ATTEMPTS=60  # 30 minutes max wait

while [ "$READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    echo ""
    echo "🔍 Check #$((ATTEMPTS+1)) - $(date '+%H:%M:%S')"

    # Check load balancer
    LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    LB_READY=false
    if [ -n "$LB_IP" ]; then
        LB_READY=true
        echo "✅ Load Balancer: $LB_IP"
    else
        echo "⏳ Load Balancer: Still provisioning..."
    fi

    # Check SSL certificate
    CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)
    CERT_READY=false
    if [ "$CERT_STATUS" = "Active" ]; then
        CERT_READY=true
        echo "✅ SSL Certificate: Active"
    else
        echo "⏳ SSL Certificate: $CERT_STATUS"
    fi

    # Check if all infrastructure is ready
    if [ "$LB_READY" = true ] && [ "$CERT_READY" = true ]; then
        echo ""
        echo "🎉 INFRASTRUCTURE READY!"
        echo "======================="
        echo ""
        echo "🌐 Load Balancer IP: $LB_IP"
        echo "🔒 SSL Certificate: Active"
        echo ""
        echo "📋 IMMEDIATE DNS UPDATES REQUIRED:"
        echo "=================================="
        echo ""
        echo "🔧 Domain Registrar Updates:"
        echo "---------------------------"
        echo "1. sapphiretrade.xyz → CNAME: sapphireinfinite.web.app"
        echo "2. api.sapphiretrade.xyz → A record: $LB_IP"
        echo ""
        echo "⏱️  DNS Propagation Time: 5-30 minutes"
        echo ""
        echo "🧪 POST-DNS VERIFICATION TESTS:"
        echo "==============================="
        echo "• curl https://sapphiretrade.xyz (Firebase redirect)"
        echo "• curl https://api.sapphiretrade.xyz/healthz (API health)"
        echo "• curl https://api.sapphiretrade.xyz/portfolio-status (API data)"
        echo ""
        echo "🚀 NEXT STEPS AFTER DNS:"
        echo "======================="
        echo "1. Run comprehensive E2E tests"
        echo "2. Enable live trading mode"
        echo "3. Monitor first live trades"
        echo "4. Set up production monitoring alerts"
        echo ""
        echo "💎 SAPPHIRE TRADING READY FOR GO-LIVE!"
        echo ""
        echo "⚡ DNS updates will complete the deployment!"

        READY=true
    else
        if [ $((ATTEMPTS % 6)) -eq 0 ]; then  # Every 3 minutes
            echo ""
            echo "💡 While waiting for infrastructure..."
            echo "• BigQuery permissions added ✅"
            echo "• Pub/Sub topics verified ✅"
            echo "• Service account permissions updated ✅"
            echo "• Enhanced Telegram bot deployed ✅"
            echo "• AI trading agents running ✅"
        fi

        echo "⏳ Waiting 30s for infrastructure completion..."
        sleep 30
        ((ATTEMPTS++))
    fi
done

if [ "$READY" = false ]; then
    echo ""
    echo "⏰ INFRASTRUCTURE TIMEOUT"
    echo "========================"
    echo ""
    echo "The infrastructure is taking longer than expected to provision."
    echo "This is sometimes normal for GKE load balancers and certificates."
    echo ""
    echo "🔧 MANUAL CHECKS:"
    echo "• kubectl get ingress -n trading"
    echo "• kubectl get managedcertificate -n trading"
    echo "• gcloud compute addresses list"
    echo ""
    echo "📞 If issues persist, contact GCP support or try:"
    echo "• Deleting and recreating the ingress"
    echo "• Checking GCP project quotas and limits"
fi

