# Sapphire AI 2.0 - Emergency Fix Plan: Deployment Failure

## 1. The Issue
The build failed at **Step 5** of `cloudbuild.yaml`:
`BUILD FAILURE: Build step failure: build step 5 "gcr.io/cloud-builders/gcloud" failed: step exited with non-zero status: 1`

**Step 5 in `cloudbuild.yaml`:**
```yaml
  # Validate Helm Chart
  - name: 'gcr.io/cloud-builders/gcloud'
    entrypoint: sh
    args:
      - -c
      - |
        echo "🔍 Validating Helm Chart..."
        # ... Install Helm ...

        # Lint with error handling
        if ! helm lint ./helm/trading-system; then
          # ...
          exit 1
        fi
```

The logs stop abruptly after "Starting Step #5". This strongly suggests a syntax error in the bash script passed to `sh -c`, or `helm lint` finding a critical error in the charts.

## 2. Root Cause Analysis
The `helm lint` command is failing. This is almost certainly due to:
1.  **Templating Errors:** We recently modified `deployment-cloud-trader.yaml` to add Native Sidecars. If the YAML indentation or Go template syntax (`{{ ... }}`) is off, Helm will crash.
2.  **Missing Values:** If `helm lint` runs without the secret values or overrides, and the chart requires them (e.g., strict checking enabled), it fails.

## 3. Action Plan (The Fix)

### Step 1: Verify & Fix Helm Templates
I will manually run `helm lint` locally (or simulate it) to find the exact syntax error in `helm/trading-system`.
*   *Hypothesis:* The indentation in `deployment-cloud-trader.yaml` around the new `cloud-sql-proxy` block might be incorrect relative to the `{{- if }}` block.

### Step 2: Update Cloud Build for Better Debugging
The current logs are truncated or sparse. I will add `helm lint --debug` and `helm template --debug` to Step 5 in `cloudbuild.yaml` so we see *why* it fails next time.

### Step 3: Retry Build
Once the template error is fixed, re-submit the build.

## 4. Execution
I will now:
1.  Read the `deployment-cloud-trader.yaml` file again to check indentation.
2.  Run a dry-run lint check if possible.
3.  Patch the file if errors are found.
