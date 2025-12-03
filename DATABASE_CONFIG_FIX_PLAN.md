# Sapphire AI 2.0 - Emergency Fix Plan: Helm Lint Failure (Database Key)

## 1. The Issue
The build `4bb596fa` failed at **Step 5 (Helm Lint)** with a new error:
`[ERROR] templates/: template: trading-system/templates/deployment-cloud-trader.yaml:87:22: executing "trading-system/templates/deployment-cloud-trader.yaml" at <.Values.database.enabled>: nil pointer evaluating interface {}.enabled`

## 2. Root Cause
When we restored `helm/trading-system/values.yaml` previously, we might have missed restoring the `database` section, or it was deleted in a subsequent edit.
-   **Evidence:** The template tries to access `.Values.database.enabled`, but `.Values.database` is nil (missing).
-   **Confirmation:** Reading the current `values.yaml` (previous step) shows sections for `global`, `trading`, `cloudTrader`, etc., but **no `database` section**.

## 3. Action Plan

### Step 1: Restore the Database Configuration
I will manually add the missing `database` configuration block back into `helm/trading-system/values.yaml`.

**Configuration to Add:**
```yaml
# Database configuration
database:
  enabled: true
  driver: "postgresql+asyncpg"
  host: "/cloudsql/sapphireinfinite:us-central1:sapphire-trading-db"
  port: 5432
  name: "trading_db"
  user: "trading_user"
  # password: set via secret
  poolSize: 5
  maxOverflow: 10
  cloudSqlInstance: "sapphireinfinite:us-central1:sapphire-trading-db"
  metrics:
    enabled: true
  persistence:
    enabled: true
    size: 8Gi
```

### Step 2: Verify Integrity
I will read the file to ensure *all* critical sections (`global`, `cloudTrader`, `database`, `serviceAccount`, `grokTrader`) are present.

### Step 3: Re-Launch
Trigger `gcloud builds submit` again.

## 4. Execution
I am ready to apply this fix immediately.
