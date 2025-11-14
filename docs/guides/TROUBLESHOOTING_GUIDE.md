# Sapphire Trading System - Troubleshooting Guide

## Overview

This guide provides systematic troubleshooting procedures for common issues encountered during development, deployment, and operation of the Sapphire AI Trading System.

## 🚨 Emergency Procedures

### Critical System Down
```bash
# Immediate assessment
kubectl get pods -n trading-system
kubectl get nodes

# Stop trading activities
kubectl scale deployment --all --replicas=0 -n trading-system

# Notify stakeholders
# Escalate to incident response team
```

### Data Loss Incident
```bash
# Stop all write operations
kubectl scale deployment --all --replicas=0 -n trading-system

# Assess data loss scope
# Check BigQuery backups
bq ls --project_id=$PROJECT_ID

# Restore from backup
bq cp $PROJECT_ID:backup.dataset_name $PROJECT_ID:production.dataset_name

# Verify data integrity
python scripts/verify_data_integrity.py
```

## 🔍 Systematic Troubleshooting

### 1. Pod Status Issues

#### Pod CrashLoopBackOff
**Symptoms:**
- Pod shows `CrashLoopBackOff` status
- Container restarts repeatedly

**Diagnosis:**
```bash
# Check pod events
kubectl describe pod <pod-name> -n trading-system

# Check container logs
kubectl logs <pod-name> -n trading-system --previous

# Check resource constraints
kubectl get pod <pod-name> -n trading-system -o yaml | grep -A 10 resources
```

**Common Causes & Solutions:**

**Out of Memory:**
```bash
# Check memory usage
kubectl top pod <pod-name> -n trading-system

# Increase memory limits
kubectl patch deployment <deployment-name> \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "2Gi"}]'
```

**Configuration Error:**
```bash
# Check environment variables
kubectl exec <pod-name> -n trading-system -- env | grep -i error

# Check ConfigMap/Secret mounting
kubectl describe pod <pod-name> -n trading-system | grep -A 10 Mounts
```

**Dependency Failure:**
```bash
# Check service dependencies
kubectl get services -n trading-system

# Test connectivity
kubectl exec <pod-name> -n trading-system -- \
  curl -f http://redis-service:6379 || echo "Redis unreachable"
```

#### Pod Pending
**Symptoms:**
- Pod stuck in `Pending` state
- No node assignment

**Diagnosis:**
```bash
# Check pod events
kubectl describe pod <pod-name> -n trading-system

# Check node resources
kubectl describe nodes | grep -A 10 "Allocated resources"

# Check node selectors/tolerations
kubectl get pod <pod-name> -n trading-system -o yaml | grep -A 10 nodeSelector
```

**Common Solutions:**

**Resource Constraints:**
```bash
# Check cluster capacity
kubectl get nodes --show-labels

# Scale cluster or reduce pod requests
gcloud container clusters resize hft-trading-cluster --num-nodes=5
```

**Node Selector Issues:**
```bash
# Remove node selector or update node labels
kubectl patch deployment <deployment-name> \
  --type='json' \
  -p='[{"op": "remove", "path": "/spec/template/spec/nodeSelector"}]'
```

### 2. Service Connectivity Issues

#### Service Unreachable
**Symptoms:**
- `Connection refused` errors
- Service DNS resolution failures

**Diagnosis:**
```bash
# Check service endpoints
kubectl get endpoints -n trading-system

# Test DNS resolution
kubectl exec <pod-name> -n trading-system -- \
  nslookup <service-name>.trading-system.svc.cluster.local

# Check service configuration
kubectl describe service <service-name> -n trading-system
```

**Common Solutions:**

**Service Selector Mismatch:**
```bash
# Check pod labels vs service selector
kubectl get pods -n trading-system --show-labels
kubectl describe service <service-name> -n trading-system
```

**Network Policy Blocking:**
```bash
# Check network policies
kubectl get networkpolicies -n trading-system

# Temporarily disable policies for testing
kubectl delete networkpolicy <policy-name> -n trading-system
```

#### Load Balancer Issues
**Symptoms:**
- External access failing
- Ingress not routing traffic

**Diagnosis:**
```bash
# Check ingress status
kubectl get ingress -n trading-system

# Check load balancer
gcloud compute backend-services list

# Check SSL certificates
gcloud compute ssl-certificates list
```

**Solutions:**
```bash
# Recreate ingress
kubectl delete ingress trading-ingress -n trading-system
kubectl apply -f trading-ingress.yaml

# Check certificate provisioning
gcloud compute ssl-certificates describe sapphire-trading-cert
```

### 3. Agent-Specific Issues

#### Agent Registration Failure
**Symptoms:**
- Agent shows as "idle" or "disconnected"
- MCP communication errors

**Diagnosis:**
```bash
# Check agent registration
kubectl logs deployment/trading-coordinator -n trading-system | grep register

# Test agent-to-coordinator communication
kubectl exec deployment/trend-momentum-agent -n trading-system -- \
  curl -f http://coordinator-service:8080/health
```

**Solutions:**
```bash
# Restart agent registration
kubectl delete pod -l app=trend-momentum-agent -n trading-system

# Check MCP configuration
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -c "from cloud_trader.mcp_coordinator import MCPCoordinator; print(coordinator.list_agents())"
```

#### Trading Strategy Failures
**Symptoms:**
- No trades executed
- Strategy validation errors

**Diagnosis:**
```bash
# Check agent logs
kubectl logs deployment/<agent-name> -n trading-system --tail=100

# Verify market data access
kubectl exec deployment/<agent-name> -n trading-system -- \
  python -c "from cloud_trader.exchange import AsterClient; client = AsterClient(); print(client.test_connection())"

# Check strategy parameters
kubectl exec deployment/<agent-name> -n trading-system -- \
  cat /app/config/agent-config.yaml
```

**Solutions:**
```bash
# Update API credentials
kubectl patch secret aster-dex-credentials \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/aster-api-key", "value": "'$(echo -n "new-key" | base64)'"}]'

# Restart agent with new config
kubectl rollout restart deployment/<agent-name> -n trading-system
```

### 4. Performance Issues

#### High CPU/Memory Usage
**Symptoms:**
- Pod restarts due to resource limits
- Slow response times

**Diagnosis:**
```bash
# Monitor resource usage
kubectl top pods -n trading-system

# Check application metrics
curl http://coordinator-service:8080/metrics

# Profile application
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -m memory_profiler cloud_trader/service.py
```

**Optimization Solutions:**
```bash
# Adjust resource limits
kubectl patch deployment trading-coordinator \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "1000m"}]'

# Enable horizontal pod autoscaling
kubectl autoscale deployment trading-coordinator \
  --cpu-percent=70 \
  --min=1 \
  --max=5 \
  -n trading-system
```

#### Database Connection Issues
**Symptoms:**
- Redis connection timeouts
- BigQuery query failures

**Diagnosis:**
```bash
# Test Redis connectivity
kubectl exec deployment/trading-coordinator -n trading-system -- \
  redis-cli -h redis-service ping

# Check BigQuery permissions
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -c "from google.cloud import bigquery; client = bigquery.Client(); print('BigQuery OK')"
```

**Solutions:**
```bash
# Restart Redis
kubectl rollout restart deployment redis -n trading-system

# Check BigQuery service account
gcloud iam service-accounts list
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/bigquery.dataEditor"
```

### 5. Build & Deployment Issues

#### Docker Build Failures
**Symptoms:**
- Cloud Build fails
- Local docker build errors

**Common Issues:**
```bash
# Check build logs
gcloud builds log read <build-id>

# Test local build
docker build -t test-build .

# Check dependencies
pip check
```

**Solutions:**
```bash
# Clear build cache
gcloud builds submit --no-cache

# Update base images
sed -i 's/python:3.11-slim/python:3.11-slim-bookworm/' Dockerfile

# Fix dependency conflicts
pip-tools compile requirements.in
```

#### Kubernetes Manifest Issues
**Symptoms:**
- `kubectl apply` failures
- Resource validation errors

**Diagnosis:**
```bash
# Validate YAML syntax
kubectl apply --dry-run=client -f k8s/

# Check resource quotas
kubectl describe resourcequota -n trading-system

# Validate API versions
kubectl api-versions | grep apps/v1
```

**Solutions:**
```bash
# Update API versions
sed -i 's/apps/v1beta1/apps/v1/g' k8s/*.yaml

# Check namespace limits
kubectl get resourcequota -n trading-system

# Fix indentation
python -c "import yaml; yaml.safe_load(open('k8s/deployment.yaml'))"
```

## 🔧 Advanced Debugging Tools

### Network Debugging
```bash
# Packet capture
kubectl exec deployment/trading-coordinator -n trading-system -- \
  tcpdump -i eth0 -w /tmp/capture.pcap

# Network connectivity test
kubectl run network-test --image=nicolaka/netshoot --rm -it -n trading-system

# Service mesh debugging
istioctl proxy-config listeners trading-coordinator-pod-name.trading-system
```

### Application Profiling
```bash
# CPU profiling
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -m cProfile -o /tmp/profile.prof cloud_trader/service.py

# Memory profiling
kubectl exec deployment/trading-coordinator -n trading-system -- \
  python -m tracemalloc --trace cloud_trader/service.py

# Download profiles for analysis
kubectl cp trading-system/trading-coordinator-pod:/tmp/profile.prof ./profile.prof
```

### Log Analysis
```bash
# Structured log search
kubectl logs deployment/trading-coordinator -n trading-system | \
  jq 'select(.level == "error")'

# Log correlation
stern "trading-coordinator" -n trading-system --since=1h | \
  grep -C 5 "ERROR"

# Log aggregation search
gcloud logging read "resource.type=k8s_container AND resource.labels.cluster_name=hft-trading-cluster" \
  --filter="textPayload:ERROR" \
  --limit=50
```

## 🚨 Incident Response

### Severity Classification
- **Critical**: Complete system outage, data loss, security breach
- **High**: Major functionality broken, significant performance degradation
- **Medium**: Minor functionality issues, intermittent problems
- **Low**: Cosmetic issues, minor performance degradation

### Response Procedures

#### Critical Incident
1. **Immediate Actions:**
   - Stop all trading activities
   - Notify all stakeholders
   - Escalate to incident response team
   - Start incident timeline documentation

2. **Assessment:**
   - Determine scope and impact
   - Identify root cause
   - Assess data loss potential

3. **Containment:**
   - Isolate affected components
   - Implement temporary fixes
   - Scale down problematic services

4. **Recovery:**
   - Deploy fixes
   - Restore from backups if needed
   - Verify system stability

5. **Post-Incident:**
   - Document incident and resolution
   - Update monitoring/alerting
   - Conduct retrospective analysis

#### Communication Template
```markdown
**INCIDENT REPORT**

**Status:** 🔴 ACTIVE / 🟡 MONITORING / 🟢 RESOLVED

**Summary:**
Brief description of the issue

**Impact:**
- Affected services: [list]
- User impact: [description]
- Business impact: [description]

**Timeline:**
- Detected: [timestamp]
- Response started: [timestamp]
- Resolution: [timestamp]

**Actions Taken:**
- [List of actions]

**Next Steps:**
- [Recovery plan]
- [Prevention measures]

**Contact:**
- Lead responder: [name]
- Escalation contact: [name]
```

## 📊 Monitoring & Alerting

### Key Metrics to Monitor
```promql
# System health
up{job="sapphire-trading"}
kube_pod_container_status_ready{namespace="trading-system"}

# Performance
rate(http_requests_total{job="sapphire-trading"}[5m])
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Business metrics
trading_system_active_trades
trading_system_pnl_total
trading_system_api_errors_total
```

### Alert Configuration
```yaml
groups:
- name: sapphire_trading_alerts
  rules:
  - alert: TradingSystemDown
    expr: up{job="sapphire-trading"} == 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Sapphire Trading System is down"

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High error rate detected"

  - alert: AgentDisconnected
    expr: trading_system_agent_status != 1
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Trading agent disconnected"
```

## 🛠️ Automated Diagnostics

### Health Check Script
```bash
#!/bin/bash
# comprehensive-health-check.sh

echo "🔍 Comprehensive Health Check"
echo "============================="

# Pod status
echo "Pod Status:"
kubectl get pods -n trading-system --no-headers | awk '{print $1, $3}' | column -t

# Service endpoints
echo -e "\nService Endpoints:"
kubectl get endpoints -n trading-system --no-headers | column -t

# Resource usage
echo -e "\nResource Usage:"
kubectl top pods -n trading-system 2>/dev/null || echo "Metrics not available"

# Application health
echo -e "\nApplication Health:"
services=("coordinator-service" "redis-service")
for svc in "${services[@]}"; do
    if kubectl exec deployment/trading-coordinator -n trading-system -- \
        curl -f -s http://${svc}:8080/health >/dev/null 2>&1; then
        echo "✅ ${svc}: Healthy"
    else
        echo "❌ ${svc}: Unhealthy"
    fi
done

# Recent errors
echo -e "\nRecent Errors:"
kubectl logs --since=10m deployment/trading-coordinator -n trading-system | \
    grep -i error | tail -5 || echo "No recent errors"
```

### Automated Recovery
```bash
#!/bin/bash
# auto-recovery.sh

echo "🔄 Automated Recovery Starting"

# Check for common issues
if kubectl get pods -n trading-system | grep CrashLoopBackOff >/dev/null; then
    echo "Detected CrashLoopBackOff - attempting restart"
    kubectl delete pods -n trading-system --field-selector=status.phase=Failed
fi

if kubectl get pods -n trading-system | grep Pending >/dev/null; then
    echo "Detected pending pods - checking resources"
    kubectl describe nodes | grep -A 10 "Allocated resources"
fi

# Restart unhealthy deployments
kubectl rollout restart deployment -n trading-system \
    $(kubectl get deployments -n trading-system -o jsonpath='{.items[?(@.status.replicas!=@.status.readyReplicas)].metadata.name}')

echo "✅ Recovery actions completed"
```

## 📞 Support & Escalation

### Internal Support Matrix
| Issue Type | Primary Contact | Backup Contact | Escalation Time |
|------------|-----------------|----------------|-----------------|
| Infrastructure | DevOps Lead | Platform Engineer | 15 minutes |
| Application | Tech Lead | Senior Developer | 30 minutes |
| Trading Logic | Trading Lead | Quant Developer | 15 minutes |
| Security | Security Team | DevOps Lead | Immediate |
| Data | Data Engineer | DBA | 30 minutes |

### External Support
- **Google Cloud Support**: Enterprise support contract
- **Kubernetes Community**: GitHub issues, Slack channels
- **FastAPI Community**: GitHub discussions
- **Vendor Support**: Aster DEX, Vertex AI support

### Knowledge Base
- **Internal Wiki**: Company documentation
- **GitHub Issues**: Historical issues and resolutions
- **Runbooks**: Detailed operational procedures
- **Postmortems**: Incident analysis and lessons learned

---

## Prevention Best Practices

### Proactive Monitoring
- Implement comprehensive health checks
- Set up alerting for key metrics
- Regular performance benchmarking
- Automated dependency checks

### Code Quality
- Comprehensive test coverage
- Automated code review requirements
- Static analysis and linting
- Security scanning in CI/CD

### Infrastructure Resilience
- Multi-zone deployment
- Automated backups
- Chaos engineering testing
- Capacity planning and scaling

### Incident Prevention
- Regular dependency updates
- Configuration drift detection
- Security vulnerability scanning
- Performance regression testing

For development workflow, see [DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md).
For deployment procedures, see [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).
