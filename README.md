# Sapphire V2.3

**Autonomous AI Trading System**

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

High-performance autonomous trading system with **independent platform traders**, memory-augmented learning, and reinforcement learning integration.

**V2.3 ARCHITECTURE**: Each trader operates independently on its dedicated platform with **no consensus delays**, optimized for maximum speed and profitability.

---

## 🚀 What's New in V2.3

### Independent Platform Traders (No Consensus)
- **3-5 second latency eliminated** - No more waiting for agent consensus votes
- **Autonomous execution** - Each trader makes independent decisions for its platform
- **Platform-specific optimization** - Traders optimized for their exchange's quirks
- **Better reliability** - Platform failures don't cascade to other traders

### Platform-Specific Trading
```
Drift Trader      → Drift Platform only (Solana Perps: SOL, JUP, BONK, WIF)
Hyperliquid       → Hyperliquid only (L1 Perps: BTC, ETH, SOL, HYPE, DOGE)
Aster Trader      → Aster only (CEX with Shield Strategy for HFT)
Symphony Trader   → Symphony only (Monad Treasury: MON, DAC, DEGEN)
Lighter Trader    → Lighter only (Eth L2: WBTC-USDC, WETH-USDC)
```

### Removed in V2.3
- ❌ Jupiter spot swaps (API key issues) - kept for price data only
- ❌ Multi-agent consensus voting system
- ❌ Cross-platform failover chains
- ❌ Complex routing logic

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SAPPHIRE V2.3                                   │
│                      INDEPENDENT PLATFORM TRADERS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Vue 3 Frontend                               │    │
│  │              (Trader Terminals + System Overview)                    │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                          WebSocket + REST                                    │
│                                 │                                            │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │                      FastAPI Gateway                                 │    │
│  │                   (main_v2.py : Cloud Run)                           │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                    ┌────────────┴────────────┐                              │
│                    │   Platform Router        │                              │
│                    │  (Direct Execution)      │                              │
│                    │  NO CONSENSUS            │                              │
│                    └──┬──────┬──────┬──────┬──┘                              │
│                       │      │      │      │                                 │
│                       ▼      ▼      ▼      ▼      ▼                          │
│                  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                   │
│                  │Drift│ │Hyper│ │Aster│ │Symph│ │Light│                   │
│                  │     │ │liquid│ │     │ │ony │ │er   │                   │
│                  │Perps│ │ L1  │ │ CEX │ │Monad│ │Eth  │                   │
│                  │Sol  │ │Perps│ │Shield│ │Trea │ │ L2  │                   │
│                  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                   │
│                     ↑       ↑       ↑       ↑       ↑                        │
│                     │       │       │       │       │                        │
│              Independent Traders (No Cross-Platform Failover)                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Trading Platforms

| Platform | Type | Chain | Status | Primary Symbols |
|----------|------|-------|--------|-----------------|
| **Hyperliquid** | DeFi Perpetuals | L1 | ✅ Active | BTC, ETH, SOL, HYPE, DOGE, AVAX |
| **Drift** | Perpetuals | Solana | ✅ Active | SOL, JUP, PYTH, BONK, WIF |
| **Aster** | CEX | - | ✅ Active | All pairs (US blocked) |
| **Symphony** | Treasury | Monad/Base | ✅ Active | MON, DAC, DEGEN, BRETT |
| **Lighter** | Order Book | Ethereum L2 | ✅ Active | WBTC-USDC, WETH-USDC |
| **Jupiter** | DEX Aggregator | Solana | 📊 Data Only | Price feeds (trading disabled) |

---

## Independent Trader Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     INDEPENDENT PLATFORM EXECUTION                           │
│                          (No Consensus Voting)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│         Market Data Feed (Price, Volume, Order Book, Sentiment)              │
│                                   │                                          │
│         ┌─────────────────────────┼─────────────────────────┐               │
│         │              │          │          │              │               │
│         ▼              ▼          ▼          ▼              ▼               │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│   │  Drift   │  │  Hyper   │  │  Aster   │  │Symphony  │  │ Lighter  │     │
│   │  Trader  │  │  liquid  │  │  Trader  │  │ Trader   │  │  Trader  │     │
│   │    🌀    │  │  Trader  │  │    ⚡    │  │    🎵    │  │    💡    │     │
│   │          │  │    🔷    │  │          │  │          │  │          │     │
│   ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤     │
│   │Platform: │  │Platform: │  │Platform: │  │Platform: │  │Platform: │     │
│   │  Drift   │  │Hyperliq. │  │  Aster   │  │ Symphony │  │ Lighter  │     │
│   │          │  │          │  │          │  │          │  │          │     │
│   │Strategy: │  │Strategy: │  │Strategy: │  │Strategy: │  │Strategy: │     │
│   │VPIN HFT  │  │Momentum  │  │ Shield   │  │Treasury  │  │Arb/MM    │     │
│   │          │  │          │  │10-125x   │  │          │  │          │     │
│   │Leverage: │  │Leverage: │  │Leverage  │  │Leverage: │  │Leverage: │     │
│   │5-20x     │  │10-50x    │  │          │  │1.1-25x   │  │5-10x     │     │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│        │             │             │             │             │            │
│        ▼             ▼             ▼             ▼             ▼            │
│   EXECUTE       EXECUTE       EXECUTE       EXECUTE       EXECUTE           │
│  DIRECTLY       DIRECTLY      DIRECTLY      DIRECTLY      DIRECTLY          │
│  (< 100ms)      (< 100ms)     (< 50ms)      (< 200ms)     (< 150ms)         │
│                                                                              │
│  NO CONSENSUS • NO VOTING • NO WAITING                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Performance Improvements

| Metric | V2.2 (Consensus) | V2.3 (Independent) | Improvement |
|--------|------------------|--------------------| ------------|
| Decision Latency | 3-5 seconds | < 100ms | **50x faster** |
| Trade Frequency | 10/day | 15-20/day | **+50-100%** |
| Platform Failures | Cascade | Isolated | **Better reliability** |
| Code Complexity | High | Low | **Simpler** |

---

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
# Cloud Run deployment
gcloud builds submit --config=cloudbuild_all_microservices.yaml

# Check status
gcloud run services describe sapphire-v2 --region=us-central1
```

---

## Security

- All secrets stored in Google Cloud Secret Manager
- Circuit breakers prevent cascade failures (per-platform isolation)
- Rate limiting on all platform connections
- Per-platform authentication (EIP-712, Solana, API keys)

---

## Performance Features

### Aster Shield Strategy (HFT)
- **Rapid SL placement**: Stop-loss within 100ms of entry
- **Dynamic leverage**: 10-125x based on volatility and confidence
- **Position chasing**: Trailing stops for winning trades
- **Intelligent SL distance**: Tighter stops for higher leverage

### Autonomous Learning System
- **Drift**: Self-learning Solana perps trader, discovers optimal patterns through experience
- **Hyperliquid**: Autonomous L1 trader, evolves strategies based on what works
- **Aster**: Adaptive HFT learner, masters high-leverage execution organically
- **Symphony**: Self-improving Monad trader, learns profitable ecosystem patterns
- **Lighter**: Intelligent L2 trader, discovers arbitrage and market-making opportunities

**NO hardcoded strategies** - Each agent develops its own methodology through:
- Pattern discovery from successful trades
- Continuous adaptation to market conditions
- Platform-specific optimization through experience
- Frequent trading with self-evolved approaches

---

## License

MIT

---

**Version 2.3.0** | 5 Trading Platforms | Independent Traders | No Consensus Delays | 50x Faster
