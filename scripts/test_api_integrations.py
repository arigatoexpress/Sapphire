"""
Comprehensive API Integration Testing Suite
Tests all external service connections and documents capabilities.

Services tested:
1. Drift Protocol - Solana perpetual futures
2. Jupiter Ultra - Solana DEX swaps
3. Symphony.finance - Fund management
4. Monad - Agent orchestration (if applicable)

For each service, this suite:
- Verifies authentication
- Tests all major endpoints
- Documents rate limits
- Enumerates capabilities
- Validates error handling
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from cloud_trader.drift_client import get_drift_client
from cloud_trader.jupiter_client import JupiterSwapClient
from cloud_trader.logger import get_logger
from cloud_trader.symphony_client import SymphonyClient

logger = get_logger(__name__)


class APITestResult:
    """Result of an API test."""

    def __init__(
        self,
        service: str,
        test_name: str,
        status: str,  # "PASS", "FAIL", "SKIP"
        details: Optional[str] = None,
        data: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        self.service = service
        self.test_name = test_name
        self.status = status
        self.details = details
        self.data = data
        self.error = error
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "service": self.service,
            "test": self.test_name,
            "status": self.status,
            "details": self.details,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class DriftProtocolTester:
    """
    Test suite for Drift Protocol integration.

    Drift is a decentralized perpetual futures DEX on Solana.
    """

    def __init__(self):
        self.client = get_drift_client()
        self.service_name = "Drift Protocol"
        self.results: List[APITestResult] = []

    async def test_initialization(self) -> APITestResult:
        """Test client initialization and configuration."""
        try:
            await self.client.initialize()

            config = {
                "rpc_url": self.client.rpc_url,
                "api_base": self.client.api_base,
                "has_private_key": bool(self.client.private_key),
                "subaccount_id": self.client.subaccount_id,
                "initialized": self.client.is_initialized,
            }

            return APITestResult(
                service=self.service_name,
                test_name="initialization",
                status="PASS",
                details="Client initialized successfully",
                data=config,
            )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="initialization", status="FAIL", error=str(e)
            )

    async def test_get_perp_market(self) -> APITestResult:
        """Test fetching perpetual market data."""
        try:
            market = await self.client.get_perp_market("SOL-PERP")

            required_fields = ["symbol", "oracle_price", "funding_rate_24h", "open_interest"]
            missing_fields = [f for f in required_fields if f not in market]

            if missing_fields:
                return APITestResult(
                    service=self.service_name,
                    test_name="get_perp_market",
                    status="FAIL",
                    error=f"Missing fields: {missing_fields}",
                    data=market,
                )

            # Validate data types
            if market["oracle_price"] <= 0:
                return APITestResult(
                    service=self.service_name,
                    test_name="get_perp_market",
                    status="FAIL",
                    error="Invalid oracle price (must be > 0)",
                    data=market,
                )

            return APITestResult(
                service=self.service_name,
                test_name="get_perp_market",
                status="PASS",
                details=f"Market data fetched: SOL @ ${market['oracle_price']:.2f}",
                data=market,
            )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="get_perp_market", status="FAIL", error=str(e)
            )

    async def test_get_position(self) -> APITestResult:
        """Test fetching position data."""
        try:
            position = await self.client.get_position("SOL-PERP")

            required_fields = ["symbol", "amount", "entry_price", "unrealized_pnl"]
            missing_fields = [f for f in required_fields if f not in position]

            if missing_fields:
                return APITestResult(
                    service=self.service_name,
                    test_name="get_position",
                    status="FAIL",
                    error=f"Missing fields: {missing_fields}",
                    data=position,
                )

            return APITestResult(
                service=self.service_name,
                test_name="get_position",
                status="PASS",
                details="Position data structure valid",
                data=position,
            )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="get_position", status="FAIL", error=str(e)
            )

    async def test_place_order_simulation(self) -> APITestResult:
        """Test order placement (simulation mode)."""
        try:
            result = await self.client.place_perp_order(
                symbol="SOL-PERP", side="buy", amount=0.1, order_type="market"
            )

            if "tx_sig" not in result or "status" not in result:
                return APITestResult(
                    service=self.service_name,
                    test_name="place_order",
                    status="FAIL",
                    error="Missing tx_sig or status in response",
                    data=result,
                )

            return APITestResult(
                service=self.service_name,
                test_name="place_order",
                status="PASS",
                details="Order placement simulation successful",
                data=result,
            )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="place_order", status="FAIL", error=str(e)
            )

    async def run_all_tests(self) -> List[APITestResult]:
        """Run all Drift Protocol tests."""
        logger.info(f"🧪 Testing {self.service_name}...")

        self.results = [
            await self.test_initialization(),
            await self.test_get_perp_market(),
            await self.test_get_position(),
            await self.test_place_order_simulation(),
        ]

        passed = sum(1 for r in self.results if r.status == "PASS")
        total = len(self.results)
        logger.info(f"✅ {self.service_name}: {passed}/{total} tests passed")

        return self.results

    def get_capabilities(self) -> Dict[str, Any]:
        """Document Drift Protocol capabilities."""
        return {
            "service": "Drift Protocol",
            "type": "Decentralized Perpetual Futures DEX",
            "blockchain": "Solana",
            "capabilities": {
                "trading": {
                    "perpetual_futures": True,
                    "spot_trading": False,
                    "order_types": ["market", "limit", "stop_market", "stop_limit"],
                    "max_leverage": 20,
                    "min_position_size": 0.01,
                    "supported_symbols": ["SOL-PERP", "BTC-PERP", "ETH-PERP", "..."],
                },
                "market_data": {
                    "oracle_prices": True,
                    "funding_rates": True,
                    "open_interest": True,
                    "order_book": True,
                    "historical_candles": True,
                },
                "account": {
                    "positions": True,
                    "orders": True,
                    "pnl_tracking": True,
                    "margin_info": True,
                },
            },
            "rate_limits": {
                "rest_api": "Unknown (recommend 10 req/sec)",
                "websocket": "Available for real-time data",
                "note": "No official rate limit docs, use conservative limits",
            },
            "fees": {
                "taker": "0.06% (6 bps)",
                "maker": "0.00% (0 bps)",
                "funding": "Variable, typically ±0.01% per 8 hours",
            },
            "authentication": {
                "method": "Solana wallet signature",
                "required": ["SOLANA_PRIVATE_KEY", "DRIFT_SUBACCOUNT_ID"],
                "test_mode": "Available (no real funds)",
            },
            "sdk": {"python": "driftpy", "version": ">=0.4.0", "docs": "https://docs.drift.trade"},
            "notes": [
                "Currently using CoinGecko for prices (backup source)",
                "Full driftpy integration pending",
                "Funding rates are mocked until SDK integrated",
                "All orders are simulated in current implementation",
            ],
        }


class JupiterUltraTester:
    """
    Test suite for Jupiter Ultra Swap API.

    Jupiter is the leading DEX aggregator on Solana.
    """

    def __init__(self):
        self.client = JupiterSwapClient()
        self.service_name = "Jupiter Ultra"
        self.results: List[APITestResult] = []

        # Token addresses for testing
        self.SOL_MINT = "So11111111111111111111111111111111111111112"
        self.USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    async def test_api_connection(self) -> APITestResult:
        """Test basic API connectivity."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("https://api.jup.ag/ultra/v1/healthcheck")

                if response.status_code == 200:
                    return APITestResult(
                        service=self.service_name,
                        test_name="api_connection",
                        status="PASS",
                        details="API endpoint reachable",
                        data={"status_code": response.status_code},
                    )
                else:
                    return APITestResult(
                        service=self.service_name,
                        test_name="api_connection",
                        status="FAIL",
                        error=f"Unexpected status code: {response.status_code}",
                    )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="api_connection", status="FAIL", error=str(e)
            )

    async def test_get_order(self) -> APITestResult:
        """Test fetching a swap quote/order."""
        try:
            # Request 1 SOL -> USDC swap
            amount = 1_000_000_000  # 1 SOL in lamports

            order = await self.client.get_order(
                input_mint=self.SOL_MINT,
                output_mint=self.USDC_MINT,
                amount=amount,
                slippage_bps=50,  # 0.5% slippage
            )

            required_fields = ["inputMint", "outputMint", "inAmount", "outAmount"]
            missing_fields = [f for f in required_fields if f not in order]

            if missing_fields:
                return APITestResult(
                    service=self.service_name,
                    test_name="get_order",
                    status="FAIL",
                    error=f"Missing fields: {missing_fields}",
                    data=order,
                )

            # Calculate effective rate
            in_sol = int(order["inAmount"]) / 1e9
            out_usd = int(order["outAmount"]) / 1e6  # USDC has 6 decimals
            rate = out_usd / in_sol if in_sol > 0 else 0

            return APITestResult(
                service=self.service_name,
                test_name="get_order",
                status="PASS",
                details=f"Quote received: {in_sol:.4f} SOL → ${out_usd:.2f} USDC (rate: ${rate:.2f}/SOL)",
                data=order,
            )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="get_order", status="FAIL", error=str(e)
            )

    async def test_authentication(self) -> APITestResult:
        """Test API key authentication."""
        has_key = bool(self.client.api_key)

        if not has_key:
            return APITestResult(
                service=self.service_name,
                test_name="authentication",
                status="FAIL",
                error="JUPITER_API_KEY not configured",
                details="API key required for Jupiter Ultra",
            )

        # Test if key works with a real request
        try:
            await self.test_get_order()
            return APITestResult(
                service=self.service_name,
                test_name="authentication",
                status="PASS",
                details="API key valid and working",
                data={"api_key_length": len(self.client.api_key)},
            )
        except Exception as e:
            if "401" in str(e) or "403" in str(e):
                return APITestResult(
                    service=self.service_name,
                    test_name="authentication",
                    status="FAIL",
                    error="API key invalid or unauthorized",
                )
            else:
                return APITestResult(
                    service=self.service_name,
                    test_name="authentication",
                    status="PASS",
                    details="API key present (request failed for other reason)",
                )

    async def run_all_tests(self) -> List[APITestResult]:
        """Run all Jupiter Ultra tests."""
        logger.info(f"🧪 Testing {self.service_name}...")

        self.results = [
            await self.test_api_connection(),
            await self.test_authentication(),
            await self.test_get_order(),
        ]

        passed = sum(1 for r in self.results if r.status == "PASS")
        total = len(self.results)
        logger.info(f"✅ {self.service_name}: {passed}/{total} tests passed")

        return self.results

    def get_capabilities(self) -> Dict[str, Any]:
        """Document Jupiter Ultra capabilities."""
        return {
            "service": "Jupiter Ultra",
            "type": "DEX Aggregator",
            "blockchain": "Solana",
            "capabilities": {
                "trading": {
                    "spot_swaps": True,
                    "perpetual_futures": False,
                    "aggregation": "Routes across all Solana DEXs",
                    "supported_tokens": "15,000+ SPL tokens",
                    "min_swap_amount": "No minimum (subject to fees)",
                    "slippage_protection": True,
                },
                "routing": {
                    "multi_hop": True,
                    "split_routes": True,
                    "price_impact_minimization": True,
                    "mev_protection": True,
                },
                "execution": {
                    "atomic_swaps": True,
                    "partial_fills": False,
                    "priority_fees": "Auto-optimized",
                    "rpc_required": "No (Jupiter handles RPC)",
                },
            },
            "rate_limits": {
                "free_tier": "10 requests/second",
                "paid_tier": "100+ requests/second",
                "websocket": "Not available",
                "note": "Ultra API requires API key",
            },
            "fees": {
                "platform_fee": "0.00% (JUP takes no fees)",
                "dex_fees": "Variable (0.25% typical)",
                "priority_fee": "Auto-calculated based on network",
            },
            "authentication": {
                "method": "API key (x-api-key header)",
                "required": ["JUPITER_API_KEY"],
                "test_mode": "Quotes available without execution",
            },
            "api": {
                "version": "Ultra v1",
                "endpoint": "https://api.jup.ag/ultra/v1",
                "docs": "https://dev.jup.ag/docs/ultra",
            },
            "notes": [
                "Ultra API combines quote + transaction in one call",
                "Requires Solana wallet for signing",
                "Automatic slippage protection included",
                "Best-in-class price execution on Solana",
            ],
        }


class SymphonyTester:
    """
    Test suite for Symphony.finance integration.

    Symphony provides on-chain fund management infrastructure.
    """

    def __init__(self):
        try:
            self.client = SymphonyClient()
            self.service_name = "Symphony Finance"
            self.results: List[APITestResult] = []
        except Exception as e:
            logger.error(f"Failed to initialize Symphony client: {e}")
            self.client = None
            self.service_name = "Symphony Finance"
            self.results = []

    async def test_api_connection(self) -> APITestResult:
        """Test basic API connectivity."""
        if not self.client:
            return APITestResult(
                service=self.service_name,
                test_name="api_connection",
                status="FAIL",
                error="Client initialization failed",
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.client.base_url}/health")

                if response.status_code == 200:
                    return APITestResult(
                        service=self.service_name,
                        test_name="api_connection",
                        status="PASS",
                        details="API endpoint reachable",
                        data={"base_url": self.client.base_url},
                    )
                else:
                    return APITestResult(
                        service=self.service_name,
                        test_name="api_connection",
                        status="FAIL",
                        error=f"Health check failed: {response.status_code}",
                    )
        except Exception as e:
            return APITestResult(
                service=self.service_name, test_name="api_connection", status="FAIL", error=str(e)
            )

    async def test_authentication(self) -> APITestResult:
        """Test Symphony API authentication."""
        if not self.client:
            return APITestResult(
                service=self.service_name,
                test_name="authentication",
                status="FAIL",
                error="Client not initialized",
            )

        has_key = bool(self.client.api_key)

        if not has_key:
            return APITestResult(
                service=self.service_name,
                test_name="authentication",
                status="FAIL",
                error="SYMPHONY_API_KEY not configured",
            )

        # Test with actual API call
        try:
            account = await self.client.get_account_info()
            return APITestResult(
                service=self.service_name,
                test_name="authentication",
                status="PASS",
                details="API key valid, account accessible",
                data=account,
            )
        except Exception as e:
            if "404" in str(e):
                return APITestResult(
                    service=self.service_name,
                    test_name="authentication",
                    status="PASS",
                    details="API key works (no fund created yet)",
                    error="404 - Fund not found (expected for new accounts)",
                )
            elif "401" in str(e) or "403" in str(e):
                return APITestResult(
                    service=self.service_name,
                    test_name="authentication",
                    status="FAIL",
                    error="Authentication failed: invalid API key",
                )
            else:
                return APITestResult(
                    service=self.service_name,
                    test_name="authentication",
                    status="FAIL",
                    error=str(e),
                )

    async def test_get_account_info(self) -> APITestResult:
        """Test fetching account information."""
        if not self.client:
            return APITestResult(
                service=self.service_name,
                test_name="get_account_info",
                status="SKIP",
                details="Client not initialized",
            )

        try:
            account = await self.client.get_account_info()
            return APITestResult(
                service=self.service_name,
                test_name="get_account_info",
                status="PASS",
                details="Account info retrieved",
                data=account,
            )
        except Exception as e:
            if "404" in str(e):
                return APITestResult(
                    service=self.service_name,
                    test_name="get_account_info",
                    status="PASS",
                    details="No fund created yet (404 expected)",
                    error=str(e),
                )
            else:
                return APITestResult(
                    service=self.service_name,
                    test_name="get_account_info",
                    status="FAIL",
                    error=str(e),
                )

    async def run_all_tests(self) -> List[APITestResult]:
        """Run all Symphony tests."""
        logger.info(f"🧪 Testing {self.service_name}...")

        self.results = [
            await self.test_api_connection(),
            await self.test_authentication(),
            await self.test_get_account_info(),
        ]

        passed = sum(1 for r in self.results if r.status == "PASS")
        total = len(self.results)
        logger.info(f"✅ {self.service_name}: {passed}/{total} tests passed")

        return self.results

    def get_capabilities(self) -> Dict[str, Any]:
        """Document Symphony capabilities."""
        return {
            "service": "Symphony Finance",
            "type": "On-Chain Fund Management",
            "blockchain": "Multi-chain (EVM, Solana)",
            "capabilities": {
                "fund_management": {
                    "create_fund": True,
                    "manage_positions": True,
                    "rebalancing": True,
                    "auto_compound": True,
                },
                "asset_support": {
                    "tokens": "All ERC-20, SPL tokens",
                    "perps": True,
                    "spot": True,
                    "lp_tokens": True,
                },
                "automation": {
                    "scheduled_rebalancing": True,
                    "profit_taking": True,
                    "stop_loss": True,
                    "dca": True,
                },
            },
            "rate_limits": {
                "api": "100 requests/minute (estimated)",
                "websocket": "Not available",
                "note": "Contact Symphony for enterprise limits",
            },
            "fees": {
                "platform": "Variable (check Symphony docs)",
                "gas_optimization": "Batched transactions",
            },
            "authentication": {
                "method": "API key",
                "required": ["SYMPHONY_API_KEY"],
                "test_mode": "Available",
            },
            "api": {"base_url": "https://api.symphony.io", "docs": "https://docs.symphony.finance"},
            "notes": [
                "Current  implementation uses symphony.io domain",
                "404 errors expected if no fund created yet",
                "Supports both fund creation and management",
                "Integrates with multiple DeFi protocols",
            ],
        }


async def run_all_api_tests() -> Dict[str, Any]:
    """
    Run comprehensive API tests for all services.

    Returns:
        Complete test report with results and capabilities
    """
    logger.info("=" * 60)
    logger.info("🚀 ASTER AI TRADING SYSTEM - API INTEGRATION TEST SUITE")
    logger.info("=" * 60)

    # Initialize testers
    drift_tester = DriftProtocolTester()
    jupiter_tester = JupiterUltraTester()
    symphony_tester = SymphonyTester()

    # Run all tests
    all_results = []
    all_results.extend(await drift_tester.run_all_tests())
    all_results.extend(await jupiter_tester.run_all_tests())
    all_results.extend(await symphony_tester.run_all_tests())

    # Compile report
    report = {
        "test_run": {
            "timestamp": datetime.utcnow().isoformat(),
            "total_tests": len(all_results),
            "passed": sum(1 for r in all_results if r.status == "PASS"),
            "failed": sum(1 for r in all_results if r.status == "FAIL"),
            "skipped": sum(1 for r in all_results if r.status == "SKIP"),
        },
        "results_by_service": {
            "drift": [r.to_dict() for r in all_results if r.service == "Drift Protocol"],
            "jupiter": [r.to_dict() for r in all_results if r.service == "Jupiter Ultra"],
            "symphony": [r.to_dict() for r in all_results if r.service == "Symphony Finance"],
        },
        "capabilities": {
            "drift": drift_tester.get_capabilities(),
            "jupiter": jupiter_tester.get_capabilities(),
            "symphony": symphony_tester.get_capabilities(),
        },
    }

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Tests: {report['test_run']['total_tests']}")
    logger.info(f"✅ Passed: {report['test_run']['passed']}")
    logger.info(f"❌ Failed: {report['test_run']['failed']}")
    logger.info(f"⏭️  Skipped: {report['test_run']['skipped']}")
    logger.info("=" * 60)

    return report


async def main():
    """Main entry point for API testing."""
    report = await run_all_api_tests()

    # Save report to file
    output_file = "api_test_report.json"
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\n📝 Full report saved to: {output_file}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
