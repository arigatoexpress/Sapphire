# Sapphire Trading System - Configuration Guide

This guide details the required API keys and configuration steps to fully activate the Sapphire Trading System's external integrations.

## 1. Environment Variables
The system expects a `.env` file in the root directory (or environment variables set in your deployment context).

```bash
# Core
SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"
SOLANA_PRIVATE_KEY="[YOUR_PRIVATE_KEY_ARRAY_OR_BASE58]"

# Integrations
SYMPHONY_API_KEY="sk_live_..."       # Required for Agentic Fund management
JUPITER_API_KEY="[OPTIONAL]"         # Improves quote performance, defaults to public API
DRIFT_SUBACCOUNT_ID="0"              # Default is 0, change if using multiple subaccounts
```

## 2. Symphony Finance Integration
**Status**: `Mocked (Demo Mode)`
**Requirement**: You must provide a valid `SYMPHONY_API_KEY` to enable fund creation and rebalancing.
1. Sign up at [Symphony Finance Developer Portal](https://symphony.finance).
2. Generate an API Key.
3. Add to `.env`.

**Without Key**: The system defaults to a mock behavior, logging warnings and simulating fund actions locally.

## 3. Drift Protocol Integration
**Status**: `Read-Only` (if private key missing)
**Requirement**: A funded Solana wallet private key is required for execution.
1. Export private key from Phantom/Solflare.
2. Ensure the wallet has SOL for rent/fees and USDC for collateral.
3. Add `SOLANA_PRIVATE_KEY` to `.env`.

## 4. Jupiter Swap Integration
**Status**: `Public API`
**Optimization**: For high-frequency trading, get a dedicated Jupiter API key.
1. Visit [Jupiter Station](https://station.jup.ag).
2. Add `JUPITER_API_KEY` to `.env`.

## 5. Deployment Checks
When deploying to Cloud Run or Docker:
- Ensure `.env` is **NOT** committed to git.
- Use the cloud provider's Secret Manager to inject these variables at runtime.
