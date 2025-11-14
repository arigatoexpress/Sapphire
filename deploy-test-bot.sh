#!/bin/bash

# Test bot deployment with manual configuration

BOT_NAME="test-momentum-bot"
STRATEGY="momentum-analysis"
CAPITAL="500"

echo "🤖 DEPLOYING TEST BOT: $BOT_NAME"
echo "Strategy: $STRATEGY"
echo "Capital: $CAPITAL"
echo ""

# Create ConfigMap
kubectl create configmap "$BOT_NAME-config" \
  --from-literal=BOT_NAME="$BOT_NAME" \
  --from-literal=BOT_STRATEGY="$STRATEGY" \
  --from-literal=CAPITAL_ALLOCATION="$CAPITAL" \
  --from-literal=ASTER_BASE_URL="https://fapi.asterdex.com" \
  --from-literal=TELEGRAM_ENABLED="true" \
  -n trading --dry-run=client -o yaml | kubectl apply -f -

# Create Deployment
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $BOT_NAME
  namespace: trading
spec:
  replicas: 1
  selector:
    matchLabels:
      app: $BOT_NAME
  template:
    metadata:
      labels:
        app: $BOT_NAME
    spec:
      containers:
      - name: $BOT_NAME
        image: us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest
        env:
        - name: BOT_NAME
          valueFrom:
            configMapKeyRef:
              name: ${BOT_NAME}-config
              key: BOT_NAME
        - name: BOT_STRATEGY
          valueFrom:
            configMapKeyRef:
              name: ${BOT_NAME}-config
              key: BOT_STRATEGY
        - name: CAPITAL_ALLOCATION
          valueFrom:
            configMapKeyRef:
              name: ${BOT_NAME}-config
              key: CAPITAL_ALLOCATION
        - name: ASTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: aster-dex-credentials
              key: api_key
        - name: ASTER_API_SECRET
          valueFrom:
            secretKeyRef:
              name: aster-dex-credentials
              key: api_secret
        - name: ASTER_BASE_URL
          valueFrom:
            configMapKeyRef:
              name: ${BOT_NAME}-config
              key: ASTER_BASE_URL
        - name: TELEGRAM_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: telegram-secret
              key: TELEGRAM_BOT_TOKEN
        - name: TELEGRAM_CHAT_ID
          valueFrom:
            secretKeyRef:
              name: telegram-secret
              key: TELEGRAM_CHAT_ID
        - name: TELEGRAM_ENABLED
          valueFrom:
            configMapKeyRef:
              name: ${BOT_NAME}-config
              key: TELEGRAM_ENABLED
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
EOF

# Create Service
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${BOT_NAME}-service
  namespace: trading
spec:
  selector:
    app: $BOT_NAME
  ports:
  - port: 8080
    targetPort: 8080
EOF

echo "✅ Test bot deployment initiated!"
echo "Verifying deployment..."
kubectl get pods -n trading -l app=$BOT_NAME