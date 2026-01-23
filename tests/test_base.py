"""
Base Test Framework
Common utilities, fixtures, and base test classes for all platform tests
"""

import asyncio
import pytest
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal


class TestResult:
    """Stores individual test results"""

    def __init__(self, name: str, platform: str):
        self.name = name
        self.platform = platform
        self.passed = False
        self.error = None
        self.duration = 0.0
        self.details = {}
        self.timestamp = datetime.now()

    def mark_passed(self, details: Optional[Dict] = None):
        """Mark test as passed"""
        self.passed = True
        if details:
            self.details = details

    def mark_failed(self, error: str, details: Optional[Dict] = None):
        """Mark test as failed"""
        self.passed = False
        self.error = error
        if details:
            self.details = details

    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.platform:12} | {self.name:40} | {self.duration:.2f}s"


class PlatformTestBase:
    """Base class for platform-specific tests"""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.results = []
        self.client = None

    async def setup(self):
        """Setup before tests - override in subclass"""
        pass

    async def teardown(self):
        """Cleanup after tests - override in subclass"""
        pass

    async def run_test(self, test_name: str, test_func, *args, **kwargs):
        """Run a single test and record results"""
        result = TestResult(test_name, self.platform_name)
        start_time = datetime.now()

        try:
            test_result = await test_func(*args, **kwargs)
            result.mark_passed(test_result)
        except Exception as e:
            result.mark_failed(str(e))

        result.duration = (datetime.now() - start_time).total_seconds()
        self.results.append(result)
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary statistics"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        return {
            "platform": self.platform_name,
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "results": self.results
        }


class TestConfig:
    """Test configuration and constants"""

    # Test sizes (small amounts for testing)
    TEST_SOL_SIZE = 0.01  # 0.01 SOL (~$1-2)
    TEST_BTC_SIZE = 0.0001  # 0.0001 BTC (~$10)
    TEST_ETH_SIZE = 0.001  # 0.001 ETH (~$3-4)
    TEST_USDC_SIZE = 10.0  # $10 USDC

    # Test leverage (conservative)
    TEST_LEVERAGE = 2.0

    # Timeouts
    INIT_TIMEOUT = 30  # seconds
    ORDER_TIMEOUT = 60  # seconds
    POSITION_TIMEOUT = 60  # seconds

    # Price tolerance for limit orders
    PRICE_TOLERANCE = 0.01  # 1%

    # Test symbols by platform
    JUPITER_TEST_SYMBOLS = ["SOL-USDC", "JUP-USDC"]
    DRIFT_TEST_SYMBOLS = ["SOL-PERP", "BTC-PERP"]
    HYPERLIQUID_TEST_SYMBOLS = ["BTC-USDC", "ETH-USDC"]
    ASTER_TEST_SYMBOLS = ["BTC-USDT", "ETH-USDT"]
    SYMPHONY_TEST_SYMBOLS = ["MON-USDC"]
    LIGHTER_TEST_SYMBOLS = ["WBTC-USDC", "WETH-USDC"]


def mock_mode_active() -> bool:
    """Check if running in mock/simulation mode"""
    import os
    return os.getenv("TEST_MODE", "mock") == "mock"


async def wait_for_condition(condition_func, timeout: float = 30.0, interval: float = 1.0):
    """Wait for a condition to be true with timeout"""
    start = datetime.now()

    while (datetime.now() - start).total_seconds() < timeout:
        if await condition_func():
            return True
        await asyncio.sleep(interval)

    return False


def assert_price_valid(price: float, symbol: str):
    """Assert that a price is valid (non-zero, positive)"""
    assert price > 0, f"Invalid price for {symbol}: {price}"


def assert_balance_sufficient(balance: float, required: float, asset: str):
    """Assert that balance is sufficient"""
    assert balance >= required, f"Insufficient {asset} balance: {balance} < {required}"


def calculate_position_value(size: float, price: float, leverage: float = 1.0) -> float:
    """Calculate position value in USD"""
    return size * price * leverage


def calculate_stop_loss_price(entry_price: float, side: str, percentage: float = 0.05) -> float:
    """Calculate stop-loss price (5% by default)"""
    if side.upper() in ["BUY", "LONG"]:
        return entry_price * (1 - percentage)
    else:  # SELL, SHORT
        return entry_price * (1 + percentage)


def calculate_take_profit_price(entry_price: float, side: str, percentage: float = 0.10) -> float:
    """Calculate take-profit price (10% by default)"""
    if side.upper() in ["BUY", "LONG"]:
        return entry_price * (1 + percentage)
    else:  # SELL, SHORT
        return entry_price * (1 - percentage)
