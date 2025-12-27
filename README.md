# 💎 Sapphire AI Trading System
> *The First Multi-Chain Swarm Intelligence for High-Frequency DeFi.*

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.11+-blue.svg) ![Solana](https://img.shields.io/badge/Solana-HFT-purple) ![Monad](https://img.shields.io/badge/Monad-EVM-red)

**Sapphire** is a production-grade, autonomous trading system that orchestrates a "Swarm" of specialized AI agents across **Solana**, **Monad**, and **Base**. It combines high-frequency signal processing with a self-learning agentic architecture to capture alpha in all market regimes.

---

## ⚡ Modular Swarm Architecture

Sapphire has evolved from a monolithic bot into a **decoupled, modular architecture** built for speed and intelligence.

### 🧠 Core Components
- **`MarketScanner`**: Intelligent discovery of opportunities using real-time volatility and trend analysis.
- **`AgentConsensus`**: Orchestrates 6 specialized AI agents to reach weighted decisions before execution.
- **`PlatformRouter`**: Abstract adapter layer routing trades to **Symphony** (Monad/Base) or **Aster** (Solana).
- **`Self-Learning Feed`**: Closed-loop feedback system where agents update their indicator preferences based on PnL outcomes.

### 🐝 The Swarm (Symphony Agents)
1.  **🎵 MILF Agent** (`f6cc5590-ff96-4077-ac80-9775c7f805cc`): Optimized for Monad ecosystem swaps.
2.  **🏛️ MIT Agent** (`ee5bcfda-0919-469c-ac8f-d665a5dd444e`): The Monad Implementation Treasury, managing long-term strategic positions.
3.  **🔥 AGDG Agent** (`01b8c2b7-b210-493f-8c76-dafd97663e2c`): Aggressive perpetual futures trading on Base.

---

## 🛠 Technology Stack

*   **Language**: Python 3.11+ (Asyncio Core).
*   **Infrastructure**: Google Cloud Run (Serverless, Auto-Scaling).
*   **Intelligence**: Grok & Gemini-powered arbitration and reasoning.
*   **Monitoring**: Real-time React dashboard with sub-second WebSocket updates.

## 🚀 Deployment

Sapphire is designed for **"One-Click" Cloud Deployment** using Docker and Cloud Run.

1.  **Configure Secrets**:
    ```bash
    export SYMPHONY_API_KEY="..."
    export GROK_API_KEY="..."
    export HL_SECRET_KEY="..."
    ```
2.  **Verify Integrity**:
    ```bash
    python3 run.py --verify-only
    ```
3.  **Launch**:
    ```bash
    gcloud run deploy sapphire-cloud-trader --source . --region northamerica-northeast1
    ```

## 🧹 Pristine Repository Standards
The codebase follows a strict **"Core vs Internal"** separation:
- `cloud_trader/`: Clean, production runtime only.
- `internal/`: Proprietary tools, legacy modules, and test suites.
- `run.py`: Singular, standardized entry point.

---
*Built with ❤️ by the Sapphire AI Team for the Future of Finance.*
