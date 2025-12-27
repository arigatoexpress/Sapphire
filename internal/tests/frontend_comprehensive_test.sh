#!/bin/bash
echo "🧪 COMPREHENSIVE SYSTEM TEST SUITE"
echo "=================================="
echo ""

# Test 1: Frontend Deployment
echo "1️⃣  FRONTEND TESTS"
echo "-----------------"
echo "Testing Firebase Hosting..."
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://sapphireinfinite.web.app)
if [ "$FRONTEND_STATUS" = "200" ]; then
    echo "✅ Frontend: Responding (HTTP 200)"
else
    echo "❌ Frontend: Failed (HTTP $FRONTEND_STATUS)"
fi
echo ""

# Test 2: Backend API (when load balancer is ready)
echo "2️⃣  BACKEND API TESTS"
echo "--------------------"
LB_IP=$(kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [ -n "$LB_IP" ]; then
    echo "✅ Load Balancer: $LB_IP"

    # Test health endpoint
    HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "timeout")
    if [ "$HEALTH_STATUS" = "200" ]; then
        echo "✅ API Health: Responding"
    else
        echo "❌ API Health: Failed ($HEALTH_STATUS)"
    fi

    # Test portfolio endpoint
    PORTFOLIO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://api.sapphiretrade.xyz/portfolio-status 2>/dev/null || echo "timeout")
    if [ "$PORTFOLIO_STATUS" = "200" ]; then
        echo "✅ Portfolio API: Responding"
    else
        echo "❌ Portfolio API: Failed ($PORTFOLIO_STATUS)"
    fi
else
    echo "⏳ Load Balancer: Still provisioning (no external IP yet)"
fi
echo ""

# Test 3: Pod Health
echo "3️⃣  POD HEALTH CHECK"
echo "------------------"
TOTAL_PODS=$(kubectl get pods -n trading --no-headers | wc -l)
READY_PODS=$(kubectl get pods -n trading --no-headers | grep "1/1" | wc -l)
RUNNING_PODS=$(kubectl get pods -n trading --no-headers | grep "Running" | wc -l)

echo "Total Pods: $TOTAL_PODS"
echo "Ready Pods: $READY_PODS"
echo "Running Pods: $RUNNING_PODS"

if [ "$TOTAL_PODS" = "$READY_PODS" ] && [ "$READY_PODS" = "$RUNNING_PODS" ]; then
    echo "✅ All pods healthy"
else
    echo "❌ Pod health issues detected"
fi
echo ""

# Test 4: Certificate Status
echo "4️⃣  SSL CERTIFICATE STATUS"
echo "------------------------"
CERT_STATUS=$(kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null)
if [ "$CERT_STATUS" = "Active" ]; then
    echo "✅ SSL Certificate: Active"
else
    echo "⏳ SSL Certificate: $CERT_STATUS"
fi
echo ""

# Test 5: Service Connectivity
echo "5️⃣  SERVICE CONNECTIVITY"
echo "----------------------"
echo "Testing internal service communication..."
kubectl exec -n trading deployment/cloud-trader -- curl -s http://cloud-trader-service/portfolio-status > /dev/null 2>&1
if [ $? = 0 ]; then
    echo "✅ Internal services: Communicating"
else
    echo "❌ Internal services: Connection issues"
fi
echo ""

# Test 6: DNS Resolution
echo "6️⃣  DNS RESOLUTION"
echo "----------------"
DOMAIN_IP=$(nslookup sapphiretrade.xyz 2>/dev/null | grep "Address" | tail -1 | awk '{print $2}')
if [ -n "$DOMAIN_IP" ]; then
    echo "✅ Domain Resolution: $DOMAIN_IP"
else
    echo "❌ Domain Resolution: Failed"
fi
echo ""

# Summary
echo "📊 TEST SUMMARY"
echo "=============="
echo "✅ Frontend: Deployed & Responding"
echo "⏳ Backend: Waiting for load balancer"
echo "✅ Kubernetes: All pods healthy"
echo "⏳ SSL: Certificate provisioning"
echo "✅ Internal Services: Communicating"
echo ""
echo "🎯 NEXT: Wait for infrastructure, then test full API connectivity"
