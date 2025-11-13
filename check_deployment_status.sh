#!/bin/bash
# Quick status check for deployment

PROJECT_ID="sapphireinfinite"
NAMESPACE="trading"
DOMAIN="api.sapphiretrade.xyz"

echo "📊 SAPPHIRE Deployment Status"
echo "=============================="
echo ""

echo "Pods:"
kubectl get pods -n $NAMESPACE --no-headers | awk '{printf "  %s: %s\n", $1, $3}'
echo ""

echo "Deployment:"
kubectl get deployment -n $NAMESPACE cloud-trader -o jsonpath='  Replicas: {.spec.replicas} (Ready: {.status.readyReplicas}/{.status.replicas})' 2>/dev/null
echo ""
echo ""

echo "LoadBalancer IP:"
kubectl get svc -n $NAMESPACE cloud-trader-service -o jsonpath='  {.status.loadBalancer.ingress[0].ip}' 2>/dev/null
echo ""
echo ""

echo "Static IP (Ingress):"
gcloud compute addresses describe cloud-trader-ip --global --project=$PROJECT_ID --format="get(address)" 2>/dev/null
echo ""
echo ""

echo "DNS Resolution:"
nslookup $DOMAIN 2>/dev/null | grep -A 1 "Name:" | tail -1 | awk '{print "  " $0}'
echo ""

echo "SSL Certificate:"
CERT_STATUS=$(kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.certificateStatus}' 2>/dev/null)
DOMAIN_STATUS=$(kubectl get managedcertificate -n $NAMESPACE cloud-trader-cert -o jsonpath='{.status.domainStatus[0].status}' 2>/dev/null)
echo "  Status: $CERT_STATUS"
echo "  Domain: $DOMAIN_STATUS"
echo ""

echo "Ingress:"
INGRESS_IP=$(kubectl get ingress -n $NAMESPACE cloud-trader-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [ -z "$INGRESS_IP" ]; then
    echo "  Address: (provisioning...)"
else
    echo "  Address: $INGRESS_IP"
fi
echo ""

