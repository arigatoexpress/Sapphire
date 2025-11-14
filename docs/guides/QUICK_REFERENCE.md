# Sapphire Trading - Quick Reference Guide

## 🚀 One-Command Deployments

### Fresh Environment Setup
```bash
# Complete fresh deployment
./scripts/fresh-deploy.sh

# Quick development setup
./scripts/dev-setup.sh

# Production deployment
./scripts/prod-deploy.sh
```

### Component-Specific Deployments
```bash
# Deploy only agents
./deploy-agents.sh

# Deploy only infrastructure
./deploy-infrastructure.sh

# Deploy only frontend
./scripts/deploy-frontend.sh
```

## 🔧 Common kubectl Commands

### Pod Management
```bash
# Get pod status
kubectl get pods -n trading-system

# View pod logs
kubectl logs deployment/trading-coordinator -n trading-system -f

# Exec into pod
kubectl exec -it deployment/trading-coordinator -n trading-system -- /bin/bash

# Debug pod
kubectl describe pod <pod-name> -n trading-system

# Restart deployment
kubectl rollout restart deployment/trading-coordinator -n trading-system
```

### Service Management
```bash
# Get services
kubectl get services -n trading-system

# Port forward
kubectl port-forward svc/trading-coordinator-service 8080:8080 -n trading-system

# Check endpoints
kubectl get endpoints -n trading-system
```

### Troubleshooting
```bash
# Check events
kubectl get events -n trading-system --sort-by=.metadata.creationTimestamp

# Check resource usage
kubectl top pods -n trading-system

# Check cluster status
kubectl cluster-info

# Check node status
kubectl get nodes
```

## 📊 Health Checks & Monitoring

### Application Health
```bash
# Coordinator health
curl http://coordinator-service.trading-system.svc.cluster.local:8080/health

# Agent health
curl http://trend-momentum-agent-service.trading-system.svc.cluster.local:8080/health

# All agent health
kubectl get pods -n trading-system -o jsonpath='{.items[*].status.phase}'
```

### Metrics & Logs
```bash
# Application metrics
curl http://coordinator-service:8080/metrics

# System metrics
kubectl top nodes
kubectl top pods -n trading-system

# Recent logs
kubectl logs --since=1h -l app=trading-coordinator -n trading-system
```

## 🔧 Development Workflow

### Code Changes
```bash
# Create feature branch
git checkout -b feature/new-agent

# Make changes
# Add tests
# Update docs

# Commit and push
git add .
git commit -m "feat: add new agent functionality"
git push origin feature/new-agent

# Create PR
# CI/CD will run automatically
```

### Testing
```bash
# Unit tests
pytest tests/ -v

# Integration tests
pytest tests/integration/ -v

# Load tests
locust -f tests/load/locustfile.py

# Code quality
flake8 cloud_trader/
black cloud_trader/ --check
```

### Building
```bash
# Local build
docker build -t sapphire-trader:latest .

# Cloud build
gcloud builds submit --config cloudbuild.yaml

# Build with specific tag
gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE_TAG=v1.2.3
```

## 🚨 Emergency Procedures

### Rollback Deployment
```bash
# Immediate rollback
kubectl rollout undo deployment/trading-coordinator -n trading-system

# Rollback to specific revision
kubectl rollout undo deployment/trading-coordinator --to-revision=2 -n trading-system

# Check rollout history
kubectl rollout history deployment/trading-coordinator -n trading-system
```

### Scale Down Services
```bash
# Stop all trading
kubectl scale deployment --all --replicas=0 -n trading-system

# Stop specific agent
kubectl scale deployment trend-momentum-agent --replicas=0 -n trading-system

# Emergency stop all
kubectl delete namespace trading-system --ignore-not-found=true
```

### Data Recovery
```bash
# Backup current state
kubectl get all -n trading-system -o yaml > backup-$(date +%Y%m%d-%H%M%S).yaml

# Restore from backup
kubectl apply -f backup-20241114-120000.yaml

# Check BigQuery backups
bq ls --project_id=$PROJECT_ID
```

## 🔍 Debugging Commands

### Network Debugging
```bash
# Test service connectivity
kubectl run test-pod --image=busybox --rm -it -n trading-system -- \
  wget -qO- http://coordinator-service:8080/health

# DNS resolution
kubectl exec deployment/trading-coordinator -n trading-system -- \
  nslookup redis-service.trading-system.svc.cluster.local

# Network policies
kubectl get networkpolicies -n trading-system
```

### Performance Debugging
```bash
# CPU/Memory usage
kubectl top pods -n trading-system

# Pod resource limits
kubectl describe pod <pod-name> -n trading-system | grep -A 10 "Limits:"

# Application profiling
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -m cProfile -s cumtime cloud_trader/service.py
```

### Log Analysis
```bash
# Search for errors
kubectl logs deployment/trading-coordinator -n trading-system | grep ERROR

# Recent errors
kubectl logs deployment/trading-coordinator -n trading-system --since=1h | grep -i error

# Correlated logs
stern "trading-coordinator" -n trading-system --since=1h
```

## ⚙️ Configuration Reference

### Environment Variables
```bash
# Required
GCP_PROJECT_ID=your-project-id
ASTER_API_KEY=your-api-key
ASTER_SECRET_KEY=your-secret-key

# Optional
LOG_LEVEL=INFO
REDIS_URL=redis://redis-service:6379
METRICS_ENABLED=true
HEALTH_CHECK_INTERVAL=30
```

### Agent Configuration
```yaml
# agent-resource-tiers.yaml
trend-momentum-agent:
  cpu: 500m
  memory: 1Gi
  replicas: 1

strategy-optimization-agent:
  cpu: 750m
  memory: 2Gi
  replicas: 1
```

### Service Ports
```yaml
Coordinator: 8080
Agents: 8080
Frontend: 3000
Redis: 6379
Metrics: 9090
```

## 📞 Support & Escalation

### Internal Support
```bash
# Slack channels
#dev-trading    - Development discussions
#dev-infra      - Infrastructure issues
#dev-ai         - AI/ML questions
#prod-support   - Production issues

# Emergency contacts
DevOps Lead: @devops-lead
Trading Lead: @trading-lead
Security: @security-team
```

### External Resources
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [GCP Documentation](https://cloud.google.com/docs)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Material-UI Docs](https://mui.com/)

### Issue Reporting
```bash
# Bug report template
Title: [BUG] Brief description
Environment: dev/staging/prod
Severity: low/medium/high/critical
Steps to reproduce:
1. Step 1
2. Step 2
Expected: What should happen
Actual: What actually happened
Logs: Relevant log snippets
```

---

## 📝 Checklists

### Pre-Deployment Checklist
- [ ] Code reviewed and approved
- [ ] Tests passing (unit, integration, e2e)
- [ ] Security scan passed
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Rollback plan documented
- [ ] Stakeholders notified

### Post-Deployment Checklist
- [ ] Services healthy (all pods ready)
- [ ] Health checks passing
- [ ] Metrics collecting data
- [ ] Logs flowing to aggregation
- [ ] Monitoring alerts configured
- [ ] Load balancer routing traffic
- [ ] SSL certificates valid

### Emergency Response Checklist
- [ ] Assess impact and severity
- [ ] Notify stakeholders
- [ ] Scale down if needed
- [ ] Investigate root cause
- [ ] Implement fix
- [ ] Test fix in staging
- [ ] Deploy fix to production
- [ ] Monitor for 24-48 hours
- [ ] Document incident and resolution
