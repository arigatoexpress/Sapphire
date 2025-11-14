# Sapphire AI Trading System - Deployment Guide

## Overview

This guide provides comprehensive deployment instructions for the Sapphire AI Trading System across multiple environments and deployment strategies.

## 📋 Prerequisites

### Required Tools
```bash
# Core tools
kubectl >= 1.25.0
gcloud >= 400.0.0
docker >= 20.10.0
helm >= 3.10.0

# Optional but recommended
skaffold >= 2.0.0
kustomize >= 4.5.0
stern >= 1.21.0
k9s >= 0.25.0
```

### Infrastructure Requirements
```yaml
# GCP Resources
- GKE Cluster (e2-standard-8 nodes, autoscaling enabled)
- Artifact Registry repository
- BigQuery dataset
- Vertex AI API enabled
- Static IP for load balancer
- Managed SSL certificate

# Resource Allocation (Production)
- CPU: 16 cores minimum, 32 cores recommended
- Memory: 32GB minimum, 64GB recommended
- Storage: 500GB SSD for logs and metrics
- Network: 10Gbps bandwidth
```

## 🚀 Quick Start Deployment

### Automated Deployment Script
```bash
# One-command deployment (recommended for new deployments)
git clone https://github.com/your-org/sapphire-trading.git
cd sapphire-trading

# Configure environment
export GCP_PROJECT_ID="your-project-id"
export GCP_ZONE="us-central1-a"
export CLUSTER_NAME="hft-trading-cluster"

# Run automated deployment
./deploy-full-system.sh
```

### Manual Step-by-Step Deployment
```bash
# 1. Authenticate and set project
gcloud auth login
gcloud config set project $GCP_PROJECT_ID
gcloud config set compute/zone $GCP_ZONE

# 2. Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME

# 3. Create namespace
kubectl create namespace trading-system

# 4. Deploy infrastructure
kubectl apply -f infrastructure-as-code-framework.yaml

# 5. Deploy application
kubectl apply -f k8s-deployment.yaml
kubectl apply -f k8s-service.yaml

# 6. Verify deployment
kubectl get pods -n trading-system
kubectl get services -n trading-system
```

## 🐳 Container Strategy

### Multi-Stage Docker Build
```dockerfile
# Build stage
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Runtime stage
FROM python:3.11-slim as runtime
WORKDIR /app

# Install runtime dependencies only
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY cloud_trader/ ./cloud_trader/
COPY trading-dashboard/ ./trading-dashboard/

# Security hardening
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8080
CMD ["python", "-m", "cloud_trader.service"]
```

### Build Optimization
```bash
# Multi-platform build
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag sapphire-trader:latest \
  --push \
  .

# Build with cache mounts
DOCKER_BUILDKIT=1 docker build \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  --cache-from sapphire-trader:latest \
  -t sapphire-trader:v1.2.3 \
  .
```

## ☸️ Kubernetes Deployment Strategies

### 1. Declarative Deployment (Recommended)
```bash
# Apply all manifests
kubectl apply -k k8s/base/

# Wait for rollout
kubectl wait --for=condition=available --timeout=600s \
  deployment/trading-coordinator -n trading-system

# Verify health
kubectl get pods -n trading-system
kubectl get services -n trading-system
```

### 2. Helm Chart Deployment
```bash
# Add repository
helm repo add sapphire-trading https://charts.your-org.com
helm repo update

# Install with custom values
helm install sapphire-trading ./helm/sapphire-trading \
  --namespace trading-system \
  --create-namespace \
  --values values-production.yaml \
  --set image.tag=v1.2.3 \
  --wait

# Upgrade existing deployment
helm upgrade sapphire-trading ./helm/sapphire-trading \
  --namespace trading-system \
  --set image.tag=v1.2.4
```

### 3. Kustomize Deployment
```bash
# Development overlay
kubectl apply -k k8s/overlays/development/

# Staging overlay
kubectl apply -k k8s/overlays/staging/

# Production overlay
kubectl apply -k k8s/overlays/production/
```

### 4. ArgoCD GitOps Deployment
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sapphire-trading
  namespace: argocd
spec:
  project: trading
  source:
    repoURL: https://github.com/your-org/sapphire-trading
    path: k8s/base
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: trading-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## 🔧 Configuration Management

### Environment Variables
```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sapphire-config
data:
  LOG_LEVEL: "INFO"
  METRICS_ENABLED: "true"
  HEALTH_CHECK_INTERVAL: "30"

# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: sapphire-secrets
type: Opaque
data:
  aster-api-key: <base64-encoded>
  aster-secret-key: <base64-encoded>
  vertex-ai-key: <base64-encoded>
```

### Agent Configuration
```yaml
# agent-resource-tiers.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-tiers
data:
  trend-momentum-agent: |
    cpu: 500m
    memory: 1Gi
    replicas: 1
    specialization: momentum-analysis

  strategy-optimization-agent: |
    cpu: 750m
    memory: 2Gi
    replicas: 1
    specialization: strategy-optimization
```

## 📊 Monitoring & Observability

### Prometheus Metrics
```yaml
# prometheus-config.yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sapphire-trading'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: sapphire-trading
        action: keep
    metrics_path: '/metrics'
```

### Logging Aggregation
```yaml
# fluent-bit-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  fluent-bit.conf: |
    [INPUT]
        Name              tail
        Path              /var/log/containers/*sapphire*.log
        Parser            docker
        Tag               sapphire.*
        Refresh_Interval  5

    [OUTPUT]
        Name  gcs
        Match sapphire.*
        Bucket sapphire-logs
        Object_Key logs/{time}-{pod_name}.log
```

### Health Checks
```yaml
# deployment.yaml (excerpt)
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

## 🔒 Security Hardening

### Network Policies
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sapphire-trading-policy
spec:
  podSelector:
    matchLabels:
      app: sapphire-trading
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - ipBlock:
        cidr: 0.0.0.0/0
    ports:
    - protocol: TCP
      port: 443  # Allow HTTPS outbound
```

### Security Context
```yaml
# pod-security.yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-pod
spec:
  securityContext:
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
  containers:
  - name: app
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      runAsNonRoot: true
      capabilities:
        drop:
        - ALL
```

### Secret Management
```bash
# External secrets operator
kubectl apply -f https://raw.githubusercontent.com/external-secrets/external-secrets/main/deploy/crds/bundle.yaml

# GCP Secret Manager integration
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: sapphire-secrets
spec:
  secretStoreRef:
    name: gcp-secret-store
    kind: SecretStore
  target:
    name: sapphire-secrets
    creationPolicy: Owner
  data:
  - secretKey: aster-api-key
    remoteRef:
      key: aster-credentials
      property: api_key
```

## 🚀 Advanced Deployment Patterns

### Blue-Green Deployment
```bash
# Create blue environment
kubectl apply -f k8s/blue/ -n trading-system-blue

# Test blue environment
curl -H "Host: api.sapphiretrade.xyz" http://blue-service/health

# Switch traffic to blue
kubectl patch service trading-service \
  -p '{"spec":{"selector":{"version":"blue"}}}'

# Keep green as rollback option
kubectl scale deployment trading-green --replicas=0
```

### Canary Deployment
```bash
# Deploy canary version
kubectl apply -f k8s/canary/

# Route 10% of traffic to canary
kubectl apply -f istio/canary-virtualservice.yaml

# Monitor canary metrics
kubectl logs -l version=canary -f

# Promote canary to production
kubectl apply -f istio/production-virtualservice.yaml
```

### Rolling Updates
```bash
# Zero-downtime rolling update
kubectl set image deployment/trading-coordinator \
  trading-coordinator=sapphire-trader:v1.2.4

# Monitor rollout
kubectl rollout status deployment/trading-coordinator

# Rollback if needed
kubectl rollout undo deployment/trading-coordinator
```

## 🔧 Troubleshooting Deployment Issues

### Common Issues & Solutions

#### Pod CrashLoopBackOff
```bash
# Check pod logs
kubectl logs <pod-name> -n trading-system --previous

# Check events
kubectl get events -n trading-system --sort-by=.metadata.creationTimestamp

# Debug with ephemeral container
kubectl debug <pod-name> -n trading-system --image=busybox --target=<container-name>
```

#### Service Mesh Issues
```bash
# Check Istio proxy status
kubectl exec <pod-name> -c istio-proxy -- pilot-agent request GET server_info

# View service mesh configuration
istioctl proxy-config routes <pod-name>.trading-system

# Check mutual TLS
istioctl authn tls-check <pod-name>.trading-system
```

#### Resource Constraints
```bash
# Check resource usage
kubectl top pods -n trading-system

# Adjust resource requests/limits
kubectl patch deployment trading-coordinator \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "500m"}]'

# Check cluster capacity
kubectl describe nodes
```

#### Network Issues
```bash
# Test service connectivity
kubectl run test-pod --image=busybox --rm -it -- \
  wget --spider http://trading-service:8080/health

# Check network policies
kubectl get networkpolicies -n trading-system

# Debug DNS resolution
kubectl exec <pod-name> -- nslookup trading-service.trading-system.svc.cluster.local
```

## 📈 Performance Optimization

### Resource Optimization
```yaml
# Optimized deployment
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 2Gi
        env:
        - name: GOMAXPROCS
          value: "2"
        - name: GOGC
          value: "100"
```

### HPA Configuration
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: trading-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: trading-coordinator
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### VPA Configuration
```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: trading-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: trading-coordinator
  updatePolicy:
    updateMode: "Auto"
```

## 🔄 CI/CD Pipeline

### GitHub Actions Workflow
```yaml
name: Deploy to GKE
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    - name: Authenticate to Google Cloud
      uses: google-github-actions/auth@v1
      with:
        credentials_json: ${{ secrets.GCP_SA_KEY }}

    - name: Set up Cloud SDK
      uses: google-github-actions/setup-gcloud@v1

    - name: Build and push Docker image
      run: |
        gcloud builds submit --config cloudbuild.yaml \
          --substitutions _IMAGE_TAG=${{ github.sha }}

    - name: Deploy to GKE
      run: |
        gcloud container clusters get-credentials hft-trading-cluster
        kubectl apply -f k8s/
        kubectl wait --for=condition=available deployment/trading-coordinator
```

### Cloud Build Pipeline
```yaml
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/$PROJECT_ID/sapphire-trader:$COMMIT_SHA', '.']

- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'gcr.io/$PROJECT_ID/sapphire-trader:$COMMIT_SHA']

- name: 'gcr.io/cloud-builders/gcloud'
  args:
  - container
  - clusters
  - get-credentials
  - hft-trading-cluster
  - --zone=us-central1-a

- name: 'gcr.io/cloud-builders/kubectl'
  args:
  - set
  - image
  - deployment/trading-coordinator
  - trading-coordinator=gcr.io/$PROJECT_ID/sapphire-trader:$COMMIT_SHA
  - --namespace=trading-system

- name: 'gcr.io/cloud-builders/kubectl'
  args:
  - rollout
  - status
  - deployment/trading-coordinator
  - --namespace=trading-system
```

## 📚 Alternative Deployment Methods

### Cloud Run (Serverless)
```bash
# Deploy to Cloud Run
gcloud run deploy sapphire-trading \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10 \
  --set-env-vars "REDIS_URL=$REDIS_URL"
```

### Cloud Run Jobs (Batch Processing)
```bash
# Deploy agent as Cloud Run Job
gcloud run jobs create trading-agent \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars "AGENT_TYPE=trend-momentum" \
  --execute-now
```

### App Engine (Flexible)
```yaml
# app.yaml
runtime: python311
instance_class: F4_1G
automatic_scaling:
  min_instances: 1
  max_instances: 10
  target_cpu_utilization: 0.7

env_variables:
  REDIS_URL: redis://redis-service:6379
  GCP_PROJECT_ID: your-project-id

handlers:
- url: /.*
  script: auto
  secure: always
```

## 📊 Monitoring Deployment Health

### Dashboard Queries
```promql
# Pod health
kube_pod_container_status_ready{namespace="trading-system"}

# Resource usage
container_cpu_usage_seconds_total{namespace="trading-system"}

# Application metrics
trading_system_active_agents
trading_system_trades_per_minute
trading_system_api_latency
```

### Alert Rules
```yaml
groups:
- name: deployment_alerts
  rules:
  - alert: DeploymentFailed
    expr: kube_deployment_status_replicas_unavailable > 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Deployment has unavailable replicas"

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
    labels:
      severity: warning
    annotations:
      summary: "High error rate detected"
```

---

## Quick Reference

### Emergency Commands
```bash
# Immediate rollback
kubectl rollout undo deployment/trading-coordinator -n trading-system

# Scale down problematic deployment
kubectl scale deployment trading-coordinator --replicas=0 -n trading-system

# Force restart all pods
kubectl delete pods --all -n trading-system

# Check cluster health
kubectl get componentstatuses
```

### Useful Aliases
```bash
# Add to ~/.bashrc or ~/.zshrc
alias k="kubectl"
alias kgp="kubectl get pods"
alias kgs="kubectl get services"
alias kl="kubectl logs"
alias kdp="kubectl describe pod"
alias kexec="kubectl exec -it"

# Trading system specific
alias kt="kubectl -n trading-system"
alias ktp="kubectl get pods -n trading-system"
alias ktl="kubectl logs -n trading-system"
```

### Health Check Endpoints
- **Coordinator**: `http://coordinator-service:8080/health`
- **Agents**: `http://<agent-service>:8080/health`
- **Frontend**: `http://frontend-service:3000/health`
- **Metrics**: `http://<service>:8080/metrics`

For development workflow, see [DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md).
