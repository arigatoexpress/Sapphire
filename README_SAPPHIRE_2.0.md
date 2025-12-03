# Sapphire AI 2.0 - Deployment & Architecture Guide

## System Overview
Sapphire AI 2.0 is a high-frequency trading platform deployed on Google Kubernetes Engine (GKE). It uses a multi-agent architecture powered by Google Vertex AI (Gemini/PaLM models) to analyze markets and execute trades via a centralized Cloud Trader API.

### Core Components
1.  **Cloud Trader API (`cloud-trader`)**: The central nervous system. A FastAPI service that manages:
    -   Market Data Ingestion
    -   Trade Execution
    -   Agent Coordination (MCP)
    -   Database Persistence (Cloud SQL)
2.  **Grok Trader Agent**: An ultra-high-frequency trading agent specializing in rapid execution.
3.  **AI Agents**: A suite of 6 specialized agents (Momentum, Sentiment, Strategy, etc.) running as separate services.
4.  **Infrastructure**:
    -   **GKE Cluster**: `hft-trading-cluster` (us-central1-a)
    -   **Cloud SQL**: PostgreSQL 15 (`sapphire-trading-db`)
    -   **Redis**: Memorystore/Bitnami for high-speed caching and pub/sub.

## Deployment Architecture (Simplified)
We utilize a streamlined "Native Sidecar" architecture to avoid deployment deadlocks.

### The "No-Migration-Job" Strategy
Database migrations are **decoupled** from the application deployment pipeline.
- **Why?** To prevent race conditions and sidecar deadlocks that plague complex K8s Jobs.
- **How?** Migrations are run manually or via a standalone ephemeral pod when schema changes are needed.
- **Result:** Faster, more reliable deployments (Application updates deploy in <2 minutes).

### Deployment Flow
1.  **Build**: Cloud Build compiles the Docker image and pushes to Artifact Registry.
2.  **Deploy**: Helm upgrades the release in 3 atomic steps:
    -   **Core**: Main API & Redis.
    -   **Agents**: The suite of analytical agents.
    -   **Grok**: The HFT execution agent.

## Operational Runbook

### 1. Deploying Updates
To deploy code changes:
```bash
gcloud builds submit --config cloudbuild.yaml
```

### 2. Database Migrations
To update the database schema:
1.  Launch the migration pod:
    ```bash
    kubectl run manual-migration-pod \
      --image=us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest \
      --command -- /bin/sh -c "sleep 3600"
    ```
2.  Wait for it to be Ready (Sidecar connects automatically).
3.  Execute migration:
    ```bash
    kubectl exec -it manual-migration-pod -- alembic upgrade head
    ```
4.  Cleanup:
    ```bash
    kubectl delete pod manual-migration-pod
    ```

### 3. Monitoring
-   **Dashboard**: `https://dashboard.sapphire-ai.com` (or local via port-forward)
-   **Logs**: `kubectl logs -l app=cloud-trader -n trading`
-   **Status**: `kubectl get pods -n trading`

## Key Configuration
-   **Symbols**: Controlled via `TRADING_SYMBOLS` env var. Empty string = All Market Mode.
-   **Secrets**: Managed via GCP Secret Manager (`DATABASE_URL`, `GROK4_API_KEY`, etc.) and synced to K8s secrets at deployment time.
