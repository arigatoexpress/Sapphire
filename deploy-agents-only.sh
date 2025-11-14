#!/bin/bash

# Deploy agents only - coordinator infrastructure already deployed

NAMESPACE="trading-system-clean"
IMAGE="us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest"

echo "🤖 Deploying AI Trading Agents"
echo "=============================="

# Create agent deployments
cat > agent-deployment-template.yaml << AGENT_EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {AGENT_NAME}
  namespace: trading-system-clean
  labels:
    app: {AGENT_NAME}
    component: trading-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {AGENT_NAME}
  template:
    metadata:
      labels:
        app: {AGENT_NAME}
        component: trading-agent
    spec:
      containers:
      - name: {AGENT_NAME}
        image: $IMAGE
        command: ["python", "-m", "cloud_trader.service"]
        env:
        - name: AGENT_ID
          value: "{AGENT_NAME}"
        - name: CAPITAL_ALLOCATION
          value: "500"
        - name: ENABLE_PAPER_TRADING
          value: "false"
        - name: MCP_URL
          value: "http://coordinator-service:8080"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 500m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: {AGENT_NAME}-service
  namespace: trading-system-clean
  labels:
    app: {AGENT_NAME}
    component: trading-agent
spec:
  selector:
    app: {AGENT_NAME}
  ports:
  - port: 8080
    targetPort: 8080
    protocol: TCP
AGENT_EOF

# Deploy each agent
AGENTS=("trend-momentum-agent" "strategy-optimization-agent" "financial-sentiment-agent" "market-prediction-agent" "volume-microstructure-agent" "vpin-hft")

for agent in "${AGENTS[@]}"; do
    echo "Deploying $agent..."
    sed "s/{AGENT_NAME}/$agent/g" agent-deployment-template.yaml | kubectl apply -f -
done

# Cleanup
rm agent-deployment-template.yaml

echo "⏳ Waiting for agents to deploy..."
for agent in "${AGENTS[@]}"; do
    kubectl wait --for=condition=available --timeout=300s deployment/"$agent" -n "$NAMESPACE" || echo "Warning: $agent deployment timeout"
done

echo "✅ Agent deployment complete!"
kubectl get pods -n "$NAMESPACE"
