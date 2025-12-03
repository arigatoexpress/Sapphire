# Grok Research Prompt: Debugging Cloud Build DB Migration Failure

**Context:**
I am deploying a high-frequency trading system (Sapphire AI) to Google Cloud using Cloud Build and GKE. The deployment pipeline has 5 phases: Infra, Migration, Core, Agents, Grok.
The build is failing at **Step 7 (Deploy Phase 2: DB Migration)**.

**The Error:**
`BUILD FAILURE: Build step failure: build step 7 "gcr.io/cloud-builders/gcloud" failed: step exited with non-zero status: 1`

**The Deployment Step (from cloudbuild.yaml):**
```yaml
  # Deploy Phase 2: DB Migration
  - name: 'gcr.io/cloud-builders/gcloud'
    id: 'deploy-migration'
    entrypoint: 'bash'
    args:
    - '-c'
    - |
      gcloud container clusters get-credentials hft-trading-cluster --region us-central1-a
      # Deploy migration job standalone
      # Clean up previous job if exists
      kubectl delete job trading-db-migration -n trading --ignore-not-found=true

      # Apply the debug-migration.yaml which runs "alembic upgrade head"
      kubectl apply -f debug-migration.yaml

      # Wait for completion
      kubectl wait --for=condition=complete job/debug-db-migration -n trading --timeout=300s || {
        echo "Migration failed - debugging..."
        kubectl logs job/debug-db-migration -n trading --tail=50
        exit 1
      }
      echo "DB migration complete ✅"
```

**The Migration Manifest (debug-migration.yaml):**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: debug-db-migration
  namespace: trading
spec:
  template:
    metadata:
      labels:
        app: debug-migration
    spec:
      serviceAccountName: trading-system-sa
      restartPolicy: OnFailure
      containers:
        - name: db-migration
          image: us-central1-docker.pkg.dev/sapphireinfinite/cloud-run-source-deploy/cloud-trader:latest
          imagePullPolicy: Always
          command: ["alembic", "upgrade", "head"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: cloud-trader-secrets
                  key: DATABASE_URL
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: cloud-trader-secrets
                  key: DB_PASSWORD
        - name: cloud-sql-proxy
          image: gcr.io/cloudsql-docker/gce-proxy:1.33.2
          command:
            - "/cloud_sql_proxy"
            - "-instances=sapphireinfinite:us-central1:sapphire-trading-db=tcp:5432"
          securityContext:
            runAsNonRoot: true
```

**Hypothesis:**
1. The `cloud-trader-secrets` might be missing or empty because the "Infra" phase (Step 6) only installed Redis/Secrets, but the *values* for the secrets (like `DATABASE_URL`) are supposed to be synced from GCP Secret Manager or passed via Helm, and they might not be populated yet.
2. The `alembic` command might be failing due to connectivity issues with the Cloud SQL Proxy sidecar (race condition where proxy isn't ready?).
3. The `debug-migration.yaml` might have a permission issue with the `trading-system-sa` service account.

**Research Request:**
Please analyze this setup and provide a checklist of CLI commands I can run to:
1. **Verify Secret Existence:** Check if `cloud-trader-secrets` exists in the `trading` namespace and has valid `DATABASE_URL` and `DB_PASSWORD` data.
2. **Debug the Job:** How can I retrieve the *exact* logs of the failed `debug-db-migration` job if the Cloud Build step already exited? (The pod might still be there or deleted?).
3. **Test Local Connectivity:** Provide a `kubectl run` command to launch a temporary pod with the same image and env vars to manually test `alembic upgrade head` and `curl` connectivity to the Cloud SQL proxy.
4. **Fix the Pipeline:** Suggest improvements to `cloudbuild.yaml` to handle the Cloud SQL Proxy sidecar correctly (e.g., ensuring the main container waits for the proxy to be ready).

**Output Format:**
Provide a step-by-step "Emergency Debug Protocol" with exact `kubectl` and `gcloud` commands.
