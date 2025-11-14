#!/bin/bash

# Improved bot deployment with proper resource allocation

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
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${BOT_NAME}-config
  namespace: trading
data:
  BOT_NAME: "${BOT_NAME}"
  BOT_STRATEGY: "${STRATEGY}"
  CAPITAL_ALLOCATION: "${CAPITAL}"
  RISK_LEVEL: "${RISK}"
  ASTER_BASE_URL: "https://fapi.asterdex.com"
  TELEGRAM_ENABLED: "true"
  LOG_LEVEL: "INFO"
  METRICS_ENABLED: "true"
