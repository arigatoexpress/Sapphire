#!/bin/bash
set -e

echo "🚀 Running Sapphire MVP Smoke Tests..."

# Configuration
PROJECT_ID="sapphireinfinite"
CLUSTER_NAME="hft-trading-cluster"
ZONE="us-central1-a"
NAMESPACE="trading"
SERVICE_NAME="cloud-trader-service"

echo "🔍 Checking cluster status..."
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(status)"

echo "🔍 Checking pod status..."
kubectl -n $NAMESPACE get pods

echo "🔍 Testing health endpoint..."
# Wait for service to be ready
kubectl -n $NAMESPACE wait --for=condition=available --timeout=300s deployment/cloud-trader

# Get service IP and test health
SERVICE_IP=$(kubectl -n $NAMESPACE get svc $SERVICE_NAME -o jsonpath='{.spec.clusterIP}')
echo "Service IP: $SERVICE_IP"

# Test health endpoint
curl -f http://$SERVICE_IP/healthz
echo "✅ Health check passed"

echo "🔍 Testing dashboard endpoint..."
curl -f http://$SERVICE_IP/dashboard | head -20
echo "✅ Dashboard endpoint responding"

echo "✅ All smoke tests passed! MVP is live and healthy."
