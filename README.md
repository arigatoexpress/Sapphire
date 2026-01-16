# 💎 Sapphire V2: Autonomous AI Trading System

**ElizaOS-Inspired Multi-Platform Trading Orchestrator**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](/.github/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-Production-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)

[![Solana](https://img.shields.io/badge/Solana-Drift-9945FF?logo=solana&logoColor=white)](#)
[![Hyperliquid](https://img.shields.io/badge/Hyperliquid-Active-00D4AA)](#)
[![Monad](https://img.shields.io/badge/Monad-Symphony-FF3366)](#)
[![Status](https://img.shields.io/badge/status-Production-success)](https://sapphire-v2-267358751314.us-central1.run.app/health)

**Production URL**: `https://sapphire-v2-267358751314.us-central1.run.app`

---

## 📖 Abstract

Sapphire V2 is a production-grade, autonomous trading system implementing memory-augmented AI agents inspired by [ElizaOS](https://github.com/ai16z/eliza). The system executes across **multiple DeFi perpetual platforms** with intelligent routing.

### Key Features

1. **Dual-Platform DeFi Execution**: Hyperliquid + Drift with smart routing
2. **Swarm Intelligence**: 4 specialized AI agents with weighted consensus
3. **Memory-Augmented Learning**: RAG-like pattern for continuous improvement
4. **Symphony Treasury**: Multi-agent management on Monad ($MILF, $AGDG, $MIT)
5. **99.99% Uptime**: Circuit breaker-protected platform failover

---

## ⚡ Platform Overview

| Platform | Type | Status | Primary Symbols |
|----------|------|--------|-----------------|
| **Hyperliquid** | DeFi Perps | ✅ **ACTIVE** | BTC, ETH, ARB, OP, MATIC, AVAX, LINK, DOGE |
| **Drift** | Solana Perps | ✅ **ACTIVE** | SOL, JTO, PYTH, BONK, WIF, JUP, RNDR, HNT |
| **Aster** | CEX | ✅ **ACTIVE** | All spot pairs |
| **Symphony** | Monad Treasury | ✅ **ACTIVE** | Treasury operations |

### Smart Routing

The dual-platform router automatically selects the optimal venue:

```
BTC-PERP  → Hyperliquid (primary) → Drift (failover)
ETH-PERP  → Hyperliquid (primary) → Drift (failover)
SOL-PERP  → Drift (primary) → Hyperliquid (failover)
BONK-PERP → Drift (primary) → Hyperliquid (failover)
```

---

## 🎭 Symphony Agents

| Agent | Ticker | Status | Description |
|-------|--------|--------|-------------|
| **Monad Implementation Treasury Agent** | `$MILF` | ✅ ACTIVE | Treasury management |
| **Ari Gold Degen Agent** | `$AGDG` | ✅ ACTIVE | High-conviction momentum |
| **Monad Implementation Treasury** | `$MIT` | ⏳ PENDING | Requires 5 trades to activate |

### MIT Activation

```bash
# Check MIT status
curl https://sapphire-v2-267358751314.us-central1.run.app/api/v2/symphony/mit/status

# Execute activation trade
curl -X POST https://sapphire-v2-267358751314.us-central1.run.app/api/v2/symphony/mit/activate \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-USDC", "side": "BUY", "quantity": 0.001}'
```

---

## 🔐 Secrets Management

**All credentials are stored in Google Cloud Secret Manager** - never in code or environment variables.

### Required Secrets

| Secret Name | Description | Platform |
|-------------|-------------|----------|
| `HYPERLIQUID_PRIVATE_KEY` | Ethereum wallet private key | Hyperliquid |
| `HYPERLIQUID_WALLET_ADDRESS` | Wallet address | Hyperliquid |
| `DRIFT_PRIVATE_KEY` | Solana wallet private key | Drift |
| `ASTER_API_KEY` | API key | Aster |
| `ASTER_API_SECRET` | API secret | Aster |
| `SYMPHONY_API_KEY` | API key | Symphony |
| `TELEGRAM_BOT_TOKEN` | Bot token | Notifications |
| `TELEGRAM_CHAT_ID` | Chat ID | Notifications |
| `GEMINI_API_KEY` | Gemini AI key | Agent LLM |

### Managing Secrets

```bash
# List secrets
gcloud secrets list --project=sapphire-479610

# Create secret
echo -n "your-secret" | gcloud secrets create SECRET_NAME \
  --data-file=- --project=sapphire-479610

# Update secret
echo -n "new-value" | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=sapphire-479610

# Access secret
gcloud secrets versions access latest --secret=SECRET_NAME
```

### Loading Secrets (credentials.py)

```python
from google.cloud import secretmanager

def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/sapphire-479610/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Usage
HYPERLIQUID_KEY = get_secret("HYPERLIQUID_PRIVATE_KEY")
DRIFT_KEY = get_secret("DRIFT_PRIVATE_KEY")
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Sapphire V2 Trading System                       │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      TradingOrchestrator                           │ │
│  └─────────────┬──────────────────────────────────┬───────────────────┘ │
│                │                                  │                      │
│      ┌─────────▼─────────┐              ┌─────────▼──────────┐         │
│      │   TradingLoop     │              │  MonitoringService │         │
│      │  (60s Cycles)     │              │  (Telegram)        │         │
│      └─────────┬─────────┘              └────────────────────┘         │
│                │                                                         │
│      ┌─────────▼─────────┐                                              │
│      │ AgentOrchestrator │                                              │
│      │  (4-Agent Swarm)  │                                              │
│      └─────────┬─────────┘                                              │
│                │                                                         │
│    ┌───────────┼───────────┬───────────┬───────────┐                   │
│ ┌──▼──┐    ┌──▼──┐    ┌──▼──┐    ┌──▼──┐                             │
│ │Quant│    │Risk │    │Sent.│    │Degen│                             │
│ │Alpha│    │Guard│    │Sage │    │Hunter│                             │
│ └──┬──┘    └──┬──┘    └──┬──┘    └──┬──┘                             │
│    └──────────┴──────────┴──────────┘                                  │
│                        │                                                 │
│              ┌─────────▼──────────┐                                     │
│              │ DualPlatformRouter │ ◄── Smart Routing                  │
│              │  (HL + Drift)      │                                     │
│              └─────────┬──────────┘                                     │
│                        │                                                 │
│        ┌───────────────┼───────────────┬────────────┐                  │
│        │               │               │            │                   │
│   ┌────▼─────┐   ┌────▼──────┐   ┌────▼─────┐  ┌──▼──────┐           │
│   │Hyperliquid   │   Drift   │   │  Aster   │  │Symphony │           │
│   │  (Perps)│   │ (Solana)  │   │  (CEX)   │  │(Monad)  │           │
│   │   ✅    │   │    ✅     │   │    ✅    │  │   ✅    │           │
│   └─────────┘   └───────────┘   └──────────┘  └─────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
```

### V2 Module Structure

```
cloud_trader/v2/
├── __init__.py                    # Package exports
├── hyperliquid_client.py          # Full HL trading client
├── dual_platform_router.py        # HL + Drift smart routing
├── enhanced_circuit_breaker.py    # Multi-platform breakers
├── symphony_agent_manager.py      # $MILF, $AGDG, $MIT tracking
├── hardened_memory_manager.py     # Persistence-verified RAG
├── symphony_mit_tracker.py        # MIT 5-trade activation
└── v2_integration.py              # FastAPI integration
```

---

## 🔀 Dual Platform Router

The router intelligently selects between Hyperliquid and Drift:

### Symbol Routing

```python
# Hyperliquid Primary (EVM-native)
HYPERLIQUID_SYMBOLS = [
    "BTC-PERP", "ETH-PERP", "ARB-PERP", "OP-PERP",
    "MATIC-PERP", "AVAX-PERP", "LINK-PERP", "DOGE-PERP"
]

# Drift Primary (Solana-native)
DRIFT_SYMBOLS = [
    "SOL-PERP", "JTO-PERP", "PYTH-PERP", "BONK-PERP",
    "WIF-PERP", "JUP-PERP", "RNDR-PERP", "HNT-PERP"
]
```

### Failover Chain

```
Hyperliquid → Drift → Aster
Drift → Hyperliquid → Aster
```

### Game Theory Obfuscation

- **Jitter**: 50-500ms random delay
- **Fuzzing**: ±2% quantity randomization
- **Slippage**: Dynamic based on volatility

---

## 📊 API Reference

### Trading

```bash
# Execute trade (auto-routing)
POST /api/v2/trade
{
  "symbol": "BTC-PERP",
  "side": "BUY",
  "quantity": 0.01,
  "order_type": "MARKET"
}

# Force specific platform
POST /api/v2/trade
{
  "symbol": "BTC-PERP",
  "side": "BUY",
  "quantity": 0.01,
  "platform": "hyperliquid"  # or "drift"
}

# Get routing map
GET /api/v2/trade/routing
```

### Platforms

```bash
# All platform status
GET /api/v2/platforms/status

# Hyperliquid positions
GET /api/v2/platforms/hyperliquid/positions

# Drift positions
GET /api/v2/platforms/drift/positions

# Combined positions
GET /api/v2/platforms/all/positions
```

### Symphony

```bash
# All agents
GET /api/v2/symphony/status

# MIT status
GET /api/v2/symphony/mit/status

# Activate MIT
POST /api/v2/symphony/mit/activate
```

### Health

```bash
# V2 health check
GET /api/v2/health
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Google Cloud SDK
- Hyperliquid wallet (EVM)
- Drift/Solana wallet

### Installation

```bash
git clone https://github.com/arigatoexpress/Sapphire.git
cd Sapphire/cloud_trader
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```python
# In main_v2.py startup
from cloud_trader.v2 import initialize_v2_components

await initialize_v2_components(
    hyperliquid_private_key=get_secret("HYPERLIQUID_PRIVATE_KEY"),
    hyperliquid_wallet=get_secret("HYPERLIQUID_WALLET_ADDRESS"),
    drift_private_key=get_secret("DRIFT_PRIVATE_KEY"),
    firestore_client=db,
)
```

### Deployment

```bash
gcloud builds submit --config=cloudbuild.yaml .
```

---

## 📈 Metrics

| Metric | Value |
|--------|-------|
| **Uptime** | 99.99% |
| **Platforms** | 4 (2 DeFi Perps, 1 CEX, 1 Treasury) |
| **Agent Latency** | <500ms |
| **Circuit Recovery** | 30s (DeFi), 60s (CEX) |
| **Symphony Agents** | 3 (2 active, 1 pending) |

---

## 📁 Project Structure

```
sapphire/
├── cloud_trader/
│   ├── v2/                    # V2 enhancement modules
│   ├── core/                  # Orchestration
│   ├── agents/                # AI agents
│   ├── main_v2.py             # FastAPI entry
│   └── requirements.txt
├── docs/
├── terraform/
├── tests/
└── README.md
```

---

## 🛡️ Security

1. **All secrets in GCP Secret Manager**
2. **No hardcoded credentials**
3. **Circuit breakers prevent cascade failures**
4. **Rate limiting on all platforms**
5. **Audit logging to Firestore**

---

## 📈 Roadmap

- [x] V2 Architecture Migration
- [x] Hyperliquid Reinstatement
- [x] Dual Platform Router
- [ ] MIT Activation (5 trades)
- [ ] Multi-model AI (GPT-4, Claude)
- [ ] Dashboard & Analytics
- [ ] 20+ symbol expansion

---

## 🤝 Contributing

1. Fork the repo
2. Create feature branch
3. Run tests
4. Submit PR

---

## 📄 License

MIT License - see [LICENSE](/.github/LICENSE)

---

**Built with ❤️ for Autonomous Finance**

[Production](https://sapphire-v2-267358751314.us-central1.run.app) · [Health](https://sapphire-v2-267358751314.us-central1.run.app/health) · [Dashboard](https://sapphire-479610.web.app)

**Version 2.2.0** | **Hyperliquid: ACTIVE ✅** | **Drift: ACTIVE ✅**
