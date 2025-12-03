# Sapphire AI 2.0 - System Architecture & Issue Report

## Project Overview
**Sapphire AI 2.0** is a high-frequency crypto trading platform deployed on Google Kubernetes Engine (GKE). It leverages a multi-agent architecture powered by Google Vertex AI (Gemini 1.5 Pro, 2.0 Flash, etc.) for market analysis and execution.

### Architecture
- **Infrastructure**: GKE Cluster (`hft-trading-cluster`), Cloud SQL (PostgreSQL), Redis (Memorystore/Bitnami), GCP Secret Manager.
- **Deployment Pipeline**: Google Cloud Build with 5 phases:
  1. **Infra**: Redis & Secrets.
  2. **Migration**: Database Schema Update (Alembic).
  3. **Core**: Cloud Trader API & MCP Coordinator.
  4. **Agents**: 6 AI Agents (Momentum, Sentiment, Strategy, etc.).
  5. **Grok**: Ultra HFT Agent.
- **Key Components**:
  - `cloud-trader`: Main API service (FastAPI).
  - `mcp-coordinator`: Manages agent communication.
  - `grok-trader`: Specialized HFT agent.
  - **Cloud SQL Proxy**: Sidecar container for secure DB access.

## Current Status: STALLED
The deployment is failing at **Phase 2: DB Migration**.

### The Issue
- **Symptom**: Cloud Build fails at the "Deploy Migration" step.
- **Error Details**:
  - Previous Error: Race condition between Alembic container and Cloud SQL Proxy sidecar.
  - Latest Error: `strict decoding error: unknown field "spec.template.spec.backoffLimit"`.
- **Root Cause Analysis**:
  1. **Configuration Error**: The `backoffLimit` field was misplaced in the `Job` manifest (nested under `template.spec` instead of `spec`).
  2. **Sidecar Readiness**: The original failure was likely due to `alembic` running before the proxy was ready. We added an `initContainer` to fix this, but the manifest syntax error blocked verification.
  3. **Build Complexity**: Cloud Build substitution variables (`$POD_NAME`) caused syntax errors until fixed.

## Research Request for AI
**Objective**: Validate the fixed Job manifest and propose a foolproof migration strategy for GKE + Cloud SQL Proxy.

**Prompt for Research AI**:
```markdown
I am deploying a Python/Alembic migration job to GKE with a Cloud SQL Proxy sidecar.

**My Manifest (Fixed Candidate):**
apiVersion: batch/v1
kind: Job
metadata:
  name: debug-db-migration
spec:
  backoffLimit: 3  # Placed correctly under spec
  template:
    spec:
      initContainers:
        - name: wait-for-proxy
          image: busybox
          command: ["sh", "-c", "until nc -z localhost 5432; do echo waiting; sleep 2; done"]
      containers:
        - name: migration
          image: my-app:latest
          command: ["alembic", "upgrade", "head"]
        - name: cloud-sql-proxy
          image: gcr.io/cloudsql-docker/gce-proxy:1.33.2
          command: ["/cloud_sql_proxy", "-instances=...=tcp:5432"]

**Questions:**
1. Is `nc -z localhost 5432` sufficient to ensure the Cloud SQL Proxy is fully ready to accept connections, or does it just check the port listener?
2. How do I ensure the Cloud SQL Proxy sidecar terminates after the migration completes? (Currently, the Job might hang indefinitely because the sidecar keeps running).
3. Are there standard "best practice" patterns for "Job with Sidecar" in Kubernetes 1.29+ (e.g., native sidecar support)?
```
