#!/bin/bash
set -e

# Sapphire Trading System - Streamlined Deployment
echo "🚀 Sapphire Trading System Deployment"
echo "====================================="

# Configuration
PROJECT_ID="sapphireinfinite"
TRADING_NS="trading"
MONITORING_NS="monitoring"

echo "📋 Step 1: Setting up infrastructure..."
kubectl create namespace trading --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true

# Deploy Redis
echo "🐘 Deploying Redis..."
kubectl apply -f - >/dev/null 2>&1 <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: trading
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 300m
            memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: trading
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
  type: ClusterIP
