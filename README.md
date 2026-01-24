# Sapphire

**Autonomous AI Trading System**

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Production-grade trading system with multi-platform DeFi execution, AI agent consensus, memory-augmented learning, and reinforcement learning integration.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SAPPHIRE V2                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Vue 3 Frontend                               │    │
│  │                    (sapphire-web / Dashboard)                        │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│                          WebSocket + REST                                    │
│                                 │                                            │
│  ┌──────────────────────────────▼──────────────────────────────────────┐    │
│  │                      FastAPI Gateway                                 │    │
│  │                   (main_v2.py : Cloud Run)                           │    │
│  │                                                                      │    │
│  │  /api/trades  /api/agents  /api/positions  /health  /api/symphony   │    │
│  └──────────────────────────────┬──────────────────────────────────────┘    │
│                                 │                                            │
│        ┌────────────────────────┼────────────────────────┐                  │
│        │                        │                        │                  │
│        ▼                        ▼                        ▼                  │
│  ┌───────────┐           ┌───────────┐           ┌───────────┐             │
│  │   Agent   │           │  Episodic │           │  Circuit  │             │
│  │Orchestrator│◄─────────│  Memory   │           │  Breakers │             │
│  │  (Swarm)  │  recall   │   (RAG)   │           │           │             │
│  └─────┬─────┘           └───────────┘           └─────┬─────┘             │
│        │                                               │                    │
│        │ consensus                              protects│                    │
│        ▼                                               ▼                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       Platform Router                                │   │
│  │              (Symbol-based routing + Automatic Failover)             │   │
│  └───┬─────────┬─────────┬─────────┬─────────┬─────────┬───────────────┘   │
│      │         │         │         │         │         │                    │
│      ▼         ▼         ▼         ▼         ▼         ▼                    │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐               │
│  │Hyper- │ │ Drift │ │Jupiter│ │Lighter│ │ Aster │ │Symph- │               │
│  │liquid │ │       │ │       │ │       │ │       │ │ony    │               │
│  │       │ │       │ │       │ │       │ │       │ │       │               │
│  │ Perps │ │ Perps │ │ Spot  │ │ Perps │ │  CEX  │ │Monad  │               │
│  │  L1   │ │Solana │ │Solana │ │Eth L2 │ │       │ │Treasury               │
│  └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Trading Platforms

| Platform | Type | Chain | Status | Primary Symbols |
|----------|------|-------|--------|-----------------|
| **Hyperliquid** | DeFi Perpetuals | L1 | Active | BTC, ETH, SOL, HYPE, DOGE, AVAX |
| **Drift** | Perpetuals | Solana | Active | SOL, JUP, PYTH, BONK, WIF |
| **Jupiter** | DEX Aggregator | Solana | Active | SOL, JUP, RAY, ORCA (Spot) |
| **Lighter** | Order Book | Ethereum L2 | Active | WBTC-USDC, WETH-USDC |
| **Aster** | CEX | - | Active | All pairs (US blocked) |
| **Symphony** | Treasury | Monad/Base | Active | MON, DAC, DEGEN, BRETT |

---

## Agent Swarm Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AGENT ORCHESTRATOR                                  │
│                      (Weighted Consensus Voting)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                            Market Data Feed                                  │
│                    (Price, Volume, Order Book, Sentiment)                    │
│                                   │                                          │
│         ┌─────────────────────────┼─────────────────────────┐               │
│         │              │          │          │              │               │
│         ▼              ▼          ▼          ▼              ▼               │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│   │ Momentum │  │  Market  │  │  Swing   │  │  Drift   │  │    RL    │     │
│   │  Trader  │  │  Maker   │  │  Trader  │  │  Trader  │  │  Agent   │     │
│   │    📈    │  │    ⚡    │  │    🧠    │  │    🌀    │  │   🤖    │     │
│   ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤     │
│   │Win: 65%  │  │Win: 62%  │  │Win: 68%  │  │Win: 62%  │  │  (PPO)   │     │
│   │Risk: 1.4x│  │Risk: 2.0x│  │Risk: 1.3x│  │Risk: 1.1x│  │Weight:0.3│     │
│   │Lev: 20x  │  │Lev: 25x  │  │Lev: 10x  │  │Lev: 10x  │  │          │     │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│        │             │             │             │             │            │
│        └─────────────┴──────┬──────┴─────────────┴─────────────┘            │
│                             │                                                │
│                             ▼                                                │
│                  ┌─────────────────────┐                                    │
│                  │  Sigmoid Consensus  │                                    │
│                  │   (k=3, t=0.35)     │                                    │
│                  │                     │                                    │
│                  │  Signal = Σ(w × v)  │                                    │
│                  │  if Signal > 0.35:  │                                    │
│                  │     EXECUTE         │                                    │
│                  └──────────┬──────────┘                                    │
│                             │                                                │
│                             ▼                                                │
│                    ┌─────────────────┐                                      │
│                    │ LONG│SHORT│HOLD │                                      │
│                    └─────────────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Specifications

| Agent | Platform | Type | Baseline Win Rate | Risk Multiplier | Max Leverage |
|-------|----------|------|-------------------|-----------------|--------------|
| Momentum Trader | Aster | Momentum | 65% | 1.4x | 20x |
| Market Maker | Aster | Market Making | 62% | 2.0x | 25x |
| Swing Trader | Aster | Swing | 68% | 1.3x | 10x |
| Drift Trader | Drift | Perpetuals | 62% | 1.1x | 10x |
| Monad Treasury | Symphony | Swap | 60% | 1.0x | 20x |
| Ari Gold Fund | Symphony | Perpetuals | 60% | 1.5x | 25x |
| RL Agent (PPO) | All | Reinforcement | - | - | - |

---

## Symphony Treasury System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SYMPHONY AGENT ECOSYSTEM                                │
│                         (Monad + Base Chain)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│           ┌────────────────────────────────────────────────────┐            │
│           │              Symphony Agent Manager                 │            │
│           │         (Firestore Persistence + Tracking)          │            │
│           └───────────────────────┬────────────────────────────┘            │
│                                   │                                          │
│          ┌────────────────────────┼────────────────────────────┐            │
│          │                        │                            │            │
│          ▼                        ▼                            ▼            │
│   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐        │
│   │    MILF     │          │    AGDG     │          │     MIT     │        │
│   │     🦾      │          │     🦅      │          │     🏛️      │        │
│   ├─────────────┤          ├─────────────┤          ├─────────────┤        │
│   │ Status:     │          │ Status:     │          │ Status:     │        │
│   │  ACTIVE ✅  │          │  ACTIVE ✅  │          │ PENDING ⏳  │        │
│   ├─────────────┤          ├─────────────┤          ├─────────────┤        │
│   │ Chain:      │          │ Chain:      │          │ Activation: │        │
│   │  Monad      │          │  Base       │          │  0/5 trades │        │
│   ├─────────────┤          ├─────────────┤          │  ░░░░░ 0%   │        │
│   │ Type:       │          │ Type:       │          ├─────────────┤        │
│   │  SWAP       │          │  PERPS      │          │ Leverage:   │        │
│   ├─────────────┤          ├─────────────┤          │  20x        │        │
│   │ Strategy:   │          │ Strategy:   │          │ TP/SL:      │        │
│   │ Whale Track │          │ AI/Privacy  │          │  Enabled    │        │
│   │ Smart Money │          │ Virtuals    │          │             │        │
│   └─────────────┘          └─────────────┘          └─────────────┘        │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │  MIT ACTIVATION FLOW                                                │   │
│   │  ════════════════════                                               │   │
│   │                                                                     │   │
│   │   Trade 1     Trade 2     Trade 3     Trade 4     Trade 5          │   │
│   │     ○───────────○───────────○───────────○───────────○              │   │
│   │   PENDING    PENDING     PENDING     PENDING    ACTIVATING         │   │
│   │                                                      │              │   │
│   │                                                      ▼              │   │
│   │                                               ┌─────────────┐      │   │
│   │                                               │   ACTIVE    │      │   │
│   │                                               │ Production  │      │   │
│   │                                               │   Trading   │      │   │
│   │                                               └─────────────┘      │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Memory & Learning System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EPISODIC MEMORY SYSTEM                                │
│                    (RAG Architecture + Vector Search)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌─────────────────────────────────────────────────────────────────┐      │
│    │                      Trade Execution                             │      │
│    │        (Symbol, Side, Entry, Exit, PnL, Duration)                │      │
│    └───────────────────────────┬─────────────────────────────────────┘      │
│                                │                                             │
│                                ▼                                             │
│    ┌─────────────────────────────────────────────────────────────────┐      │
│    │                    Episode Generation                            │      │
│    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │      │
│    │  │Market Data  │  │  Decision   │  │       Outcome           │  │      │
│    │  │ • OHLCV     │  │ • Signal    │  │ • PnL                   │  │      │
│    │  │ • Indicators│  │ • Confidence│  │ • Was Profitable?       │  │      │
│    │  │ • Regime    │  │ • Reasoning │  │ • Exit Price/Duration   │  │      │
│    │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │      │
│    └───────────────────────────┬─────────────────────────────────────┘      │
│                                │                                             │
│          ┌─────────────────────┼─────────────────────┐                      │
│          │                     │                     │                      │
│          ▼                     ▼                     ▼                      │
│   ┌─────────────┐       ┌─────────────┐       ┌─────────────┐              │
│   │  In-Memory  │       │   Vector    │       │  Firestore  │              │
│   │   Storage   │       │   Index     │       │ Persistence │              │
│   ├─────────────┤       ├─────────────┤       ├─────────────┤              │
│   │ Max: 1000   │       │ Similarity  │       │  Durable    │              │
│   │ Recent: 100 │       │   Search    │       │  Backup     │              │
│   │ Fast Access │       │  Top-K      │       │  GCloud     │              │
│   └─────────────┘       └─────────────┘       └─────────────┘              │
│                                │                                             │
│                                ▼                                             │
│    ┌─────────────────────────────────────────────────────────────────┐      │
│    │                    Reflection Agent                              │      │
│    │          (Lesson Extraction + Confidence Calibration)            │      │
│    │                                                                  │      │
│    │  "What worked?" ──► Update agent thresholds                      │      │
│    │  "What failed?" ──► Avoid similar patterns                       │      │
│    └─────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Circuit Breaker Protection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CIRCUIT BREAKER LAYER                                   │
│                   (Per-Platform Failure Protection)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    Normal Operation                Failure Detected              Recovery   │
│    ════════════════                ════════════════              ════════   │
│                                                                              │
│    ┌─────────┐                    ┌─────────┐                 ┌─────────┐   │
│    │ CLOSED  │ ──5 failures──►   │  OPEN   │ ──timeout──►   │HALF_OPEN│   │
│    │   ✅    │                    │   ❌    │                 │   ⚠️    │   │
│    │ Accept  │                    │ Reject  │                 │  Test   │   │
│    │Requests │                    │   All   │                 │ Request │   │
│    └─────────┘                    └─────────┘                 └────┬────┘   │
│         ▲                                                          │        │
│         │                                                          │        │
│         └──────────────────── success ─────────────────────────────┘        │
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │  PLATFORM CIRCUIT CONFIGURATION                                    │   │
│    ├────────────────────────────────────────────────────────────────────┤   │
│    │                                                                    │   │
│    │  Platform      Fail Threshold    Recovery Timeout    Call Timeout  │   │
│    │  ─────────────────────────────────────────────────────────────────│   │
│    │  Hyperliquid        5                 60s               10s        │   │
│    │  Drift              5                 60s               15s        │   │
│    │  Jupiter            5                 60s               10s        │   │
│    │  Lighter            5                 60s               10s        │   │
│    │  Aster              5                 60s               10s        │   │
│    │  Symphony           5                 60s               10s        │   │
│    │  Vertex AI          3                 60s               60s        │   │
│    │  Redis              3                 15s                5s        │   │
│    │  Database           3                 30s               15s        │   │
│    │  Telegram           5                300s               10s        │   │
│    │                                                                    │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │  FAILOVER CHAIN                                                    │   │
│    │                                                                    │   │
│    │  Hyperliquid ──[fail]──► Drift ──[fail]──► Aster                  │   │
│    │  Drift ──[fail]──► Hyperliquid ──[fail]──► Aster                  │   │
│    │  Jupiter ──[fail]──► Drift (for SOL pairs)                        │   │
│    │                                                                    │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Microservices Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MICROSERVICES LAYER                                  │
│                           (services/)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ api-gateway │  │alpha-engine │  │market-scan  │  │   shared    │        │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤        │
│  │ Entry Point │  │ Alpha Gen   │  │ Opportunity │  │ Common Libs │        │
│  │ Rate Limit  │  │ Signals     │  │ Arbitrage   │  │ Memory      │        │
│  │ Routing     │  │ Strategy    │  │ Scanning    │  │ AI Recovery │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │bot-hyperliq │  │  bot-drift  │  │ bot-jupiter │  │  bot-aster  │        │
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤        │
│  │ DeFi Perps  │  │ SOL Perps   │  │ DEX Swaps   │  │ CEX Trading │        │
│  │ EIP-712     │  │ Driftpy SDK │  │ Ultra API   │  │ REST + WS   │        │
│  │ Dual Speed  │  │ Subaccounts │  │ Spot Only   │  │ US Blocked  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│  ┌─────────────┐                                                            │
│  │bot-symphony │                                                            │
│  ├─────────────┤                                                            │
│  │ Treasury    │                                                            │
│  │ MILF/AGDG   │                                                            │
│  │ MIT Tracker │                                                            │
│  └─────────────┘                                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Risk Management

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RISK MANAGEMENT STACK                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                      Position Level                                 │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │     │
│  │  │ Adaptive     │  │   Dynamic    │  │   Kelly      │              │     │
│  │  │ TP/SL        │  │   Slippage   │  │  Fraction    │              │     │
│  │  │              │  │   Control    │  │   Sizing     │              │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                      Portfolio Level                                │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │     │
│  │  │ Risk Guard   │  │ Correlation  │  │  Drawdown    │              │     │
│  │  │ (Max Loss)   │  │  Analysis    │  │  Protection  │              │     │
│  │  │              │  │              │  │              │              │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                      System Level                                   │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │     │
│  │  │ Circuit      │  │    Rate      │  │  Emergency   │              │     │
│  │  │ Breakers     │  │   Limiting   │  │  Close All   │              │     │
│  │  │              │  │              │  │              │              │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Real-Time Communication

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     WEBSOCKET + NOTIFICATIONS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     WebSocket Manager                                │    │
│  │                                                                      │    │
│  │  Message Types:                                                      │    │
│  │  • TRADE_UPDATE        • PORTFOLIO_UPDATE    • SYSTEM_HEALTH        │    │
│  │  • AGENT_STATUS        • MARKET_DATA         • MEMORY_UPDATE        │    │
│  │  • CONSENSUS_DECISION  • PERFORMANCE_METRICS • MARKET_REGIME        │    │
│  │                                                                      │    │
│  │  Features:                                                           │    │
│  │  • Client subscriptions to specific feeds                            │    │
│  │  • Microsecond timestamp sync                                        │    │
│  │  • Auto ping/keep-alive                                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Telegram Integration                              │    │
│  │                                                                      │    │
│  │  Alerts:                                                             │    │
│  │  • Trade notifications with AI analysis                              │    │
│  │  • Market insights and sentiment                                     │    │
│  │  • Risk warnings                                                     │    │
│  │  • Daily statistics summary                                          │    │
│  │  • Startup/shutdown alerts                                           │    │
│  │                                                                      │    │
│  │  Features:                                                           │    │
│  │  • Per-symbol throttling                                             │    │
│  │  • Lightweight HTTP API (no library dependencies)                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Trading
```
POST /api/v2/trade                    Execute trade with auto-routing
POST /api/symphony/trade/perpetual    Symphony perpetual trade
POST /api/symphony/trade/spot         Symphony spot trade
POST /api/jupiter/swap                Jupiter DEX swap
GET  /api/jupiter/quote               Get Jupiter quote
```

### Positions & Portfolio
```
GET  /api/positions                   Current positions
GET  /positions/all                   All platform positions
GET  /portfolio-status                Portfolio overview
GET  /performance/stats               Performance metrics
PUT  /positions/{symbol}/tpsl         Update TP/SL
POST /position/{symbol}/close         Close position
```

### Agents
```
GET  /api/agents/list                 List all agents
GET  /api/agents/metrics              Agent performance metrics
GET  /api/agents/consensus-history    Recent consensus decisions
GET  /api/agents/evolution/{id}       Agent evolution over time
```

### Platform Router
```
GET  /api/platform-router/status      Router status
GET  /api/platform-router/metrics     Routing metrics
GET  /api/platform-router/health      Platform health
```

### Symphony
```
GET  /api/v2/symphony/status          All symphony agents
GET  /api/v2/symphony/mit/status      MIT activation progress
POST /api/v2/symphony/mit/activate    Execute MIT trade
```

### System
```
GET  /health                          System health
GET  /health/detailed                 Detailed health check
POST /start                           Start trading
POST /stop                            Stop trading
POST /emergency/close-all             Emergency close all
```

---

## Project Structure

```
Sapphire/
├── cloud_trader/
│   ├── v2/                           # V2 Core Modules
│   │   ├── hyperliquid_client.py     # Hyperliquid integration
│   │   ├── lighter_client.py         # Lighter integration
│   │   ├── dual_platform_router.py   # Multi-platform routing
│   │   ├── hardened_memory_manager.py# Memory with persistence
│   │   ├── symphony_agent_manager.py # Symphony agents
│   │   ├── symphony_mit_tracker.py   # MIT activation
│   │   └── enhanced_circuit_breaker.py
│   ├── agents/                       # AI Agents
│   │   ├── agent_orchestrator.py     # Swarm orchestration
│   │   ├── eliza_agent.py            # Base agent
│   │   ├── vpin_hft_agent.py         # HFT agent
│   │   └── memory_manager.py         # Agent memory
│   ├── memory/                       # Learning System
│   │   ├── episodic_memory.py        # Episode storage
│   │   └── reflection_agent.py       # Lesson extraction
│   ├── rl/                           # Reinforcement Learning
│   │   ├── rl_agent.py               # PPO agent
│   │   └── trading_env.py            # RL environment
│   ├── api.py                        # REST endpoints
│   ├── websocket_manager.py          # WebSocket handling
│   ├── drift_client.py               # Drift integration
│   ├── symphony_client.py            # Symphony integration
│   ├── jupiter_trader_unified.py     # Jupiter integration
│   ├── circuit_breaker.py            # Protection layer
│   ├── risk_manager.py               # Risk management
│   └── main_v2.py                    # Application entry
├── services/                         # Microservices
│   ├── api-gateway/                  # Entry point
│   ├── alpha-engine/                 # Signal generation
│   ├── market-scanner/               # Opportunity detection
│   ├── bot-hyperliquid/              # Hyperliquid bot
│   ├── bot-drift/                    # Drift bot
│   ├── bot-jupiter/                  # Jupiter bot
│   ├── bot-aster/                    # Aster bot
│   ├── bot-symphony/                 # Symphony bot
│   └── shared/                       # Common libraries
├── sapphire-web/                     # Frontend (Vue 3)
│   ├── src/views/
│   │   ├── DashboardView.vue         # Main dashboard
│   │   ├── AgentsView.vue            # Agent management
│   │   └── TerminalView.vue          # CLI interface
│   └── src/stores/                   # State management
├── tests/                            # Test suite
└── terraform/                        # Infrastructure
```

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
gcloud builds submit --config=cloudbuild.yaml .

# Docker Compose (local)
docker-compose up -d
```

---

## Security

- All secrets stored in Google Cloud Secret Manager
- Circuit breakers prevent cascade failures
- Rate limiting on all platform connections
- Write-ahead logging for crash recovery
- Per-platform authentication (EIP-712, Solana, API keys)
- AI-powered error classification and recovery

---

## License

MIT

---

**Version 2.2.0** | 6 Trading Platforms | 7 AI Agents | RAG Memory | RL Integration
