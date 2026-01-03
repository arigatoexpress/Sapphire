# 💎 Sapphire AI Trading System

<div align="center">

> **The First Multi-Chain Swarm Intelligence for High-Frequency DeFi**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-Deployed-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)

[![Solana](https://img.shields.io/badge/Solana-HFT-9945FF?logo=solana&logoColor=white)](#)
[![Monad](https://img.shields.io/badge/Monad-EVM-FF3366)](#)
[![Base](https://img.shields.io/badge/Base-L2-0052FF?logo=coinbase&logoColor=white)](#)

</div>

---

## 📖 Overview

**Sapphire** is a production-grade, autonomous trading system that orchestrates a "Swarm" of specialized AI agents across **Solana**, **Monad**, and **Base**. It combines high-frequency signal processing with a self-learning agentic architecture to capture alpha in all market regimes.

### ✨ Key Features

- 🤖 **6 Specialized AI Agents** - Each with unique trading strategies
- ⚡ **Sub-second Execution** - WebSocket-powered real-time updates  
- 🔄 **Multi-Chain Support** - Solana, Monad, Base, and EVM chains
- 🧠 **Self-Learning** - Agents adapt based on PnL outcomes
- 📊 **World-Class Dashboard** - React 18 with real-time monitoring

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Sapphire AI System                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ MarketScanner│  │AgentConsensus│  │   PlatformRouter   │  │
│  │   Discovery  │─▶│   6 Agents  │─▶│ Symphony / Aster   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Resilience │  │  Event Bus  │  │   Self-Learning     │  │
│  │   Patterns  │  │ Redis Pub/Sub│  │      Feedback       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 🧠 Core Components

| Component | Description |
|-----------|-------------|
| **MarketScanner** | Intelligent opportunity discovery using volatility & trend analysis |
| **AgentConsensus** | Orchestrates 6 specialized AI agents for weighted decision-making |
| **PlatformRouter** | Abstract adapter layer routing to Symphony (Monad/Base) or Aster (Solana) |
| **Self-Learning Feed** | Closed-loop system where agents update preferences based on PnL |

### 🐝 The AI Swarm

| Agent | ID | Specialization |
|-------|-----|----------------|
| 🎵 **MILF** | `f6cc5590-...` | Monad ecosystem swaps |
| 🏛️ **MIT** | `ee5bcfda-...` | Long-term strategic positions |
| 🔥 **AGDG** | `01b8c2b7-...` | Aggressive perpetual futures (Base) |

---

## 🛠️ Technology Stack

<table>
<tr>
<td><strong>Backend</strong></td>
<td>Python 3.11+ (Asyncio), FastAPI, uvicorn</td>
</tr>
<tr>
<td><strong>Frontend</strong></td>
<td>React 18, TypeScript, Material-UI, Vite</td>
</tr>
<tr>
<td><strong>Infrastructure</strong></td>
<td>Google Cloud Run, Firebase Hosting, Redis</td>
</tr>
<tr>
<td><strong>AI/ML</strong></td>
<td>Grok, Gemini 2.0 Flash, Vertex AI</td>
</tr>
<tr>
<td><strong>Monitoring</strong></td>
<td>Real-time WebSocket, Prometheus metrics</td>
</tr>
</table>

---

## 🛡️ Enterprise-Grade Resilience

Sapphire features world-class reliability patterns:

### Backend Resilience
```python
@with_retry(max_attempts=3, base_delay=0.5)  # Exponential backoff
@with_timeout(30.0)                           # Operation timeouts
Bulkhead(max_concurrent=20)                   # Concurrency limiting
```

- **`resilience.py`** - Retry, timeout, bulkhead patterns
- **`event_bus.py`** - Redis Pub/Sub with local fallback
- **Circuit Breakers** - Automatic failure isolation per platform
- **GZip Compression** - API response optimization

### Real-Time Observability
- **`/health/detailed`** - Comprehensive system health
- **WebSocket Events** - Live platform router updates
- **Execution History** - Last 100 trades with latency metrics

### Frontend Performance
- **React.memo** - Optimized re-rendering
- **useMemo/useCallback** - Memoized computations
- **TypeScript Strict** - Full type safety

---

## 🚀 Deployment

### Prerequisites
```bash
# Install Google Cloud SDK
brew install --cask google-cloud-sdk

# Authenticate
gcloud auth login
```

### Environment Variables
```bash
export SYMPHONY_API_KEY="..."
export GROK_API_KEY="..."  
export HL_SECRET_KEY="..."
export REDIS_URL="redis://..."  # Optional: for production caching
```

### Deploy Backend (Cloud Run)
```bash
gcloud run deploy sapphire-cloud-trader \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated
```

### Deploy Frontend (Firebase)
```bash
cd trading-dashboard
npm run build
firebase deploy --only hosting
```

---

## 📁 Project Structure

```
sapphire/
├── cloud_trader/           # 🐍 Python backend (production)
│   ├── api.py              # FastAPI endpoints
│   ├── platform_router.py  # Trade routing logic
│   ├── resilience.py       # Retry/timeout patterns
│   ├── event_bus.py        # Redis Pub/Sub
│   └── trading_service.py  # Core trading engine
├── trading-dashboard/      # ⚛️ React frontend
│   └── src/
│       ├── components/     # UI components
│       ├── contexts/       # React contexts
│       └── pages/          # Route pages
├── internal/               # 🔒 Proprietary tools (not deployed)
├── run.py                  # 🚀 Unified entry point
└── Dockerfile              # 🐳 Container configuration
```

---

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Basic health check |
| `/health/detailed` | GET | Comprehensive system health |
| `/api/platform-router/status` | GET | Platform router status |
| `/api/platform-router/metrics` | GET | Execution metrics |
| `/api/platform-router/health` | GET | Platform health status |
| `/api/platform-router/history` | GET | Execution history |
| `/api/dashboard/state` | GET | Dashboard data |
| `/ws/dashboard` | WS | Real-time updates |

---

## 🧪 Testing

```bash
# Run backend tests
python -m pytest tests/

# Verify imports
python -c "from cloud_trader.api import app; print('✅ Backend OK')"

# Frontend build
cd trading-dashboard && npm run build
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ by the Sapphire AI Team for the Future of Finance**

[Website](https://sapphiretrade.xyz) · [Dashboard](https://sapphire-479610.web.app)

</div>
