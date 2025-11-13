# Trading System Monitoring

Comprehensive monitoring stack for the autonomous trading system using Prometheus, Grafana, and Redis.

## 🚀 Quick Start

```bash
cd infra/monitoring
./setup-monitoring.sh
```

## 📊 Services

### Prometheus (`localhost:9090`)
- **Metrics Collection**: Scrapes metrics from all trading services
- **Alerting Rules**: Configurable alerting for system issues
- **Query Language**: PromQL for complex metric analysis

### Grafana (`localhost:3000`)
- **Dashboards**: Pre-built trading system dashboard
- **Data Sources**: Prometheus and Redis integration
- **Alerts**: Configurable alerts and notifications

### Redis Exporter (`localhost:9121`)
- **Redis Metrics**: Memory usage, connections, commands/sec
- **Stream Monitoring**: Track trading decision streams
- **Performance Data**: Latency and throughput metrics

### Node Exporter (`localhost:9100`)
- **System Metrics**: CPU, memory, disk, network
- **Host Monitoring**: Infrastructure health
- **Resource Tracking**: System resource utilization

## 📈 Monitored Services

### Cloud Trader
- Portfolio balance and P&L
- Active positions and leverage
- Trading decision metrics
- Risk management indicators

### Wallet Orchestrator
- Order execution status
- Risk limit compliance
- Position reconciliation
- Emergency stop triggers

### DeepSeek LLM
- Inference latency and throughput
- Model confidence scores
- Decision processing metrics
- API response times

### Redis Cache
- Connection count and health
- Memory usage and hit rates
- Stream processing metrics
- Command execution stats

## 🎯 Key Metrics

### Trading Performance
- `trading_portfolio_balance`: Current portfolio value
- `trading_position_size`: Size of active positions
- `trading_llm_confidence`: AI decision confidence scores
- `trading_decisions_total`: Total trading decisions made

### Risk Management
- `trading_portfolio_leverage`: Current leverage ratio
- `trading_drawdown_percent`: Portfolio drawdown percentage
- `trading_risk_limits_breached`: Risk limit violations

### System Health
- `up{job="cloud-trader"}`: Service availability
- `redis_connected_clients`: Active Redis connections
- `trading_llm_inference_duration_seconds`: AI inference time

## 🔧 Configuration

### Prometheus (`prometheus.yml`)
```yaml
scrape_configs:
  - job_name: 'cloud-trader'
    static_configs:
      - targets: ['cloud-trader-342943608894.us-central1.run.app']
    metrics_path: '/metrics'
```

### Grafana (`grafana-provisioning.yml`)
- Auto-configures Prometheus data source
- Provisions trading dashboard
- Sets up Redis data source

### Dashboard (`trading-dashboard.json`)
- System status indicators
- Portfolio performance charts
- Risk metrics visualization
- LLM decision tracking

## 🚨 Alerting

Configure alerts in Grafana for:
- Service downtime
- High portfolio drawdown
- Risk limit breaches
- Low LLM confidence scores
- Redis connection issues

## 📊 Custom Queries

### Portfolio Performance
```promql
rate(trading_portfolio_balance[5m])
```

### Risk Monitoring
```promql
trading_portfolio_leverage > 3
```

### Decision Quality
```promql
avg_over_time(trading_llm_confidence[1h]) < 0.6
```

## 🔄 Data Flow

```
Trading Services → Prometheus → Grafana
     ↓              ↓          ↓
  Redis Streams → Metrics → Dashboards
     ↓              ↓          ↓
  Decisions → Alerts → Notifications
```

## 🛠️ Troubleshooting

### Common Issues

**Grafana not loading dashboard**
```bash
# Check Grafana logs
docker-compose logs grafana

# Restart Grafana
docker-compose restart grafana
```

**Prometheus not scraping metrics**
```bash
# Check Prometheus targets
curl http://localhost:9090/targets

# Reload configuration
curl -X POST http://localhost:9090/-/reload
```

**Redis connection issues**
```bash
# Check Redis exporter logs
docker-compose logs redis-exporter

# Verify Redis connectivity
redis-cli -h 10.161.118.219 ping
```

## 📚 Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Guide](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Trading Metrics Best Practices](https://prometheus.io/docs/practices/naming/)
