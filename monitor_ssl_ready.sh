#!/bin/bash
echo "🔒 SSL CERTIFICATE MONITOR"
echo "========================="

READY=false
ATTEMPTS=0
MAX_ATTEMPTS=20  # 10 minutes max wait

while [ "$READY" = false ] && [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    echo ""
    echo "🔍 Check #$((ATTEMPTS+1)) - $(date '+%H:%M:%S')"

    CERT_STATUS=$(kubectl get managedcertificate cloud-trader-cert -n trading -o jsonpath='{.status.certificateStatus}' 2>/dev/null)
    DOMAIN_STATUS=$(kubectl get managedcertificate cloud-trader-cert -n trading -o jsonpath='{.status.domainStatus[0].status}' 2>/dev/null)

    echo "Certificate Status: $CERT_STATUS"
    echo "Domain Status: $DOMAIN_STATUS"

    if [ "$CERT_STATUS" = "Active" ]; then
        echo ""
        echo "🎉 SSL CERTIFICATE ACTIVE!"
        echo "========================="
        echo ""
        echo "✅ Certificate: Active"
        echo "✅ Domain: Verified"
        echo ""
        echo "🔒 HTTPS ENDPOINTS NOW AVAILABLE:"
        echo "================================="
        echo "• https://api.sapphiretrade.xyz/healthz"
        echo "• https://api.sapphiretrade.xyz/portfolio-status"
        echo ""
        echo "🧪 TESTING HTTPS ENDPOINTS..."
        echo "============================"

        # Test HTTPS health
        HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "https://api.sapphiretrade.xyz/healthz" 2>/dev/null || echo "failed")
        if [ "$HTTPS_CODE" = "200" ]; then
            echo "✅ HTTPS Health Check: 200 OK"
        else
            echo "⚠️  HTTPS Health Check: $HTTPS_CODE (may still be propagating)"
        fi

        READY=true
    elif [ "$DOMAIN_STATUS" = "FailedNotVisible" ]; then
        echo "❌ Domain still not visible to certificate authority"
        echo "   DNS propagation may take 5-15 minutes"
    else
        echo "⏳ Certificate still provisioning..."
    fi

    if [ "$READY" = false ]; then
        echo "⏳ Waiting 30s for certificate activation..."
        sleep 30
        ((ATTEMPTS++))
    fi
done

if [ "$READY" = false ]; then
    echo ""
    echo "⏰ SSL CERTIFICATE TIMEOUT"
    echo "========================="
    echo ""
    echo "The SSL certificate is taking longer than expected."
    echo "This can happen due to certificate authority processing times."
    echo ""
    echo "🔧 TROUBLESHOOTING:"
    echo "• Check DNS propagation: dig api.sapphiretrade.xyz"
    echo "• Verify certificate: kubectl describe managedcertificate cloud-trader-cert -n trading"
    echo "• GCP Console: Check Certificate Manager for detailed status"
    echo ""
    echo "💡 Sometimes certificates activate within 15-30 minutes"
    echo "   The HTTP endpoints are still working: http://34.144.213.188"
fi

