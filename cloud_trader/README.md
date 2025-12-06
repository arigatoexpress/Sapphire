# 🤖 Cloud Trader

The main trading engine for Agent Symphony, managing multiple AI trading agents on the Aster Exchange.

## Overview

Cloud Trader is a Python FastAPI service that:
- Manages 7+ specialized trading agents
- Executes trades on Aster Exchange
- Provides WebSocket connections for the dashboard
- Sends Telegram notifications
- Runs continuous market analysis

## Architecture

```mermaid
flowchart TB
    API[FastAPI Server :8080] --> TL[Trading Loop]
    API --> WS[WebSocket Manager]
    
    TL --> Agents[AI Agents]
    TL --> PM[Position Manager]
    TL --> MDM[Market Data Manager]
    
    Agents --> EX[Aster Exchange]
    PM --> REDIS[(Redis)]
    WS --> DASH[Dashboard]
```

## Key Files

| File | Description |
|------|-------------|
| `api.py` | FastAPI application & WebSocket endpoints |
| `trading_service.py` | Core trading loop & agent coordination |
| `position_manager.py` | Position tracking & sync |
| `market_data.py` | Exchange data fetching |
| `enhanced_telegram.py` | AI-powered notifications |
| `client.py` | Aster exchange API client |
| `config.py` | Settings & symbol configuration |

## Running Locally

```bash
# From project root
python -m cloud_trader.api
```

## Environment Variables

```bash
GCP_PROJECT_ID=sapphire-479610
ASTER_API_KEY=your_key
ASTER_SECRET_KEY=your_secret
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://user:pass@localhost:5432/trading_db
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/portfolio` | GET | Portfolio summary |
| `/api/positions` | GET | Open positions |
| `/api/trades` | GET | Recent trades |
| `/ws/dashboard` | WS | Real-time updates |

## Deployment

```bash
gcloud builds submit --config cloudbuild_trader.yaml .
gcloud run deploy cloud-trader --image gcr.io/sapphire-479610/cloud-trader \
  --platform managed --region northamerica-northeast1 \
  --vpc-connector sapphire-conn --vpc-egress all-traffic
```
