# 💎 Aster AI Trading System
> *The First Multi-Chain Swarm Intelligence for High-Frequency DeFi.*

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.11+-blue.svg) ![Solana](https://img.shields.io/badge/Solana-HFT-purple) ![Monad](https://img.shields.io/badge/Monad-EVM-red)

**Aster** is a production-grade, autonomous trading system that orchestrates a "Swarm" of specialized AI agents across **Solana** and **Monad**. It combines high-frequency signal processing with agentic portfolio management to capture alpha in all market regimes.

![Architecture](https://mermaid.ink/img/pako:eNqVVEFv2zAM_iuCTu2AJEG3Fdtl26HAYtuwYRiKXYaJSLZMWTIlO0mR4v9HyU6cOmmH9RLJ9_iRjxJ9oEprhECV1U_Gk_gW_Vbgl6q65o24J-Vb0qA0OqO1OaGzOaOzBUNnC4bOLhn2O2Q47JHhsE-GwyEZDkdkeEiGh2MyPJyQ4fCUDE-nZHg6I8PzGRl-nJPh5ZwMzxdk-HlFht9XZPjjigx_r8nwzy0Z_r0lw_93ZPig_4Rj8Scciz_hWPwJx-LPZfhbV0T4W_8TEdHPGf789D8TEdHPGf768j8TEbFOyPC3j4iIdUaGv31ERPznZPj7R0TEPyfDt6iIiH9Ohm9REfHPyfAtKiL-ORm-RUXEvyDDt6iI-Bdk-BYVEf-C_B_FiP8v9H8UI_6_0P9RjPj_Qv9HMeL_C_0fxYj_L_R_FCP-v9D_UYz4_0L_RzHi_wv9H8WI_y_0fxQj_r_Q_1GM-P9C_0fvq_8D3aL-D3SL-j_QLer_QL_Q_wPd4X-hW_Q_0C36H-gW_f8XukX_A92i_4F-of8HukX_A92i_4F-of8HukX_A92i_4F-of9f6Bb9D3SL_ge6Rf8D3aL_gX6h_we6Rf8D3aL_gX6h_we6Rf8D3aL_gX6h_we6Rf8D3aL_gX6h_we6Rf8D3aL_gX6h_we6xf4HukX_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3WL_A91i_wPdYv8D3aL_ge5Qf6B7VF_odlUf6A7VF7pD9YXuUH2hO1Rf6A7VF7pD9YXuUH2hO1Rf6A7VF7pD9YXuUH2hO1Rf6A7VF7pD9YXuUH2hO1Rf6A7VF7pD9YXuUH2hO1Rf6A7VF7pD9YXuUH2h21V9oDtUf6BbVF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukv1he5SfaG7VF_oLtUXukP1he5QfaE7VF_oDtUXukP1he5QfaE7VF_oDtUXukP1he5Q_f8B3aH6Qneo_kC3qL7QXaovdLf_Bbpb9YXuVn2hu1Vf6G7VF7pb9YXunn-hu1df6O7VF7oH9YXugX-he1Bf6B7VF7oH9YXuvv-h29df6Pb1F7p9_YV-X__P_wGz7i_k)

## ⚡ Cutting-Edge Architecture

Aster is not just a bot; it's a **distributed swarm architecture** running on a microservices backbone.

### 🧠 The Core Brain: `Market Regime Engine`
*   **Regime Detection**: Real-time classification of "Bull", "Bear", or "Crab" markets using multi-factor analysis (Volume, Volatility, Momentum).
*   **Context Awareness**: Filters signals that don't match the macro environment (e.g., blocks Longs in Bear trends).

### 🐝 The Swarm (Specialized Agents)
1.  **🎵 Monad Vanguard (The Ecosystem Capture)**:
    *   **Tech**: High-Frequency EVM Native.
    *   **Role**: Aggressively captures early ecosystem value. Handles "Launch Season" rotations and maintains a basket of high-conviction assets (**$MON**, **$EMO**, **$MONCOCK**).
2.  **🌊 Drift Sniper (The Alpha Generator)**:
    *   **Tech**: Solana RPC + Drift Protocol SDK.
    *   **Role**: Executes **Symmetric Mean Reversion** trades on Perps with sub-second latency.
3.  **🪐 Jupiter Treasurer (The Smart Sweeper)**:
    *   **Tech**: **Jupiter Ultra API (v1)** + GPU Pathfinding.
    *   **Role**: Automatically sweeps USDC profits into hard assets (SOL) using the most efficient routes on-chain.

---

## 🛠 Technology Stack

*   **Language**: Python 3.11+ (Asyncio Core).
*   **Cloud infrastructure**: Google Cloud Run (Serverless, Auto-Scaling).
*   **Data Engineering**: `pandas` + `polars` for vectorised signal processing.
*   **Integrations**:
    *   **Drift Protocol** (Perps)
    *   **Symphony** (Monad Agentic Layer)
    *   **Jupiter Ultra** (Aggregator)

## 🚀 Deployment

Aster is designed for **"One-Click" Cloud Deployment**.

1.  **Configure Secrets**:
    ```bash
    export SYMPHONY_API_KEY="..."
    export SOLANA_PRIVATE_KEY="..."
    export JUPITER_API_KEY="..."
    ```
2.  **Verify Integrity**:
    ```bash
    python3 scripts/verification/verify_accounts.py
    ```
3.  **Launch**:
    ```bash
    gcloud builds submit --tag gcr.io/project/aster
    gcloud run deploy aster --image gcr.io/project/aster
    ```

## 🛡 Security

*   **Secret Redaction**: Custom `ContextLogger` automatically masks keys and sensitive data in logs.
*   **Non-Custodial**: Private keys are injected at runtime; never stored in code.
*   **Risk Engine**: Hard-stops on drawdown limits and toxic flow detection.

---
*Built with ❤️ by the Sapphire AI Team for the Future of Finance.*
