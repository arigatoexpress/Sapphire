# Sapphire

**Autonomous AI Trading System**

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Production-grade trading system with multi-platform DeFi execution, AI agent consensus, and memory-augmented learning.

## Platforms

| Platform | Type | Status |
|----------|------|--------|
| **Hyperliquid** | DeFi Perpetuals | Active |
| **Drift** | Solana Perpetuals | Active |
| **Jupiter** | Solana DEX Aggregator | Active |
| **Lighter** | Ethereum L2 Perpetuals | Active |
| **Aster** | CEX | Active |
| **Symphony** | Monad Treasury | Active |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Gateway                       │
│                     (Cloud Run)                          │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐
    │  Agent  │    │  Memory   │   │  Circuit  │
    │  Swarm  │    │  Manager  │   │  Breaker  │
    └────┬────┘    └───────────┘   └───────────┘
         │
    ┌────▼────────────────────────────────────┐
    │          Multi-Platform Router           │
    │   (Symbol-based routing + Failover)      │
    └──┬───────┬───────┬───────┬───────┬──────┘
       │       │       │       │       │
    ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
    │ HL  │ │Drift│ │ Jup │ │Light│ │Aster│
    └─────┘ └─────┘ └─────┘ └─────┘ └─────┘
```

## Core Components

### Agent Swarm
Four specialized AI agents with weighted consensus:
- **Quant Alpha** (35%) - Technical analysis, momentum, volatility
- **Risk Guard** (25%) - Position sizing, drawdown protection
- **Sentiment Sage** (20%) - Social signals, news impact
- **Degen Hunter** (20%) - High-conviction momentum plays

### Smart Routing
- Symbol-based platform assignment (BTC/ETH → Hyperliquid, SOL/JTO → Drift)
- Automatic failover chain with circuit breaker protection
- Game theory obfuscation (jitter, fuzzing, dynamic slippage)

### Memory System
RAG-based learning with FAISS vector search and Firestore persistence:
- Trade outcomes and patterns
- Thesis templates per market condition
- Risk events and lessons learned

### Symphony Treasury
Multi-agent treasury management on Monad:
- **$MILF** - Conservative treasury management
- **$AGDG** - High-conviction momentum plays
- **$MIT** - Pending activation (5-trade requirement)

## Quick Start

```bash
# Clone
git clone https://github.com/arigatoexpress/Sapphire.git
cd Sapphire

# Setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
export GOOGLE_CLOUD_PROJECT=sapphire-479610

# Run
python cloud_trader/main_v2.py
```

## Deploy

```bash
gcloud builds submit --config=cloudbuild.yaml .
```

## API

```bash
# Trade execution
POST /api/v2/trade
{"symbol": "BTC-PERP", "side": "BUY", "quantity": 0.01}

# Platform status
GET /api/v2/platforms/status

# Memory health
GET /api/v2/memory/health

# System health
GET /health
```

## Project Structure

```
Sapphire/
├── cloud_trader/
│   ├── v2/                    # Core V2 modules
│   │   ├── dual_platform_router.py
│   │   ├── hyperliquid_client.py
│   │   ├── lighter_client.py
│   │   ├── hardened_memory_manager.py
│   │   ├── symphony_agent_manager.py
│   │   └── enhanced_circuit_breaker.py
│   ├── agents/                # AI agent implementations
│   ├── api/                   # API routes
│   └── main_v2.py             # Application entry
├── services/                  # Microservices
│   ├── bot-hyperliquid/
│   ├── bot-drift/
│   ├── bot-jupiter/
│   ├── bot-aster/
│   └── bot-symphony/
├── sapphire-web/              # Frontend
└── docs/                      # Documentation
```

## Security

- All secrets stored in Google Cloud Secret Manager
- Circuit breakers prevent cascade failures
- Rate limiting on all platform connections
- Write-ahead logging for crash recovery

## License

MIT

---

**Version 2.2.0**
