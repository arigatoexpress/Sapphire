# Sapphire AI 2.0 - Technical Architecture

## Architecture Diagram
```mermaid
graph TD
    User[Trader/Admin] -->|HTTPS| Ingress[GKE Ingress]
    Ingress --> Service[Cloud Trader Service]

    subgraph GKE Cluster (hft-trading-cluster)
        direction TB

        subgraph Core Services
            Service --> API[Cloud Trader API Pod]
            API --> Sidecar[Cloud SQL Proxy v2]
            API --> Redis[Redis Cache]
        end

        subgraph Agent Layer
            Coordinator[MCP Coordinator]
            Grok[Grok HFT Trader]
            Momentum[Momentum Agent]
            Sentiment[Sentiment Agent]
            Strategy[Strategy Agent]

            API <--> Coordinator
            Coordinator <--> Grok
            Coordinator <--> Momentum
            Coordinator <--> Sentiment
            Coordinator <--> Strategy
        end
    end

    subgraph Google Cloud Platform
        Sidecar -->|Secure Tunnel| CloudSQL[(Cloud SQL PostgreSQL)]
        API -->|API Call| VertexAI[Vertex AI (Gemini Models)]
        API -->|API Call| SecretMgr[Secret Manager]
        Grok -->|API Call| XAI[xAI API (Grok)]
    end
```

## Component Details

### 1. Cloud Trader API
- **Language**: Python 3.11 (FastAPI)
- **Role**: Gateway for all trading operations.
- **Database**: SQLAlchemy + AsyncPG for non-blocking DB access.
- **Scaling**: Horizontal Pod Autoscaling (HPA) based on CPU/Memory.

### 2. Grok Trader (HFT)
- **Language**: Python 3.11
- **Model**: Grok Beta (via xAI API).
- **Logic**: Continuous event loop (5s interval).
    - Fetches market context.
    - Evaluates `get_trade_signal` using LLM reasoning.
    - Executes via Cloud Trader API.
- **Safety**: Built-in liquidation mitigation (monitor margin ratio > 85%).

### 3. Native Sidecar Pattern
We use Kubernetes 1.29+ **Native Sidecars** for the Cloud SQL Proxy.
- **Mechanism**: The proxy is defined as an `initContainer` with `restartPolicy: Always`.
- **Benefit**: It starts *before* the main application container but continues running throughout the Pod's lifecycle. This guarantees DB connectivity is available immediately when the app starts, eliminating race conditions.

### 4. Secrets Management
- **Source**: GCP Secret Manager.
- **Sync**: Secrets are fetched during the `cloudbuild` process and injected into Kubernetes Secrets (`cloud-trader-secrets`).
- **Usage**: Mounted as environment variables in Pods.

## Data Flow
1.  **Market Data**: Ingested by `Cloud Trader` from external exchanges (Binance/Bybit via CCXT or specialized adapters).
2.  **Analysis**: Data is pushed to Redis Pub/Sub.
3.  **Agent Processing**: Agents (Grok, Momentum, etc.) consume data, query Vertex AI/xAI models for inference, and publish signals back to Redis.
4.  **Execution**: `Cloud Trader` consumes signals, validates against Risk checks, and executes orders.
5.  **Persistence**: All trades, signals, and PnL snapshots are stored in Cloud SQL.
