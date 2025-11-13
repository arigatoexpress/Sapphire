#!/bin/bash
# Comprehensive error checking script

set -e

PROJECT_ID="sapphireinfinite"
NAMESPACE="trading"

echo "🔍 Comprehensive Error Check"
echo "============================"
echo ""

# 1. Check Pods
echo "1️⃣ Pod Status:"
POD_COUNT=$(kubectl get pods -n $NAMESPACE --no-headers | wc -l | tr -d ' ')
PENDING_COUNT=$(kubectl get pods -n $NAMESPACE --field-selector=status.phase=Pending --no-headers 2>/dev/null | wc -l | tr -d ' ')
RUNNING_COUNT=$(kubectl get pods -n $NAMESPACE --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
READY_COUNT=$(kubectl get pods -n $NAMESPACE --field-selector=status.phase=Running --no-headers 2>/dev/null | grep -c "1/1" || echo "0")

echo "  Total pods: $POD_COUNT"
echo "  Running: $RUNNING_COUNT"
echo "  Ready: $READY_COUNT"
echo "  Pending: $PENDING_COUNT"

if [ "$PENDING_COUNT" -gt 0 ]; then
    echo "  ⚠️  WARNING: $PENDING_COUNT pod(s) stuck in Pending"
else
    echo "  ✅ All pods running"
fi
echo ""

# 2. Check Deployment
echo "2️⃣ Deployment Status:"
SPEC_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
CURRENT_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.status.replicas}' 2>/dev/null || echo "0")
READY_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")

echo "  Specified: $SPEC_REPLICAS"
echo "  Current: $CURRENT_REPLICAS"
echo "  Ready: $READY_REPLICAS"

if [ "$SPEC_REPLICAS" != "$CURRENT_REPLICAS" ]; then
    echo "  ⚠️  WARNING: Replica mismatch"
else
    echo "  ✅ Replicas match"
fi
echo ""

# 3. Check Service
echo "3️⃣ Service Status:"
LB_IP=$(kubectl get svc -n $NAMESPACE cloud-trader-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "None")
echo "  LoadBalancer IP: $LB_IP"

if [ "$LB_IP" = "None" ] || [ -z "$LB_IP" ]; then
    echo "  ⚠️  WARNING: No LoadBalancer IP assigned"
else
    echo "  ✅ LoadBalancer IP assigned"
fi
echo ""

# 4. Check Ingress
echo "4️⃣ Ingress Status:"
INGRESS_IP=$(kubectl get ingress -n $NAMESPACE cloud-trader-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "None")
echo "  Ingress IP: $INGRESS_IP"

if [ "$INGRESS_IP" = "None" ] || [ -z "$INGRESS_IP" ]; then
    echo "  ⚠️  WARNING: Ingress has no address (may be provisioning)"
else
    echo "  ✅ Ingress has address"
fi
echo ""

# 5. Check SSL Certificate
echo "5️⃣ SSL Certificate:"
CERT_STATUS=$(kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null || echo "Unknown")
DOMAIN_STATUS=$(kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.domainStatus[0].status}' 2>/dev/null || echo "Unknown")

echo "  Certificate Status: $CERT_STATUS"
echo "  Domain Status: $DOMAIN_STATUS"

if [ "$CERT_STATUS" != "Active" ]; then
    echo "  ⚠️  WARNING: Certificate not active (Status: $CERT_STATUS)"
    if [ "$DOMAIN_STATUS" = "FailedNotVisible" ]; then
        echo "  ⚠️  Domain not visible - check DNS"
    fi
else
    echo "  ✅ Certificate is active"
fi
echo ""

# 6. Check API Endpoint
echo "6️⃣ API Endpoint Test:"
API_RESPONSE=$(timeout 5 curl -s -o /dev/null -w "%{http_code}" https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "000")
if [ "$API_RESPONSE" = "200" ]; then
    echo "  ✅ API endpoint responding (HTTP $API_RESPONSE)"
elif [ "$API_RESPONSE" = "000" ]; then
    echo "  ⚠️  API endpoint timeout or connection refused"
else
    echo "  ⚠️  API endpoint returned HTTP $API_RESPONSE"
fi
echo ""

# 7. Check Frontend
echo "7️⃣ Frontend Test:"
FRONTEND_RESPONSE=$(timeout 5 curl -s -o /dev/null -w "%{http_code}" https://sapphiretrade.xyz 2>/dev/null || echo "000")
if [ "$FRONTEND_RESPONSE" = "200" ]; then
    echo "  ✅ Frontend responding (HTTP $FRONTEND_RESPONSE)"
else
    echo "  ⚠️  Frontend returned HTTP $FRONTEND_RESPONSE"
fi
echo ""

# 8. Check Logs for Errors
echo "8️⃣ Recent Log Errors:"
ERROR_COUNT=$(kubectl logs -n $NAMESPACE deployment/cloud-trader --tail=100 2>&1 | grep -ic "error\|exception\|failed\|traceback" || echo "0")
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "  ✅ No errors in recent logs"
else
    echo "  ⚠️  Found $ERROR_COUNT error(s) in recent logs"
    echo "  Recent errors:"
    kubectl logs -n $NAMESPACE deployment/cloud-trader --tail=100 2>&1 | grep -i "error\|exception\|failed" | tail -5 || true
fi
echo ""

# 9. Check Resource Usage
echo "9️⃣ Resource Usage:"
kubectl top pods -n $NAMESPACE --no-headers 2>/dev/null | head -3 | awk '{printf "  %s: CPU=%s, Memory=%s\n", $1, $2, $3}' || echo "  ⚠️  Metrics not available"
echo ""

# 10. Summary
echo "🔟 Summary:"
ISSUES=0

if [ "$PENDING_COUNT" -gt 0 ]; then
    echo "  ❌ $PENDING_COUNT pod(s) pending"
    ISSUES=$((ISSUES + 1))
fi

if [ "$SPEC_REPLICAS" != "$CURRENT_REPLICAS" ]; then
    echo "  ❌ Replica mismatch"
    ISSUES=$((ISSUES + 1))
fi

if [ "$CERT_STATUS" != "Active" ]; then
    echo "  ⚠️  SSL certificate not active"
    ISSUES=$((ISSUES + 1))
fi

if [ "$API_RESPONSE" != "200" ]; then
    echo "  ⚠️  API endpoint not responding"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "  ✅ No critical issues found"
else
    echo ""
    echo "  Found $ISSUES issue(s) that need attention"
fi

echo ""
echo "✅ Error check complete"

