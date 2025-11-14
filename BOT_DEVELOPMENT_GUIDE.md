# Sapphire Trade Bot Development Guide

## Overview
This guide explains how to add new trading bots to the Sapphire Trade system with automatic Telegram and Aster DEX configuration injection.

## Prerequisites

### Required Secrets
The system expects these Kubernetes secrets to exist:
- `aster-dex-credentials`: Contains `api_key` and `api_secret`
- `telegram-secret`: Contains `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

### Required Tools
- `kubectl` configured for your cluster
- `initialize-new-bot.sh` script
- `bot-config-template.yaml` template

## Adding a New Bot

### Method 1: Automated Script (Recommended)

```bash
# Initialize a new momentum trading bot
./initialize-new-bot.sh \
  --name momentum-bot \
  --strategy momentum-analysis \
  --risk medium \
  --capital 750

# Initialize a sentiment analysis bot
./initialize-new-bot.sh \
  --name sentiment-bot \
  --strategy sentiment-analysis \
  --risk low \
  --capital 500

# Dry run to see what would be created
./initialize-new-bot.sh \
  --name test-bot \
  --strategy test-strategy \
  --dry-run
```

### Method 2: Manual Configuration

1. **Create ConfigMap**:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-bot-config
  namespace: trading
data:
  BOT_NAME: "my-bot"
  BOT_STRATEGY: "my-strategy"
  RISK_LEVEL: "medium"
  CAPITAL_ALLOCATION: "500"
  ASTER_BASE_URL: "https://fapi.asterdex.com"
  TELEGRAM_ENABLED: "true"
  LOG_LEVEL: "INFO"
  METRICS_ENABLED: "true"
```

2. **Create Deployment**:
Use `bot-config-template.yaml` and replace `{{BOT_NAME}}` with your bot name.

3. **Apply Configuration**:
```bash
kubectl apply -f my-bot-config.yaml
kubectl apply -f my-bot-deployment.yaml
```

## Configuration Parameters

### Required Parameters
- `--name`: Unique bot identifier (lowercase, hyphens allowed)
- `--strategy`: Trading strategy description

### Optional Parameters
- `--risk`: Risk level (low/medium/high, default: medium)
- `--capital`: Capital allocation in USD (100-5000, default: 500)
- `--dry-run`: Preview configuration without applying

## Automatic Configuration Injection

When you use the initialization script, the following configurations are automatically injected:

### Aster DEX API
- `ASTER_API_KEY`: From shared secret
- `ASTER_API_SECRET`: From shared secret
- `ASTER_BASE_URL`: Standard API endpoint

### Telegram Notifications
- `TELEGRAM_BOT_TOKEN`: From shared secret
- `TELEGRAM_CHAT_ID`: From shared secret
- `TELEGRAM_ENABLED`: Always "true"

### Bot-Specific Configuration
- `BOT_NAME`: Bot identifier
- `BOT_STRATEGY`: Strategy description
- `CAPITAL_ALLOCATION`: Allocated capital
- `RISK_LEVEL`: Risk tolerance

### Monitoring & Logging
- `LOG_LEVEL`: INFO (configurable)
- `METRICS_ENABLED`: true (configurable)

## Verification

After initialization, verify your bot:

```bash
# Check pod status
kubectl get pods -n trading -l app=my-bot

# Check configuration injection
kubectl exec -n trading deployment/my-bot -- env | grep -E "(BOT_NAME|TELEGRAM|ASTER)"

# Check logs
kubectl logs -n trading deployment/my-bot --follow

# Test health endpoint
kubectl port-forward -n trading svc/my-bot-service 8080:8080
curl http://localhost:8080/health
```

## Troubleshooting

### Bot Won't Start
```bash
# Check pod events
kubectl describe pod -n trading -l app=my-bot

# Check logs
kubectl logs -n trading deployment/my-bot

# Check resource limits
kubectl get deployment my-bot -n trading -o yaml | grep -A 10 resources
```

### Configuration Not Injected
```bash
# Check secrets exist
kubectl get secrets -n trading

# Check configmap
kubectl get configmap my-bot-config -n trading -o yaml

# Check environment variables
kubectl exec -n trading deployment/my-bot -- env
```

### Telegram Not Working
```bash
# Test telegram credentials
kubectl exec -n trading deployment/my-bot -- python3 -c "
import os
import requests
token = os.getenv('TELEGRAM_BOT_TOKEN')
chat = os.getenv('TELEGRAM_CHAT_ID')
print(f'Token: {token[:20]}...')
print(f'Chat: {chat}')
# Test API call...
"
```

## Best Practices

### Naming Conventions
- Use lowercase with hyphens: `momentum-bot`, `sentiment-analysis-bot`
- Include strategy in name for clarity
- Keep names under 20 characters

### Capital Allocation
- Start with $500 for testing
- Scale based on performance
- Monitor correlation with existing bots

### Risk Management
- `low`: Conservative strategies
- `medium`: Balanced approaches  
- `high`: Aggressive high-frequency trading

### Monitoring
- Check daily health via monitoring script
- Monitor resource usage
- Review trading performance weekly

## Examples

### Adding a Mean-Reversion Bot
```bash
./initialize-new-bot.sh \
  --name mean-reversion-bot \
  --strategy mean-reversion \
  --risk medium \
  --capital 600
```

### Adding a Scalping Bot
```bash
./initialize-new-bot.sh \
  --name scalping-bot \
  --strategy market-making-scalping \
  --risk high \
  --capital 400
```

### Adding a Pairs Trading Bot
```bash
./initialize-new-bot.sh \
  --name pairs-trading-bot \
  --strategy statistical-arbitrage \
  --risk low \
  --capital 800
```

## Support

If you encounter issues:
1. Run the monitoring script: `./monitoring-script.sh`
2. Check the troubleshooting section above
3. Review pod logs and events
4. Contact the development team

---

*This guide ensures consistent bot initialization across the Sapphire Trade platform.*
