# 🔐 Wallet & Credential Configuration Guide

This guide provides **concrete instructions** to configure wallets for your **Symphony**, **Drift**, and **Jupiter** agents.

**⚠️ SECURITY WARNING:** Never commit this info to git. Place these in your `.env` file or Cloud Run Secret Manager.

---

## 1. Agent Symphony (Monad) 🎵
Your Monad Agent is controlled via the Symphony API.

**Required Variables:**
- `SYMPHONY_API_KEY`: Your provided API Key (starts with `sk_live_...`).
- `SYMPHONY_BASE_URL`: `https://api.symphony.finance` (Defaults to this, can be omitted).

**How to Configure:**
1.  Open your `.env` file (or Cloud Run Secrets).
2.  Add the line:
    ```bash
    SYMPHONY_API_KEY="sk_live_YOUR_KEY_HERE"
    ```

---

## 2. Drift Protocol (Solana Futures) 🌊
Used for executing Perps (e.g., `SOL-PERP`).

**Required Variables:**
- `SOLANA_PRIVATE_KEY`: Base58 encoded private key of your Solana wallet.
- `SOLANA_RPC_URL`: (Optional) Custom RPC for better speed (e.g., Helius/Triton). Defaults to Public Mainnet.
- `DRIFT_SUBACCOUNT_ID`: (Optional) Subaccount ID to trade on (Default: `0`).

**How to Configure:**
1.  Export your Private Key from Phantom/Backpack (Settings -> Export Private Key).
2.  Add to `.env`:
    ```bash
    SOLANA_PRIVATE_KEY="YOUR_BASE58_PRIVATE_KEY"
    SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
    DRIFT_SUBACCOUNT_ID="0"
    ```

---

## 3. Jupiter (Solana Swaps) 🪐
Used for Spot Swaps (e.g., USDC -> SOL).

**Required Variables:**
- `SOLANA_PRIVATE_KEY`: Shared with Drift (above).
- `JUPITER_API_KEY`: (Optional) Free tier works, but Key recommended for high frequency.

**How to Configure:**
1.  Add to `.env`:
    ```bash
    JUPITER_API_KEY="YOUR_JUPITER_KEY_IF_YOU_HAVE_ONE"
    ```

---

## Summary Checklist

Ensure your `.env` file looks like this:

```bash
# === MONAD AGENT ===
SYMPHONY_API_KEY="sk_live_..."

# === SOLANA AGENTS (Drift & Jupiter) ===
SOLANA_PRIVATE_KEY="EtW..."
SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"

# === OPTIONAL ===
JUPITER_API_KEY="..."
DRIFT_SUBACCOUNT_ID="0"
```

**✅ Verification:**
Run the verification script to confirm connections:
```bash
python3 verify_accounts.py
```
