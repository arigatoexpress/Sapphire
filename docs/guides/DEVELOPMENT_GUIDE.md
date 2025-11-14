# Sapphire AI Trading System - Development Guide

## Overview

This guide covers the complete development workflow for the Sapphire AI Trading System, a multi-agent trading platform built with Python, FastAPI, Kubernetes, and modern AI technologies.

## 🏗️ Architecture Overview

### Core Components
- **6 Specialized AI Agents**: Analysis, strategy, and execution agents
- **MCP Coordinator**: Multi-agent communication protocol
- **Cloud Trader API**: REST API for portfolio management
- **Mission Control Dashboard**: Real-time monitoring interface
- **Redis Cache**: High-performance data caching
- **Vertex AI Integration**: Google Gemini models for intelligence

### Technology Stack
- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Frontend**: React, TypeScript, Material-UI, Vite
- **Infrastructure**: Google Kubernetes Engine (GKE)
- **AI/ML**: Google Vertex AI (Gemini 2.0 Flash)
- **Database**: Redis for caching, BigQuery for analytics
- **Exchange**: Aster DEX API integration

## 🚀 Development Setup

### Prerequisites
```bash
# Required tools
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- kubectl & gcloud CLI
- Git

# GCP Resources
- GKE cluster
- Artifact Registry
- BigQuery dataset
- Vertex AI API access
```

### 1. Clone and Setup
```bash
git clone https://github.com/your-org/sapphire-trading.git
cd sapphire-trading

# Setup Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Setup Node.js environment
cd trading-dashboard
npm install
cd ..
```

### 2. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Configure required variables
export GCP_PROJECT_ID="your-project-id"
export ASTER_API_KEY="your-api-key"
export ASTER_SECRET_KEY="your-secret-key"
export VERTEX_AI_PROJECT="your-project-id"
export REDIS_URL="redis://localhost:6379"
```

### 3. Local Development
```bash
# Start local services
docker-compose up -d redis

# Run backend services
python -m cloud_trader.service

# Run frontend (separate terminal)
cd trading-dashboard
npm run dev

# Access interfaces
# Backend API: http://localhost:8080
# Frontend Dashboard: http://localhost:3000
# Mission Control: http://localhost:3000/mission-control
```

## 🧪 Testing & Quality Assurance

### Unit Testing
```bash
# Run backend tests
pytest tests/ -v --cov=cloud_trader --cov-report=html

# Run frontend tests
cd trading-dashboard
npm test

# Run integration tests
pytest tests/integration/ -v
```

### Code Quality
```bash
# Linting and formatting
flake8 cloud_trader/
black cloud_trader/
isort cloud_trader/

# Type checking
mypy cloud_trader/

# Frontend quality
cd trading-dashboard
npm run lint
npm run type-check
```

### Performance Testing
```bash
# Load testing
locust -f tests/load/locustfile.py

# Memory profiling
python -m memory_profiler cloud_trader/service.py

# API benchmarking
ab -n 1000 -c 10 http://localhost:8080/health
```

## 🔧 Development Workflow

### Feature Development
```bash
# Create feature branch
git checkout -b feature/new-trading-strategy

# Make changes with tests
# Implement feature
# Add unit tests
# Update documentation

# Commit changes
git add .
git commit -m "feat: add new trading strategy with comprehensive tests"

# Push and create PR
git push origin feature/new-trading-strategy
```

### Agent Development
```bash
# Create new agent
python scripts/create_agent.py --name "NewAgent" --type "analysis"

# Implement agent logic in cloud_trader/agents/new_agent.py
# Add agent configuration to agent-resource-tiers.yaml
# Update MCP coordinator registration
# Add agent to deployment manifests
```

### Database Schema Changes
```bash
# Create migration
alembic revision -m "add new trading metrics table"

# Apply migration
alembic upgrade head

# Update models
# Update API endpoints
# Update frontend interfaces
```

## 📦 Building & Packaging

### Docker Build
```bash
# Build optimized image
docker build -t sapphire-trader:latest \
  --build-arg CACHE_BUST=$(date +%s) \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  .

# Tag for registry
docker tag sapphire-trader:latest \
  us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/cloud-trader:latest

# Push to registry
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/cloud-trader:latest
```

### Cloud Build (CI/CD)
```bash
# Trigger automated build
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _IMAGE_TAG=$(git rev-parse --short HEAD)

# Build with specific optimizations
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _IMAGE_TAG=optimized \
  --machine-type=E2_HIGHCPU_32
```

## 🔒 Security & Compliance

### API Key Management
```bash
# Use secret manager for production
gcloud secrets create aster-credentials \
  --data-file=credentials.json

# Access in application
from google.cloud import secretmanager
client = secretmanager.SecretManagerServiceClient()
secret = client.access_secret_version(name=secret_name)
```

### Code Security
```bash
# Security scanning
snyk test
trivy image your-image:latest

# Dependency vulnerability check
safety check
pip-audit
```

### Compliance Checks
```bash
# Regulatory compliance verification
python scripts/compliance_check.py

# Risk assessment
python scripts/risk_assessment.py --portfolio-analysis

# Audit logging verification
python scripts/audit_verification.py
```

## 🐛 Debugging & Troubleshooting

### Common Issues

#### Agent Not Starting
```bash
# Check agent logs
kubectl logs deployment/<agent-name> -n trading-system

# Verify agent registration
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -c "from cloud_trader.mcp_coordinator import MCPCoordinator; print(coordinator.list_agents())"

# Check resource allocation
kubectl describe pod <agent-pod> -n trading-system
```

#### API Connectivity Issues
```bash
# Test exchange API
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -c "from cloud_trader.exchange import AsterClient; client = AsterClient(); print(client.test_connection())"

# Check network policies
kubectl get networkpolicies -n trading-system

# Verify service mesh
istioctl proxy-status
```

#### Performance Issues
```bash
# Monitor resource usage
kubectl top pods -n trading-system

# Check memory leaks
kubectl exec deployment/<agent-name> -n trading-system -- \
  python -m memory_profiler agent_script.py

# Profile performance
kubectl exec deployment/<agent-name> -n trading-system -- \
  python -m cProfile -s cumtime agent_script.py
```

### Debug Commands
```bash
# Port forward for local debugging
kubectl port-forward svc/trading-coordinator-service 8080:8080 -n trading-system

# Exec into running pod
kubectl exec -it deployment/trading-coordinator -n trading-system -- /bin/bash

# View detailed pod information
kubectl describe pod <pod-name> -n trading-system

# Check cluster events
kubectl get events -n trading-system --sort-by=.metadata.creationTimestamp
```

## 📊 Monitoring & Observability

### Application Metrics
```bash
# Prometheus metrics
curl http://localhost:9090/api/v1/query?query=trading_system_active_agents

# Custom metrics
curl http://localhost:8080/metrics

# Health checks
curl http://localhost:8080/health
```

### Logging
```bash
# Structured logging
import structlog
logger = structlog.get_logger()
logger.info("trade_executed", symbol="BTCUSDT", amount=0.1, price=45000)

# Log aggregation
kubectl logs -l app=trading-coordinator -n trading-system --tail=100

# Log analysis
python scripts/log_analyzer.py --time-range=24h --filter=ERROR
```

### Alerting
```bash
# Set up alerts
kubectl apply -f monitoring/alerts.yaml

# Custom alert rules
groups:
- name: trading_system_alerts
  rules:
  - alert: HighLatency
    expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
    labels:
      severity: warning
```

## 🚀 Deployment Strategies

### Development Environment
```bash
# Local deployment
docker-compose up -d

# Minikube deployment
kubectl apply -f k8s-dev/

# Skaffold for continuous development
skaffold dev
```

### Staging Environment
```bash
# Deploy to staging
kubectl apply -f k8s-staging/ -n staging

# Run integration tests
pytest tests/integration/ -m staging

# Performance validation
python scripts/performance_test.py --environment=staging
```

### Production Environment
```bash
# Blue-green deployment
kubectl apply -f k8s-prod-blue/
kubectl apply -f k8s-prod-green/

# Canary deployment
kubectl apply -f k8s-prod-canary/

# Rollback if needed
kubectl rollout undo deployment/trading-coordinator -n production
```

## 📚 Additional Resources

### Documentation
- [API Reference](./API_REFERENCE.md)
- [Architecture Decision Records](./ADR/)
- [Security Guidelines](./SECURITY.md)
- [Performance Benchmarks](./PERFORMANCE.md)

### External Links
- [Google Cloud Documentation](https://cloud.google.com/docs)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Material-UI Documentation](https://mui.com/)

### Support
- **Internal Wiki**: Company internal documentation
- **Slack Channels**: #dev-trading, #dev-infra, #dev-ai
- **Issue Tracking**: GitHub Issues with labels

---

## Quick Start Checklist

- [ ] Development environment setup
- [ ] Code cloned and dependencies installed
- [ ] Environment variables configured
- [ ] Local services running
- [ ] Tests passing
- [ ] Code quality checks passed
- [ ] Documentation updated
- [ ] Security review completed
- [ ] Ready for deployment

For detailed deployment instructions, see [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).
