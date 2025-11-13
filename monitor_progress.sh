#!/bin/bash
# Monitor progress of SSL, DNS, and API endpoint

echo "🔍 SAPPHIRE System Status Monitor"
echo "=================================="
echo ""

# Check SSL Certificate
echo "1️⃣ SSL Certificate:"
CERT_STATUS=$(kubectl get managedcertificate -n trading cloud-trader-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null || echo "Unknown")
DOMAIN_STATUS=$(kubectl get managedcertificate -n trading cloud-trader-cert -o jsonpath='{.status.domainStatus[0].status}' 2>/dev/null || echo "Unknown")
echo "   Status: $CERT_STATUS"
echo "   Domain: $DOMAIN_STATUS"
if [ "$CERT_STATUS" = "Active" ]; then
    echo "   ✅ Certificate is active!"
else
    echo "   ⏳ Still provisioning..."
fi
echo ""

# Check DNS
echo "2️⃣ DNS Resolution:"
CLOUD_DNS=$(gcloud dns record-sets list --zone=sapphiretrade-zone --project=sapphireinfinite --filter="name:api.sapphiretrade.xyz. AND type:A" --format="value(rrdatas)" 2>/dev/null | head -1)
PUBLIC_DNS=$(dig +short api.sapphiretrade.xyz @8.8.8.8 2>/dev/null | head -1)
echo "   Cloud DNS: $CLOUD_DNS"
echo "   Public DNS: $PUBLIC_DNS"
if [ "$CLOUD_DNS" = "$PUBLIC_DNS" ]; then
    echo "   ✅ DNS propagated!"
else
    echo "   ⏳ DNS still propagating..."
fi
echo ""

# Check API Endpoint
echo "3️⃣ API Endpoint:"
API_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "000")
if [ "$API_RESPONSE" = "200" ]; then
    echo "   ✅ API is responding (HTTP $API_RESPONSE)"
elif [ "$API_RESPONSE" = "000" ]; then
    echo "   ⏳ API not accessible yet (SSL may not be active)"
else
    echo "   ⚠️  API returned HTTP $API_RESPONSE"
fi
echo ""

# Check Frontend
echo "4️⃣ Frontend:"
FRONTEND_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://sapphireinfinite.web.app 2>/dev/null || echo "000")
if [ "$FRONTEND_RESPONSE" = "200" ]; then
    echo "   ✅ Frontend is accessible (HTTP $FRONTEND_RESPONSE)"
    echo "   URL: https://sapphireinfinite.web.app"
else
    echo "   ⚠️  Frontend returned HTTP $FRONTEND_RESPONSE"
fi
echo ""

# Summary
echo "📊 Summary:"
if [ "$CERT_STATUS" = "Active" ] && [ "$API_RESPONSE" = "200" ]; then
    echo "   ✅ System is fully operational!"
elif [ "$CERT_STATUS" = "Active" ]; then
    echo "   ⏳ SSL active, waiting for API..."
elif [ "$API_RESPONSE" = "000" ]; then
    echo "   ⏳ Waiting for SSL certificate activation..."
else
    echo "   ⏳ System is still provisioning..."
fi
echo ""
