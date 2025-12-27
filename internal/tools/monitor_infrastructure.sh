#!/bin/bash
echo "🔍 INFRASTRUCTURE MONITORING - $(date)"

echo ""
echo "📊 GKE CLUSTER STATUS:"
kubectl get pods -n trading --no-headers | wc -l | xargs echo "Pods running:"

echo ""
echo "🌐 LOAD BALANCER STATUS:"
kubectl get ingress -n trading -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "IP: Not assigned yet"

echo ""
echo "🔒 SSL CERTIFICATE STATUS:"
kubectl get managedcertificate -n trading -o jsonpath='{.items[0].status.certificateStatus}' 2>/dev/null || echo "Status: Still provisioning"

echo ""
echo "✅ SERVICE AVAILABILITY:"
echo "New Frontend: $(curl -s -o /dev/null -w "%{http_code}" https://sapphireinfinite.web.app)"
echo "Old Frontend: $(curl -s -o /dev/null -w "%{http_code}" https://sapphiretrade.xyz)"

echo ""
echo "⏱️  INFRASTRUCTURE AGE:"
kubectl get ingress -n trading -o jsonpath='{.items[0].metadata.creationTimestamp}' | xargs -I {} date -d {} +"%H:%M:%S ago" 2>/dev/null || echo "Age: Calculating..."
