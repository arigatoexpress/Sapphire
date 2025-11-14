#!/bin/bash

# Fixed bot deployment script

if [ $# -lt 2 ]; then
    echo "Usage: $0 <bot-name> <strategy> [capital] [risk]"
    exit 1
fi

BOT_NAME="$1"
STRATEGY="$2"
CAPITAL="${3:-500}"
RISK="${4:-medium}"

echo "🤖 DEPLOYING BOT: $BOT_NAME"
echo "Strategy: $STRATEGY"
echo "Capital: $CAPITAL"
echo "Risk: $RISK"
echo ""

# Create ConfigMap
kubectl create configmap "${BOT_NAME}-config" \
  --from-literal=BOT_NAME="$BOT_NAME" \
  --from-literal=BOT_STRATEGY="$STRATEGY" \
  --from-literal=CAPITAL_ALLOCATION="$CAPITAL" \
  --from-literal=RISK_LEVEL="$RISK" \
  --from-literal=ASTER_BASE_URL="https://fapi.asterdex.com" \
  --from-literal=TELEGRAM_ENABLED="true" \
  --from-literal=LOG_LEVEL="INFO" \
  --from-literal=METRICS_ENABLED="true" \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

# Create Deployment
kubectl create deployment "$BOT_NAME" \
  --image=us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest \
  --replicas=1 \
  --port=8080 \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

# Patch with environment variables
kubectl patch deployment "$BOT_NAME" -n trading --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/containers/0/env", "value": [
    {"name": "BOT_NAME", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "BOT_NAME"}}},
    {"name": "BOT_STRATEGY", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "BOT_STRATEGY"}}},
    {"name": "CAPITAL_ALLOCATION", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "CAPITAL_ALLOCATION"}}},
    {"name": "RISK_LEVEL", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "RISK_LEVEL"}}},
    {"name": "ASTER_API_KEY", "valueFrom": {"secretKeyRef": {"name": "aster-dex-credentials", "key": "api_key"}}},
    {"name": "ASTER_API_SECRET", "valueFrom": {"secretKeyRef": {"name": "aster-dex-credentials", "key": "api_secret"}}},
    {"name": "ASTER_BASE_URL", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "ASTER_BASE_URL"}}},
    {"name": "TELEGRAM_BOT_TOKEN", "valueFrom": {"secretKeyRef": {"name": "telegram-secret", "key": "TELEGRAM_BOT_TOKEN"}}},
    {"name": "TELEGRAM_CHAT_ID", "valueFrom": {"secretKeyRef": {"name": "telegram-secret", "key": "TELEGRAM_CHAT_ID"}}},
    {"name": "TELEGRAM_ENABLED", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "TELEGRAM_ENABLED"}}},
    {"name": "LOG_LEVEL", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "LOG_LEVEL"}}},
    {"name": "METRICS_ENABLED", "valueFrom": {"configMapKeyRef": {"name": "'${BOT_NAME}'-config", "key": "METRICS_ENABLED"}}}
  ]},
  {"op": "add", "path": "/spec/template/spec/containers/0/resources", "value": {
    "requests": {"memory": "256Mi", "cpu": "200m"},
    "limits": {"memory": "512Mi", "cpu": "500m"}
  }},
  {"op": "add", "path": "/spec/template/spec/containers/0/livenessProbe", "value": {
    "httpGet": {"path": "/health", "port": 8080},
    "initialDelaySeconds": 30,
    "periodSeconds": 10
  }},
  {"op": "add", "path": "/spec/template/spec/containers/0/readinessProbe", "value": {
    "httpGet": {"path": "/ready", "port": 8080},
    "initialDelaySeconds": 5,
    "periodSeconds": 5
  }}
]'

# Create Service
kubectl create service clusterip "${BOT_NAME}-service" \
  --tcp=8080:8080 \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Bot $BOT_NAME deployment completed!"
echo "Waiting for pod to start..."
sleep 5
kubectl get pods -n trading -l app=$BOT_NAME
