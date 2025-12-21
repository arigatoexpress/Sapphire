# Symphony/Monad Integration Setup Guide

## Environment Variables

Add these to your `.env` file or deployment secrets:

```bash
# Symphony API Key (REQUIRED)
SYMPHONY_API_KEY=sk_live_k7h5KAh71HJM7uKARBf4a-JGJoaltQoRaAuY7a4wjp8

# Symphony API Base URL  
SYMPHONY_BASE_URL=https://api.symphony.finance

# MIT Fund Settings
MIT_FUND_NAME=Sapphire MIT Agent
MIT_FUND_DESCRIPTION=Autonomous AI trading agent powered by Sapphire intelligence on Monad blockchain
MIT_AUTO_SUBSCRIBE=true

# Trading Configuration
MIT_DEFAULT_LEVERAGE=3
MIT_MAX_POSITION_SIZE_USDC=100

# Risk Management
MIT_ENABLE_STOP_LOSS=true
MIT_ENABLE_TAKE_PROFIT=true
MIT_DEFAULT_SL_PERCENT=0.03
MIT_DEFAULT_TP_PERCENT=0.08
```

## Activation Requirements

- **Trades Required**: 5 successful trades
- **Status**: Once activated, your fund can accept subscribers
- **Trade Types**: Perpetuals or Spot trades count toward activation

## Quick Start

1. Add environment variables to `.env`
2. Create your agentic fund via the MIT dashboard
3. Execute 5 trades to activate
4. Start accepting subscribers and earning fees

## API Documentation

See Symphony API docs: https://docs.symphony.finance
