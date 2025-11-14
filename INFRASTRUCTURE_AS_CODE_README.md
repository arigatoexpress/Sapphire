# Infrastructure as Code Framework

## Overview

This framework provides a robust, declarative approach to deploying and managing the Sapphire Trade AI trading system. It eliminates deployment conflicts and ensures consistent, repeatable infrastructure management.

## Architecture Principles

### 1. Declarative Infrastructure
- **All infrastructure defined in YAML manifests**
- **Version-controlled deployments**
- **No imperative kubectl commands in production**

### 2. Immutable Deployments
- **Never modify running resources**
- **Always replace with new versions**
- **Blue-green deployment ready**

### 3. Safe Rollback
- **Automated cleanup procedures**
- **Comprehensive validation**
- **Zero-downtime deployments**

### 4. Resource Optimization
- **Tiered resource allocation**
- **Cost-effective scaling**
- **Quota management**

## Quick Start

### Initial Deployment
```bash
# 1. Deploy clean infrastructure
./deploy-infrastructure.sh

# 2. Deploy trading agents
./deploy-agents.sh

# 3. Validate deployment
./validate-deployment.sh
```

### Ongoing Management
```bash
# Daily health checks
./validate-deployment.sh

# Weekly cleanup
./cleanup-infrastructure.sh --dry-run

# Monitor resources
./elastic-monitor.sh
```

## Component Overview

### Core Infrastructure (`infrastructure-as-code-framework.yaml`)
- **Namespace**: `trading-system`
- **Resource Quotas**: Production-ready limits (16 CPU cores, 32Gi memory)
- **Secrets**: Aster DEX and Telegram credentials
- **ConfigMaps**: System configuration and resource tiers
- **Redis**: Caching and data storage
- **Trading Coordinator**: Core orchestration service

### Agent Tiers

| Tier | CPU Request | Memory Request | Use Case | Scaling |
|------|-------------|----------------|----------|---------|
| **Lightweight** | 100m | 128Mi | Basic strategies | 20% of agents |
| **Standard** | 300m | 384Mi | Complex strategies | 60% of agents |
| **Heavy** | 800m | 1.5Gi | AI/ML workloads | 15% of agents |
| **Accelerated** | 1500m | 2Gi + TPU | HFT/VPIN | 5% of agents |

### Multi-Agent Ensemble
- **Momentum Agent**: Trend-following strategies
- **Sentiment Agent**: NLP-based market analysis
- **Pairs Agent**: Statistical arbitrage
- **Breakout Agent**: Technical breakout detection
- **Scalping Agent**: Market making
- **Volatility Agent**: Volatility harvesting

## Scripts Overview

### Deployment Scripts
- **`deploy-infrastructure.sh`**: Clean infrastructure deployment
- **`deploy-agents.sh`**: Multi-agent ensemble deployment
- **`validate-deployment.sh`**: Comprehensive health validation

### Management Scripts
- **`cleanup-infrastructure.sh`**: Safe resource cleanup
- **`elastic-monitor.sh`**: Resource usage monitoring
- **`monitoring-script.sh`**: System health monitoring

## Troubleshooting

### Deployment Failures
```bash
# Check validation report
./validate-deployment.sh --exit-on-failure

# View detailed logs
kubectl logs -n trading-system deployment/trading-coordinator

# Check resource quotas
kubectl get resourcequotas -n trading-system
```

### Resource Issues
```bash
# Monitor usage
./elastic-monitor.sh

# Check pod resource usage
kubectl top pods -n trading-system

# Adjust quotas if needed
kubectl edit resourcequota production-trading-quota -n trading-system
```

### Cleanup Issues
```bash
# Dry run cleanup
./cleanup-infrastructure.sh --dry-run

# Force cleanup
./cleanup-infrastructure.sh
```

## Best Practices

### Deployment Workflow
1. **Always validate before deploying**
   ```bash
   ./validate-deployment.sh
   ```

2. **Use dry-run for testing**
   ```bash
   ./cleanup-infrastructure.sh --dry-run
   ```

3. **Deploy infrastructure first**
   ```bash
   ./deploy-infrastructure.sh
   ./deploy-agents.sh
   ```

### Monitoring Strategy
- **Daily**: `./validate-deployment.sh`
- **Hourly**: Critical alerts via monitoring
- **Weekly**: `./cleanup-infrastructure.sh`

### Resource Management
- **Monitor usage**: `./elastic-monitor.sh`
- **Scale proactively**: Set up HPAs for auto-scaling
- **Cost optimize**: Use appropriate resource tiers

## Security Considerations

### Secret Management
- **Never commit secrets to version control**
- **Use Kubernetes secrets for API keys**
- **Rotate credentials regularly**

### Network Security
- **Service mesh integration ready**
- **Network policies can be added**
- **mTLS encryption support**

### Access Control
- **RBAC policies can be implemented**
- **Namespace isolation enforced**
- **Audit logging enabled**

## Scaling Strategy

### Horizontal Scaling
- **Pod autoscaling** via HPAs (CPU/memory based)
- **Cluster autoscaling** (1-6 nodes)
- **Load balancing** across pods

### Vertical Scaling
- **Resource tier upgrades** for individual agents
- **Node pool scaling** for increased capacity
- **TPU integration** for AI workloads

### Cost Optimization
- **Spot instances** for non-critical workloads
- **Auto-shutdown** during low volatility
- **Resource right-sizing** based on usage patterns

## Disaster Recovery

### Backup Strategy
- **Manifest versioning** in Git
- **Automated deployment** from manifests
- **Configuration as code** ensures consistency

### Rollback Procedure
```bash
# Clean current deployment
./cleanup-infrastructure.sh

# Deploy previous version
git checkout <previous-tag>
./deploy-infrastructure.sh
./deploy-agents.sh
```

### Recovery Time
- **Infrastructure**: < 5 minutes
- **Agents**: < 10 minutes
- **Full system**: < 15 minutes

## Performance Benchmarks

### Target Metrics
- **Deployment time**: < 10 minutes
- **Validation time**: < 2 minutes
- **Resource efficiency**: > 70% utilization
- **Uptime**: > 99.9%

### Monitoring Alerts
- **CPU > 80%**: Scale up resources
- **Memory > 85%**: Scale up resources
- **Pod failures**: Automatic restart
- **Quota exceeded**: Alert administrators

## Future Enhancements

### GitOps Integration
- **ArgoCD** for automated deployments
- **Flux** for Git-based synchronization
- **Automated rollbacks** on failure

### Advanced Monitoring
- **Prometheus** integration
- **Grafana** dashboards
- **ELK stack** for logging

### Security Hardening
- **Pod security policies**
- **Network policies**
- **Service mesh** (Istio/Linkerd)

---

## Quick Reference

### Emergency Commands
```bash
# Complete system reset
./cleanup-infrastructure.sh
rm -rf /tmp/*-manifest.yaml
./deploy-infrastructure.sh

# Check system health
./validate-deployment.sh --exit-on-failure

# Monitor resources
./elastic-monitor.sh
```

### Daily Operations
```bash
# Morning check
./validate-deployment.sh

# Resource monitoring
./elastic-monitor.sh

# Weekly cleanup
./cleanup-infrastructure.sh --dry-run
```

This framework ensures **reliable, repeatable, and maintainable** infrastructure deployments for the Sapphire Trade system.
