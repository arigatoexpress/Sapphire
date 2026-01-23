# Sapphire V2 Testing Framework

Comprehensive unit tests for all trading platforms and agents.

## Overview

This testing framework verifies functionality across all 6 trading platforms:

| Platform | Type | Markets | Tests |
|----------|------|---------|-------|
| **Jupiter** | Spot Trading | 14 pairs | 7 tests |
| **Drift** | Perpetuals | 15 markets | 8 tests |
| **Hyperliquid** | Perpetuals | Multiple | 4 tests |
| **Aster** | Trading | Multiple | 3 tests |
| **Symphony** | Monad DEX | MON pairs | 3 tests |
| **Lighter** | L2 Order Book | 2 pairs | 3 tests |

**Total: 28 comprehensive tests** across 6 platforms

---

## Quick Start

### Run All Tests
```bash
cd /Users/aribs/Documents/Sapphire_Claude_V1.0
python3 run_all_tests.py
```

### Run Individual Platform Tests
```bash
# Jupiter (Spot Trading)
python3 sapphire_repo/tests/test_jupiter.py

# Drift (Perpetuals)
python3 sapphire_repo/tests/test_drift.py

# All Other Platforms
python3 sapphire_repo/tests/test_all_platforms.py
```

---

## Test Coverage

### Jupiter DEX Tests (7 tests)
1. ✅ **Initialization** - Client setup and configuration
2. ✅ **Get Token Price** - Price fetching for SOL, JUP
3. ✅ **Get Quote** - Swap quote generation
4. ✅ **Execute Swap** - Spot swap execution (simulated)
5. ✅ **Get Wallet Balance** - SOL balance retrieval
6. ✅ **Get Supported Markets** - Market listing (14 pairs)
7. ✅ **Error Handling** - Invalid input handling

### Drift Protocol Tests (8 tests)
1. ✅ **Initialization** - Client setup and wallet verification
2. ✅ **Get Perp Market** - Market info and oracle prices
3. ✅ **Get All Positions** - Position tracking
4. ✅ **Market Index Mapping** - Symbol ↔ Index conversion
5. ✅ **Open Position** - Perpetual position opening (simulated)
6. ✅ **Close Position** - Position closing (simulated)
7. ✅ **Get Supported Markets** - Market listing (15 markets)
8. ✅ **Wallet Verification** - Wallet address validation

### Hyperliquid Tests (4 tests)
1. ✅ **Initialization** - Client setup
2. ✅ **Get Positions** - Position retrieval
3. ✅ **Get Balance** - Account balance
4. ✅ **Place Order** - Order placement (simulated)

### Aster Tests (3 tests)
1. ✅ **Initialization** - Client setup
2. ✅ **Get Token Price** - Price fetching
3. ✅ **Place Order** - Order placement (simulated)

### Symphony Tests (3 tests)
1. ✅ **Initialization** - Client setup
2. ✅ **Get Token Price** - MON price fetching
3. ✅ **Execute Swap** - MON swap (simulated)

### Lighter Tests (3 tests)
1. ✅ **Initialization** - Client setup and connection
2. ✅ **Get Orderbook** - Orderbook retrieval
3. ✅ **Place Order** - Order placement (simulated)

---

## Test Configuration

### Test Sizes (Conservative)
```python
TEST_SOL_SIZE = 0.01      # 0.01 SOL (~$1-2)
TEST_BTC_SIZE = 0.0001    # 0.0001 BTC (~$10)
TEST_ETH_SIZE = 0.001     # 0.001 ETH (~$3-4)
TEST_USDC_SIZE = 10.0     # $10 USDC
TEST_LEVERAGE = 2.0       # 2x leverage (conservative)
```

### Timeouts
```python
INIT_TIMEOUT = 30       # 30 seconds for initialization
ORDER_TIMEOUT = 60      # 60 seconds for orders
POSITION_TIMEOUT = 60   # 60 seconds for positions
```

---

## Test Output

### Summary Format
```
Platform         Total   Passed   Failed  Pass Rate    Status
--------------------------------------------------------------------------------
Jupiter             7        7        0      100.0%   ✅ PASS
Drift               8        6        2       75.0%   ❌ FAIL
Hyperliquid         4        4        0      100.0%   ✅ PASS
Aster               3        3        0      100.0%   ✅ PASS
Symphony            3        3        0      100.0%   ✅ PASS
Lighter             3        3        0      100.0%   ✅ PASS
--------------------------------------------------------------------------------
TOTAL              28       26        2       92.9%   ❌ FAIL
```

### Detailed Results
```
✅ PASS | Jupiter     | test_initialization                      | 0.12s
✅ PASS | Jupiter     | test_get_token_price                     | 1.45s
❌ FAIL | Drift       | test_initialization                      | 0.08s
```

### JSON Report
Results saved to `test_results.json`:
```json
{
  "timestamp": "2026-01-23T22:45:00",
  "duration_seconds": 45.2,
  "total_platforms": 6,
  "total_tests": 28,
  "total_passed": 26,
  "total_failed": 2,
  "platforms": [...]
}
```

---

## Test Modes

### Simulation Mode (Default)
Tests run in simulation mode by default:
- No real funds at risk
- Tests client initialization
- Tests API calls
- Tests error handling
- Some tests may show "skipped" if credentials unavailable locally

### Production Mode
Set `TEST_MODE=production` to run with real API calls:
```bash
export TEST_MODE=production
python3 run_all_tests.py
```

⚠️ **Warning**: Production mode may execute real trades with small amounts

---

## Common Issues

### "Drift not initialized"
- **Cause**: Missing `DRIFT_SOLANA_PRIVATE_KEY` in local environment
- **Solution**: Expected behavior when testing locally
- **Note**: Drift client works correctly in Cloud Run production

### "Import error: driftpy"
- **Cause**: driftpy SDK not installed locally
- **Solution**: Install with `pip install driftpy` or test in Cloud Run

### "RPC timeout"
- **Cause**: Solana RPC rate limiting
- **Solution**: Tests will retry or handle gracefully

---

## Test File Structure

```
tests/
├── __init__.py              # Package init
├── README.md                # This file
├── test_base.py             # Base test framework
├── test_jupiter.py          # Jupiter tests (7 tests)
├── test_drift.py            # Drift tests (8 tests)
└── test_all_platforms.py    # Other platforms (13 tests)

run_all_tests.py             # Comprehensive test runner
```

---

## Adding New Tests

### 1. Create Test Class
```python
from tests.test_base import PlatformTestBase

class MyPlatformTests(PlatformTestBase):
    def __init__(self):
        super().__init__("MyPlatform")

    async def test_something(self):
        # Test logic
        return {"result": "data"}

    async def run_all_tests(self):
        await self.setup()
        await self.run_test("test_name", self.test_something)
        await self.teardown()
        return self.get_summary()
```

### 2. Add to Test Runner
```python
# In run_all_tests.py
from tests.test_my_platform import MyPlatformTests

# In run_all_tests():
my_platform = MyPlatformTests()
self.all_summaries.append(await my_platform.run_all_tests())
```

---

## CI/CD Integration

### GitHub Actions
```yaml
name: Run Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: python3 run_all_tests.py
```

### Cloud Build
```yaml
steps:
  - name: 'python:3.11'
    entrypoint: python3
    args: ['run_all_tests.py']
```

---

## Expected Results

### Local Testing
- **Jupiter**: 5-6/7 tests pass (some require mainnet access)
- **Drift**: 4-5/8 tests pass (requires private key in production)
- **Hyperliquid**: 3-4/4 tests pass
- **Aster**: 2-3/3 tests pass
- **Symphony**: 2-3/3 tests pass
- **Lighter**: 2-3/3 tests pass

### Production Testing (Cloud Run)
- **All platforms**: 90-100% pass rate expected
- **All clients**: Should initialize successfully
- **All operations**: Should execute or simulate correctly

---

## Support

**Documentation:**
- Testing Framework: This file
- Platform Docs: `/DRIFT_PERPETUALS_COMPLETE.md`, etc.

**Troubleshooting:**
1. Check test output for specific errors
2. Review platform-specific documentation
3. Verify credentials and configuration
4. Check network connectivity

---

**Last Updated:** 2026-01-23
**Framework Version:** 1.0
**Total Tests:** 28 across 6 platforms
