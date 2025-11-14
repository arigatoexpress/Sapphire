# Sapphire Trading System - Operational Runbook

## Overview
This runbook provides operational procedures for the Sapphire Trading System, a high-frequency AI-powered trading platform.

## System Architecture

### Core Components
- **Cloud Trader**: Main trading service with AI agents
- **MCP Coordinator**: Multi-agent communication protocol coordinator
- **AI Agents**: 6 specialized AI trading agents (Trend Momentum, Strategy Optimization, Financial Sentiment, Market Prediction, Volume Microstructure, VPIN HFT) powered by Gemini models
- **Redis**: Caching and session management
- **PostgreSQL**: Trade and market data storage
- **Vertex AI**: Machine learning inference service

### Monitoring Stack
- **Prometheus**: Metrics collection
- **Grafana**: Visualization dashboards
- **Self-Healing**: Automatic recovery systems
- **Compliance Audit**: Regulatory compliance monitoring

## Emergency Procedures

### 🚨 Critical System Failure

**Symptoms:**
- Trading halts
- All services show unhealthy status
- Critical error alerts

**Immediate Actions:**
```bash
# 1. Stop all trading activities
kubectl scale deployment trading-system-cloud-trader --replicas=0 -n trading

# 2. Check system status
kubectl get pods -n trading
kubectl logs -n trading deployment/trading-system-cloud-trader --tail=100

# 3. Restart core services
kubectl rollout restart deployment/trading-system-cloud-trader -n trading
kubectl rollout restart deployment/trading-system-mcp-coordinator -n trading
```

**Escalation:**
- Contact on-call engineer immediately
- Notify compliance officer if trading data affected

### 🚨 High CPU/Memory Usage

**Thresholds:**
- CPU > 80%
- Memory > 85%

**Actions:**
```bash
# Check resource usage
kubectl top pods -n trading

# Scale up if needed
kubectl scale deployment trading-system-cloud-trader --replicas=3 -n trading

# Check for memory leaks
kubectl logs -n trading deployment/trading-system-cloud-trader --tail=200 | grep -i "memory\|leak"
```

### 🚨 Network Connectivity Issues

**Symptoms:**
- API timeouts
- External service failures

**Actions:**
```bash
# Check network policies
kubectl get networkpolicies -n trading

# Test external connectivity
kubectl run test --image=busybox --rm -it --restart=Never -- wget -q -O - google.com

# Restart affected services
kubectl rollout restart deployment/trading-system-cloud-trader -n trading
```

## Regular Maintenance

### Daily Checks

#### Morning System Health Check
```bash
# Check all pods are running
kubectl get pods -n trading

# Verify service health
curl http://trading-system-cloud-trader.trading.svc.cluster.local:8080/healthz

# Check resource usage
kubectl top pods -n trading

# Review recent errors
kubectl logs -n trading --since=1h | grep -i error
```

#### Performance Monitoring
```bash
# Check trading metrics
kubectl exec -n trading deployment/trading-system-cloud-trader -- python3 -c "
from cloud_trader.performance_monitor import get_performance_monitor
monitor = get_performance_monitor()
print(monitor.get_performance_summary())
"
```

### Weekly Maintenance

#### Compliance Audit
```bash
# Run compliance check
kubectl exec -n trading deployment/trading-system-cloud-trader -- python3 -c "
import asyncio
from cloud_trader.compliance_audit import generate_compliance_report
report = asyncio.run(generate_compliance_report())
print('Compliance Status:', report['overall_status'])
"
```

#### Security Review
```bash
# Check security status
kubectl exec -n trading deployment/trading-system-cloud-trader -- python3 -c "
from cloud_trader.security_hardening import get_security_status
status = get_security_status()
print('Security Health:', status['health_check']['status'])
"
```

#### Backup Verification
```bash
# Verify recent backups
gsutil ls gs://sapphire-trading-backups/ | tail -10

# Test backup restoration (in staging environment)
# [Backup restoration procedures]
```

### Monthly Maintenance

#### System Updates
```bash
# Update container images
kubectl set image deployment/trading-system-cloud-trader cloud-trader=us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest -n trading

# Rolling update
kubectl rollout status deployment/trading-system-cloud-trader -n trading
```

#### Performance Optimization
```bash
# Run performance analysis
kubectl exec -n trading deployment/trading-system-cloud-trader -- python3 -c "
from cloud_trader.performance_monitor import get_performance_status
status = get_performance_status()
for rec in status['recommendations']:
    print(f'- {rec}')
"
```

## Deployment Procedures

### Standard Deployment
```bash
# 1. Build and push images
gcloud builds submit --config cloudbuild.yaml --substitutions _ARTIFACT_REGISTRY_REPO=sapphireinfinite .

# 2. Verify build success
gcloud builds describe $(gcloud builds list --limit=1 --format="value(id)") --format="value(status)"

# 3. Deploy to staging
helm upgrade --install trading-system-staging ./helm/trading-system --namespace staging --create-namespace

# 4. Run tests in staging
kubectl exec -n staging deployment/trading-system-cloud-trader -- python3 comprehensive_test.py

# 5. Deploy to production
helm upgrade --install trading-system ./helm/trading-system --namespace trading --create-namespace

# 6. Verify production deployment
kubectl get pods -n trading
kubectl logs -n trading deployment/trading-system-cloud-trader --tail=50
```

### Rollback Procedure
```bash
# Quick rollback to previous version
kubectl rollout undo deployment/trading-system-cloud-trader -n trading

# Or rollback to specific revision
kubectl rollout undo deployment/trading-system-cloud-trader --to-revision=2 -n trading

# Verify rollback
kubectl rollout status deployment/trading-system-cloud-trader -n trading
```

## Monitoring & Alerting

### Key Metrics to Monitor

#### System Health
- Pod status and restarts
- CPU/Memory usage
- Network connectivity
- Disk space

#### Trading Performance
- Request latency (P95 < 100ms)
- Success rate (> 99.5%)
- Trading volume
- Error rates

#### Business Metrics
- P&L tracking
- Win rate
- Sharpe ratio
- Maximum drawdown

### Alert Thresholds

#### Critical Alerts (Immediate Response)
- System unavailable > 5 minutes
- Trading halted
- Data loss
- Security breach

#### Warning Alerts (Monitor Closely)
- CPU > 80%
- Memory > 85%
- Error rate > 5%
- Latency > 500ms

#### Info Alerts (Track Trends)
- Performance degradation
- Unusual trading patterns
- Compliance warnings

## Security Procedures

### Access Control
```bash
# Check active sessions
kubectl exec -n trading deployment/trading-system-cloud-trader -- python3 -c "
from cloud_trader.security_hardening import get_security_status
status = get_security_status()
print('Active Sessions:', status['security_report']['active_sessions'])
"
```

### Incident Response
1. **Isolate**: Stop affected services
2. **Investigate**: Check logs and metrics
3. **Contain**: Block malicious IPs if applicable
4. **Recover**: Restore from backup if needed
5. **Report**: Document incident and resolution

## Troubleshooting Guide

### Common Issues

#### High Latency
```
Symptoms: API responses slow (>500ms)
Causes: Database locks, network issues, resource constraints
Solutions:
1. Check database performance
2. Scale up resources
3. Optimize queries
```

#### Memory Leaks
```
Symptoms: Gradual memory increase, OOM kills
Causes: Unclosed connections, large data structures
Solutions:
1. Monitor memory usage patterns
2. Implement connection pooling
3. Add memory profiling
```

#### Trading Halts
```
Symptoms: No new trades, system appears healthy
Causes: Risk limits exceeded, circuit breakers
Solutions:
1. Check risk metrics
2. Review circuit breaker status
3. Manual override if needed
```

## Contact Information

### On-Call Engineers
- Primary: [Engineer Name] - [Phone] - [Email]
- Secondary: [Engineer Name] - [Phone] - [Email]

### Compliance Officer
- [Officer Name] - [Phone] - [Email]

### Business Contacts
- Trading Desk: [Contact] - [Phone]
- Risk Management: [Contact] - [Phone]

## Appendices

### A. Service Ports
- Cloud Trader: 8080
- MCP Coordinator: 8081
- AI Agents: 8080 (each)

### B. Environment Variables
- `LOG_LEVEL`: INFO/DEBUG/WARNING
- `ENABLE_PAPER_TRADING`: true/false
- `MAX_DRAWDOWN`: 0.25
- `RISK_MULTIPLIER`: 1.0-2.0

### C. Backup Schedule
- Database: Daily at 02:00 UTC
- Logs: Hourly
- Configuration: On changes

### D. Performance Benchmarks
- Target: 1000 RPS with <100ms P95 latency
- Current: [Update based on testing]
- Degradation threshold: 2000ms P95 latency

---

**Last Updated:** November 13, 2025
**Version:** 1.0
**Author:** Sapphire Trading Team
