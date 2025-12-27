# Integration Tests

This directory contains integration tests for external API connections.

## Test Files

- `test_symphony_integration.py` - Symphony API integration (Monad perpetuals/spot)
- `test_drift_integration.py` - Drift Protocol integration (Solana perps)
- `test_aster_integration.py` - Aster DEX integration (futures trading)

## Running Integration Tests

```bash
# Run all integration tests (requires API keys)
PYTHONPATH=. pytest tests/integration/ -v

# Run with mocked external calls (for CI/CD)
PYTHONPATH=. pytest tests/integration/ -v -m "not live"

# Run specific integration test
PYTHONPATH=. pytest tests/integration/test_symphony_integration.py -v
```

## Environment Variables Required

### Symphony
- `SYMPHONY_API_KEY` - Symphony API key
- `SYMPHONY_AGENT_ID` - Agent ID for the fund

### Drift
- `SOLANA_RPC_URL` - Solana RPC endpoint
- `SOLANA_PRIVATE_KEY` - Wallet private key (for live tests)

### Aster
- `ASTER_API_KEY` - Aster exchange API key
- `ASTER_API_SECRET` - Aster exchange API secret
