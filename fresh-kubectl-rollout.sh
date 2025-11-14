#!/bin/bash

# Fresh Kubernetes Rollout Script
# Clean deployment with fixed components

set -e

NAMESPACE="trading-system-clean"
IMAGE="us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:fresh-deploy"

echo "🚀 Starting Fresh Kubernetes Rollout"
echo "===================================="

# Clean any old deployments in the namespace
echo "🧹 Cleaning existing deployments..."
kubectl delete deployment --all -n "$NAMESPACE" --ignore-not-found=true
kubectl delete service --all -n "$NAMESPACE" --ignore-not-found=true
kubectl delete configmap --all -n "$NAMESPACE" --ignore-not-found=true
kubectl delete secret --all -n "$NAMESPACE" --ignore-not-found=true

echo "⏳ Waiting for cleanup..."
sleep 10

# Deploy infrastructure components
echo "🏗️  Deploying infrastructure..."

# Redis
kubectl apply -f k8s-deployment-redis.yaml -n "$NAMESPACE"

# ConfigMaps and Secrets
kubectl apply -f k8s-configmap-prometheus.yaml -n "$NAMESPACE"
kubectl apply -f k8s-secrets.yaml -n "$NAMESPACE"

# Coordinator
kubectl apply -f k8s-service-mcp-coordinator.yaml -n "$NAMESPACE"
kubectl apply -f k8s-deployment-mcp-coordinator.yaml -n "$NAMESPACE"

echo "⏳ Waiting for infrastructure to stabilize..."
kubectl wait --for=condition=available --timeout=300s deployment/redis -n "$NAMESPACE"
kubectl wait --for=condition=available --timeout=300s deployment/trading-coordinator -n "$NAMESPACE"

# Deploy agents
echo "🤖 Deploying trading agents..."

# Create agent deployments with proper resource allocation
cat > agent-deployment-template.yaml << AGENT_EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {AGENT_NAME}
  namespace: trading-system-fresh
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
  namespace: trading-system-fresh
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

# Cleanup template
rm agent-deployment-template.yaml

echo "⏳ Waiting for agents to deploy..."
for agent in "${AGENTS[@]}"; do
    kubectl wait --for=condition=available --timeout=300s deployment/"$agent" -n "$NAMESPACE" || echo "Warning: $agent deployment timeout"
done

echo "✅ Fresh rollout complete!"
echo "📊 Checking deployment status..."
kubectl get pods -n "$NAMESPACE"
kubectl get services -n "$NAMESPACE"

echo ""
echo "🎯 Next steps:"
echo "1. Verify agent logs: kubectl logs -f deployment/<agent-name> -n $NAMESPACE"
echo "2. Check health endpoints: kubectl port-forward svc/<agent-name>-service 8080 -n $NAMESPACE"
echo "3. Monitor trading: kubectl logs -f deployment/trading-coordinator -n $NAMESPACE"
