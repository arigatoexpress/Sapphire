#!/bin/bash
# Troubleshooting script for SAPPHIRE deployment issues

set -e

PROJECT_ID="sapphireinfinite"
NAMESPACE="trading"
DOMAIN="api.sapphiretrade.xyz"

echo "🔍 SAPPHIRE Deployment Troubleshooting"
echo "========================================"
echo ""

# 1. Check current state
echo "1️⃣ Checking current deployment state..."
echo ""

echo "📊 Pod Status:"
kubectl get pods -n $NAMESPACE --no-headers | awk '{print $1, $3, $4}' | column -t
echo ""

echo "📊 Deployment Replicas:"
DEPLOYMENT_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.spec.replicas}')
CURRENT_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.status.replicas}')
READY_REPLICAS=$(kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='{.status.readyReplicas}')
echo "  Specified: $DEPLOYMENT_REPLICAS"
echo "  Current: $CURRENT_REPLICAS"
echo "  Ready: $READY_REPLICAS"
echo ""

echo "📊 LoadBalancer IP:"
LB_IP=$(kubectl get svc -n $NAMESPACE cloud-trader-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "  LoadBalancer IP: $LB_IP"
echo ""

echo "📊 Static IP (cloud-trader-ip):"
STATIC_IP=$(gcloud compute addresses describe cloud-trader-ip --global --project=$PROJECT_ID --format="get(address)" 2>/dev/null || echo "Not found")
echo "  Static IP: $STATIC_IP"
echo ""

echo "📊 DNS Resolution:"
DNS_IP=$(nslookup $DOMAIN 2>/dev/null | grep -A 1 "Name:" | tail -1 | awk '{print $2}' || echo "Failed to resolve")
echo "  DNS points to: $DNS_IP"
echo ""

echo "📊 SSL Certificate Status:"
kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null || echo "Not found"
echo ""

# 2. Identify issues
echo ""
echo "2️⃣ Identified Issues:"
echo ""

ISSUES=0

# Check DNS mismatch
if [ "$DNS_IP" != "$LB_IP" ] && [ "$DNS_IP" != "$STATIC_IP" ]; then
    echo "  ❌ DNS MISMATCH: DNS ($DNS_IP) doesn't match LoadBalancer ($LB_IP) or Static IP ($STATIC_IP)"
    ISSUES=$((ISSUES + 1))
fi

# Check pending pods
PENDING_PODS=$(kubectl get pods -n $NAMESPACE --field-selector=status.phase=Pending --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$PENDING_PODS" -gt 0 ]; then
    echo "  ❌ PENDING PODS: $PENDING_PODS pod(s) stuck in Pending state"
    ISSUES=$((ISSUES + 1))
fi

# Check certificate status
CERT_STATUS=$(kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null || echo "NOT_FOUND")
if [ "$CERT_STATUS" != "Active" ]; then
    echo "  ❌ SSL CERTIFICATE: Status is '$CERT_STATUS' (should be 'Active')"
    ISSUES=$((ISSUES + 1))
fi

# Check resource availability
if [ "$PENDING_PODS" -gt 0 ]; then
    echo "  ⚠️  RESOURCE CONTENTION: Cluster may not have enough CPU/memory"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "  ✅ No critical issues detected!"
else
    echo ""
    echo "  Found $ISSUES issue(s) that need attention."
fi

echo ""
echo "3️⃣ Recommended Fixes:"
echo ""

# Fix 1: Scale down if too many replicas
if [ "$CURRENT_REPLICAS" -gt 5 ]; then
    echo "  🔧 Scale down deployment to 2-3 replicas:"
    echo "     kubectl scale deployment cloud-trader -n $NAMESPACE --replicas=2"
fi

# Fix 2: Update DNS
if [ "$DNS_IP" != "$LB_IP" ] && [ -n "$LB_IP" ]; then
    echo "  🔧 Update DNS A record for $DOMAIN to point to $LB_IP"
    echo "     (Check your DNS provider - Cloud DNS, Namecheap, etc.)"
fi

# Fix 3: Check ingress configuration
echo "  🔧 Verify ingress is using correct IP:"
echo "     kubectl describe ingress -n $NAMESPACE cloud-trader-ingress"

echo ""
echo "4️⃣ Next Steps:"
echo "  1. Fix DNS to point to LoadBalancer IP: $LB_IP"
echo "  2. Wait 5-10 minutes for DNS propagation"
echo "  3. Check SSL certificate status:"
echo "     kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert"
echo "  4. Scale down if needed to free resources"
echo ""

