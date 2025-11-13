
# MANUAL GPU QUOTA REQUEST INSTRUCTIONS

## Step-by-Step Process:

### 1. Access GCP Console
   - Go to: https://console.cloud.google.com/iam-admin/quotas
   - Ensure project 'sapphireinfinite' is selected

### 2. Locate TPU Quota
   - Use search/filter: "TPUs (all regions)"
   - Find the quota line with Metric = "TPUS_ALL_REGIONS"

### 3. Submit Quota Request
   - Click on the quota line
   - Click "EDIT QUOTA" button
   - Fill in request details:

     **Quota Details:**
     - Name: TPUs (all regions)
     - Current limit: 0
     - New limit: 1
     - Reason: Cost-effective TPU acceleration for AI trading

### 4. Provide Justification
   Copy and paste this justification:

   "Sapphire Trading System is a cost-optimized AI-powered algorithmic trading platform that uses selective GPU acceleration only where absolutely necessary. The system employs 5 specialized AI agents with intelligent resource allocation: 4 CPU-optimized agents (DeepSeek, Qwen, FinGPT, Lag-LLaMA) and 1 GPU-accelerated VPIN trader for real-time volume-based informed trading analysis.

   GPU acceleration is strategically applied only to the VPIN trader, which requires high-performance computing for real-time market microstructure analysis. This cost-effective approach provides GPU precision where critical while maintaining CPU efficiency for other trading strategies.

   Initial deployment requires only 2 GPUs for the VPIN trader with estimated cost of $1.50-2.50/hour. The system includes comprehensive monitoring, autoscaling, and intelligent resource allocation."

### 5. Submit Request
   - Review all information
   - Click "SUBMIT REQUEST"
   - Note the request ID for tracking

### 6. Approval Timeline
   - Standard approval: 24-48 hours
   - Expedited requests may be faster for valid use cases
   - You'll receive email notification when approved

### 7. Post-Approval Steps
   Once approved, run:
   ```bash
   ./enable_tpu_acceleration.sh
   ```

## Alternative Contact Methods:

### Phone Support
   - Call GCP Support: 1-855-836-1987
   - Reference your quota request case

### Enterprise Support
   If you have GCP Enterprise Support, create a support case with:
   - Priority: High
   - Category: Quotas
   - Component: Compute Engine

## Verification
After approval, verify with:
```bash
gcloud compute project-info describe --project=sapphireinfinite --format="value(quotas[quotas.metric=TPUS_ALL_REGIONS].limit)"
```

Expected result: 1 (or higher)
