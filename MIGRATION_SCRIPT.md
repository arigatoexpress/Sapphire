# 🚀 Sapphire AI 2.0 Migration Script for Google Antigravity Agent

**Objective:** Migrate the "Sapphire AI 2.0" High-Frequency Trading (HFT) System from a local Docker environment to a scalable Google Cloud Platform (GCP) infrastructure.

---

## 🧠 1. System Context & Architecture

**Project Name:** Sapphire AI (Dual-Core HFT Engine)
**Mission:** Autonomous, self-learning trading on Aster DEX and Hyperliquid.

### 🏗️ Core Components
1.  **Cloud Trader ("Aster Bulls")**:
    *   **Role:** Primary strategy engine, Grok 4.1 Orchestrator, Risk Manager.
    *   **Tech:** Python 3.11, FastAPI, `pandas-ta`.
    *   **Key Features:** Swarm Intelligence, Deep TA, Global Circuit Breaker.
    *   **Integration:** Connects to Aster DEX (REST/WS).
2.  **Hyperliquid Trader ("Hype Bulls")**:
    *   **Role:** Specialized perp scalper & profit sweeper.
    *   **Tech:** Python 3.10, `hyperliquid-python-sdk`, Gemini 2.0 Flash.
    *   **Key Features:** Real-time WebSocket feeds, Millisecond execution, Spot Sweeping.
3.  **Duality Dashboard**:
    *   **Role:** "World Class" Command & Control Interface.
    *   **Tech:** React, Vite, TailwindCSS, Lucide Icons, Recharts.
    *   **Visuals:** Cyber-Organic aesthetic, Holographic grids.
4.  **Data Layer**:
    *   **Redis:** Real-time event bus (Pub/Sub) for inter-agent communication.
    *   **PostgreSQL:** Persistent storage for trade history and learning memory.

### 🔄 Current Workflow
-   **Local:** Running via `docker-compose` with `restart: always` policies and self-healing watchdogs.
-   **Intelligence:** Agents use a "Grok Manager Loop" to tune leverage dynamically based on win-rate feedback.

---

## 📜 2. Migration Strategy (The "Antigravity" Lift)

**Agent Instruction:** "Execute the following infrastructure provisioning and deployment plan to lift Sapphire AI into GCP."

### Phase A: Infrastructure Provisioning (Terraform / GCloud)
1.  **Networking**: Create a VPC `sapphire-net` with a private subnet.
2.  **Database**: Provision **Cloud SQL for PostgreSQL** (`db-f1-micro` or equivalent).
    *   Database Name: `trading_db`
    *   User: `trading_user`
    *   *Action:* Migrate schema from `cloud_trader/database/models_advanced.py`.
3.  **Cache**: Provision **Memorystore for Redis** (Basic Tier).
    *   *Action:* Capture Connection String/IP.
4.  **Container Registry**: Enable **Artifact Registry** (`sapphire-repo`).

### Phase B: Containerization & Build
1.  **Build Images**:
    *   `cloud-trader`: Build from `./Dockerfile` (Root context).
    *   `hyperliquid-trader`: Build from `./hyperliquid_trader/Dockerfile`.
    *   `dashboard`: Build from `./trading-dashboard/Dockerfile`.
2.  **Push**: Push all images to Artifact Registry.

### Phase C: Deployment (Cloud Run vs GKE)
*Recommendation: Cloud Run for cost efficiency and ease of management.*

1.  **Deploy `cloud-trader`**:
    *   **Type:** Cloud Run Service.
    *   **Env Vars:** Populate from `.env` (Inject Secrets via Secret Manager).
        *   `DATABASE_URL`: Connect to Cloud SQL instance.
        *   `REDIS_URL`: Connect to Memorystore.
        *   `GROK_API_KEY`: **Required**.
        *   `ASTER_API_KEY` / `ASTER_SECRET_KEY`: **Required**.
    *   **Networking:** Allow egress to internet (for DEX APIs).
2.  **Deploy `hyperliquid-trader`**:
    *   **Type:** Cloud Run Service (set `--no-cpu-throttling` for WebSocket stability).
    *   **Env Vars:**
        *   `HL_SECRET_KEY`: **Required**.
        *   `GEMINI_API_KEY`: **Required**.
        *   `REDIS_URL`: Connect to Memorystore.
3.  **Deploy `dashboard`**:
    *   **Type:** Cloud Run or Firebase Hosting (Static).
    *   **Config:** Update `VITE_API_URL` to point to the `cloud-trader` Cloud Run URL.

### Phase D: Continuous Integration (CI/CD)
1.  **Cloud Build**: Set up triggers on GitHub push to `main`.
    *   Steps: Build -> Push -> Deploy to Cloud Run.

---

## 📝 3. Critical Checkpoints for the Agent

1.  **Secrets Management**:
    *   *Instruction:* "Do not hardcode keys. Create GCP Secret Manager secrets for `HL_SECRET_KEY`, `ASTER_SECRET_KEY`, `GROK_API_KEY`, and `GEMINI_API_KEY`. Mount them as environment variables."
2.  **Persistence**:
    *   *Instruction:* "Ensure `historical_data.py` backfill can write to Cloud Storage (GCS) bucket `gs://sapphire-history` instead of local disk if needed, or rely purely on Cloud SQL."
3.  **Resilience**:
    *   *Instruction:* "Configure Cloud Run min-instances to 1 for the traders to ensure the WebSocket connections remain alive 24/7."

---

## 🚀 4. "Go Live" Command

"Agent, verify the Dockerfiles in the current directory. Authenticate with GCP. Build and push the images to `us-central1-docker.pkg.dev/PROJECT_ID/sapphire-repo`. Then, deploy the `cloud-trader` and `hyperliquid-trader` services with the secrets I provide. Finally, deploy the frontend and give me the public URL."

