# Cloud Trader Engine 🤖

The core execution engine for the Sapphire AI Trading System.

## Overview

Cloud Trader is a high-performance Python service designed for autonomous multi-chain trading. It implements a decoupled, agentic architecture that separates discovery, deliberation, and execution.

### Key Capabilities
- **Multi-Agent Swarm**: Coordinates 6 specialized AI agents for market analysis and decision making.
- **Cross-Chain Execution**: Unified routing to Symphony (Monad/Base) and Aster (Solana).
- **Self-Improving Intelligence**: Autonomous feedback loops that update agent strategy weights based on real-time PnL.
- **Microservices Core**: FastAPI-based REST and WebSocket endpoints for low-latency dashboard synchronization.

## The Swarm (Agents)

| Agent | Focus | Strategy Evolution |
|-------|-------|-------------------|
| **Trend Momentum** | Macro breakouts | Volatility-aware weighting |
| **Strategy Optimizer** | TP/SL optimization | Dynamic risk adjustment |
| **Sentiment Analyst** | Social/News impact | Confidence-based filtering |
| **Market Predictor** | Price action forecasting | Pattern-match learning |
| **Microstructure** | Order flow / VPIN | Latency-optimized execution |
| **Risk Guard** | Drawdown protection | Global exposure management |

## Core Engine Structure

| Module | Purpose |
|--------|---------|
| `trading_service.py` | Main event loop and agent orchestration. |
| `market_scanner.py` | Discovery engine for high-probability setups. |
| `platform_router.py` | Platform-agnostic execution adapter (Symphony/Aster). |
| `autonomous_agent.py` | Base class for self-learning intelligence. |
| `data_store.py` | Unified data access with TTL multi-level caching. |

## Running Locally

```bash
# Ensure you are in the project root
python3 start.py
```

## Environment Configuration

Key variables required in `.env`:
- `SYMPHONY_API_KEY`: Authentication for Monad/Base agents.
- `HL_SECRET_KEY`: Private key for Hyperliquid/Aster DEX.
- `GROK_API_KEY`: Intelligence source for agent arbitration.
- `DATABASE_URL`: (Optional) Persistence layer for trade history.

## Monitoring

Access the **Sapphire Command Center** at [https://api.sapphiretrade.xyz/dashboard](https://api.sapphiretrade.xyz/dashboard) (or your local port: 8080).

---
*For internal tools and legacy modules, see the [`internal/`](../internal/) directory.*
