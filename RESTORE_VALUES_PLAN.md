# Sapphire AI 2.0 - Emergency Fix Plan: Restore Values File

## 1. The Failure
The build failed at **Step 5 (Helm Lint)** with the error:
`[ERROR] templates/: template: trading-system/templates/serviceaccount.yaml:1:14: executing "trading-system/templates/serviceaccount.yaml" at <.Values.serviceAccount.create>: nil pointer evaluating interface {}.create`

## 2. Root Cause
The `helm/trading-system/values.yaml` file was **accidentally overwritten** during the previous update. Instead of appending the new `grokTrader` configuration, the entire file was replaced with *only* that section.
-   **Result**: Critical sections like `global`, `serviceAccount`, `cloudTrader`, and `database` are missing.
-   **Impact**: Helm cannot render any templates because the default values are gone.

## 3. Action Plan

### Step 1: Restore the File
I will use `git restore` to revert `helm/trading-system/values.yaml` to its last committed state (which contained the full configuration).

### Step 2: Re-Apply Changes (Correctly)
I will append the `grokTrader` configuration and the `TRADING_SYMBOLS` setting to the restored file, ensuring I don't delete the existing content.

### Step 3: Verify
I will read the file to confirm it has both the original sections (like `serviceAccount`) and the new `grokTrader` section.

### Step 4: Re-Launch
I will trigger the build again (`gcloud builds submit`).

## 4. Execution
I am ready to execute this fix immediately.
