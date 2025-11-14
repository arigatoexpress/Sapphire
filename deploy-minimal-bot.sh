#!/bin/bash

# Deploy bot with minimal resources

BOT_NAME="minimal-trading-bot"
STRATEGY="basic-trend-following"

echo "🤖 DEPLOYING MINIMAL BOT: $BOT_NAME"

# Create minimal ConfigMap
kubectl create configmap "$BOT_NAME-config" \
  --from-literal=BOT_NAME="$BOT_NAME" \
  --from-literal=BOT_STRATEGY="$STRATEGY" \
  --from-literal=CAPITAL_ALLOCATION="100" \
  --from-literal=TELEGRAM_ENABLED="true" \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

# Create minimal Deployment
kubectl create deployment "$BOT_NAME" \
  --image=us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest \
  --replicas=1 \
  --port=8080 \
  --requests='cpu=50m,memory=64Mi' \
  --limits='cpu=100m,memory=128Mi' \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

# Add environment variables
kubectl patch deployment "$BOT_NAME" -n trading --type='json' -p='[
  {"op": "add", "path": "/spec/template/spec/containers/0/env", "value": [
    {"name": "BOT_NAME", "valueFrom": {"configMapKeyRef": {"name": "'$BOT_NAME'-config", "key": "BOT_NAME"}}},
    {"name": "BOT_STRATEGY", "valueFrom": {"configMapKeyRef": {"name": "'$BOT_NAME'-config", "key": "BOT_STRATEGY"}}},
    {"name": "CAPITAL_ALLOCATION", "valueFrom": {"configMapKeyRef": {"name": "'$BOT_NAME'-config", "key": "CAPITAL_ALLOCATION"}}},
    {"name": "TELEGRAM_BOT_TOKEN", "valueFrom": {"secretKeyRef": {"name": "telegram-secret", "key": "TELEGRAM_BOT_TOKEN"}}},
    {"name": "TELEGRAM_CHAT_ID", "valueFrom": {"secretKeyRef": {"name": "telegram-secret", "key": "TELEGRAM_CHAT_ID"}}},
    {"name": "TELEGRAM_ENABLED", "valueFrom": {"configMapKeyRef": {"name": "'$BOT_NAME'-config", "key": "TELEGRAM_ENABLED"}}}
  ]}
]'

echo "✅ Minimal bot deployed!"
kubectl get pods -n trading -l app=$BOT_NAME
