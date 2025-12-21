# 🚀 Aster System: Deployment Checklist

This document is the final pre-flight check before commissioning the **Aster Trading System** and its Swarm.

---

## 🔒 1. Security & Secrets (Pre-Flight)
- [ ] **Environment Variables**: Ensure `.env` is **NOT** committed to git.
- [ ] **Cloud Secrets**:
    - [ ] Add `SYMPHONY_API_KEY` to Google Verification or Cloud Run Secrets (if using Secret Manager).
    - [ ] Add `SOLANA_PRIVATE_KEY` (Base58 string).
    - [ ] Add `JUPITER_API_KEY`.
- [ ] **Log Verification**: Run `python3 verify_logger.py` to confirm that keys are successfully redacted from logs.

## 🧪 2. Integration Verification
- [ ] **Run Core Diagnostics**:
    ```bash
    python3 verify_accounts.py
    ```
    *   **Goal**: Ensure all 3 Green Checks (Symphony, Solana, Jupiter).
    *   *Troubleshooting*: If Jupiter fails (DNS), confirm Key is set.

## ☁️ 3. Cloud Deployment (Google Cloud Run)
- [ ] **Build Container**:
    ```bash
    gcloud builds submit --tag gcr.io/YOUR_PROJECT/aster-trading-system
    ```
- [ ] **Deploy Service**:
    ```bash
    gcloud run deploy aster-trading-system \
      --image gcr.io/YOUR_PROJECT/aster-trading-system \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated \
      --set-env-vars="SYMPHONY_API_KEY=...,SOLANA_PRIVATE_KEY=...,JUPITER_API_KEY=..."
    ```
    *(Note: For production, use Secret Manager instead of literal env vars).*

## 💰 4. Capitalization (Funding the Agents)
- [ ] **Solana Wallet**: Send **SOL** (Gas) and **USDC** (Collateral) to the address verified in Step 2.
    *   *Min Recommmended*: 1.0 SOL + 100 USDC.
- [ ] **Monad Fund**: No manual funding needed initially; the Symphony Agent creates the fund. Once created, deposit assets via Symphony UI or Transfer.

## 👁️ 5. Launch & Monitor
- [ ] **Start the Brain**: Service auto-starts `TradingService`.
- [ ] **Check Logs**:
    *   Look for `🎵 Symphony Fund Created`.
    *   Look for `🪐 Treasurer: Wallet Loaded`.
    *   Look for `🌊 Drift: Market Data Live`.
- [ ] **Verify Swarm Cycle**: Wait 60s to see `_run_swarm_cycle` execute (Rebalancing/Sweeping).

---
**Status**: 🟢 **READY FOR LAUNCH**
